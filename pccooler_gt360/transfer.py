"""
Image transfer logic for PCCooler GT360 display.
"""

import zlib
import time
from .protocol import log_message, send_command

# Cached after the first META ACK — the device always returns the same value.
_cached_block_size: int = 0

# After a successful transfer EP_IN is already empty (we consumed the COMMIT
# ACK in Phase 3).  Only flush when the previous transfer failed, to clear any
# partial ACK left behind.
_prev_ok: bool = True


def send_image(device, image_data: bytes, get_next_seq, verbose: bool = False,
               filename: str = "image.bmp", chunk_delay: float = 0.001,
               fast_mode: bool = False, chunk_size: int = 0, compress: bool = False) -> bool:
    """Send raw image data to display.

    chunk_size: bytes per USB write call.  0 = use the device's blockMaxSize.
      Smaller values (e.g. 256) pace the MCU without needing chunk_delay > 0,
      trading slightly more USB transactions for zero artificial sleep.

    fast_mode=True (screensavers):
      - Skips the EP_IN flush when the previous frame succeeded (saves ~10 ms/frame)
      - No retries: single attempt per frame (avoids 1-3 s stall on a bad frame)
      - Tighter ACK timeout (1000 ms vs 2000 ms)

    compress=True: zlib-compress payload before sending (smaller USB transfer).
      Requires the display to support zlib-decompressed media; otherwise leave False.
    """
    global _cached_block_size, _prev_ok

    if not device:
        raise RuntimeError("Device not opened.")

    if compress:
        image_data = zlib.compress(image_data, level=6)
        if verbose:
            log_message("Payload zlib-compressed for USB", "INFO", verbose)

    # Flush stale ACKs from a previous failed transfer.
    # After a *successful* transfer EP_IN is already clean (COMMIT ACK was read
    # in Phase 3), so no flush is needed — skipping it saves 10 ms every frame.
    if fast_mode:
        if not _prev_ok:
            # One-shot: clear the one leftover ACK from the failed frame.
            try:
                log_message("Fast mode: flushing stale ACK", "DEBUG", verbose)
                device.read(4096, timeout=10)
            except Exception:
                pass
        # else: buffer is already empty, no flush needed
    else:
        try:
            flush_count = 0
            while True:
                data = device.read(4096, timeout=50)
                if not data:
                    break
                flush_count += len(data)
            if flush_count > 0:
                log_message(f"Flushed {flush_count} bytes from input buffer", "DEBUG", verbose)
        except Exception:
            pass

    size = len(image_data)
    log_message(f"Sending {size} bytes as '{filename}'", "INFO", verbose)

    ack_timeout = 500 if fast_mode else 2000
    retries    = 1   if fast_mode else 3   # 1 = single attempt (no retries)

    # ------------------------------------------------------------------
    # Phase 1: META
    # ------------------------------------------------------------------
    log_message("Phase 1: META", "INFO", verbose)
    meta_body = {
        "type": "media",
        "fileSize": size,
        "fileName": filename,
    }
    if verbose:
        log_message(f"META body: {meta_body}", "DEBUG", verbose)
        
    ack = send_command(device, "POST transport", meta_body, get_next_seq(), verbose=verbose, desc="META",
       ack_timeout=ack_timeout, retries=retries)

    if not ack or ack.get("state") != "success":
        log_message(f"META failed: {ack}", "ERROR", verbose)
        _prev_ok = False
        return False

    device_block = ack.get("blockMaxSize") or _cached_block_size or 1024
    _cached_block_size = device_block
    # Use caller-supplied chunk_size if given; must not exceed device limit
    block_size = min(chunk_size, device_block) if chunk_size > 0 else device_block
    log_message(f"META OK (blockMaxSize={device_block}, using chunk={block_size})", "INFO", verbose)

    # ------------------------------------------------------------------
    # Phase 2: DATA
    # ------------------------------------------------------------------
    log_message(f"Phase 2: DATA ({size} bytes)", "INFO", verbose)
    sent = 0
    chunk_num = 0
    # Increased write_timeout for serial bottleneck
    write_timeout = 30000 if not fast_mode else 5000
    last_progress = 0
    start_data_time = time.time()

    # Serial write chunks must not exceed the device's blockMaxSize.
    # Larger chunks cause MCU buffer overflow and corrupt the transfer.
    usb_buffer_size = block_size

    if verbose:
        log_message(f"Using usb_buffer_size={usb_buffer_size}, write_timeout={write_timeout}ms", "DEBUG", verbose)

    while sent < size:
        chunk = image_data[sent:sent + usb_buffer_size]
        chunk_num += 1
        try:
            device.write(chunk, timeout=write_timeout)
            if chunk_delay > 0:
                time.sleep(chunk_delay)
            sent += len(chunk)
            
            if verbose:
                # Per-chunk log for debugging
                log_message(f"chunk {chunk_num}: {len(chunk)}B sent (total {sent}/{size})", "DEBUG", verbose)
                
            if not fast_mode:
                progress = int(100 * sent / size)
                if progress >= last_progress + 10 or sent == size:
                    log_message(f"Progress: {sent}/{size}B ({progress}%)", "INFO", verbose)
                    last_progress = progress
        except Exception as e:
            log_message(f"DATA error at chunk {chunk_num}: {e}", "ERROR", verbose)
            _prev_ok = False
            return False

    data_duration = time.time() - start_data_time
    log_message(f"DATA complete in {data_duration:.2f}s ({size/data_duration/1024:.1f} KB/s)", "INFO", verbose)

    # Short delay to ensure MCU has processed all data before COMMIT.
    # Serial has no USB framing guarantees, so always wait a moment.
    time.sleep(0.01 if fast_mode else 0.1)

    # ------------------------------------------------------------------
    # Phase 3: COMMIT
    # ------------------------------------------------------------------
    log_message("Phase 3: COMMIT", "INFO", verbose)
    ack = send_command(device, "POST transported", {
        "md5": "todo",
        "fileName": filename,
    }, get_next_seq(), verbose=verbose, desc="COMMIT",
       ack_timeout=ack_timeout, retries=retries)

    if ack.get("state") != "success":
        log_message(f"COMMIT failed: {ack}", "ERROR", verbose)
        _prev_ok = False
        return False

    log_message("Transfer complete!", "SUCCESS", verbose)
    _prev_ok = True
    return True
