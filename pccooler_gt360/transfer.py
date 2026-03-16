"""
Image transfer logic for PCCooler GT360 display.
Supports both synchronous and asynchronous operations.
"""

from __future__ import annotations

import asyncio
import zlib
import time
from collections import deque
from typing import Callable, Optional, TYPE_CHECKING

from .protocol import log_message, send_command, send_command_async

if TYPE_CHECKING:
    from .device import SerialDevice, AsyncSerialDevice

# Cached after the first META ACK — the device always returns the same value.
_cached_block_size: int = 0

# After a successful transfer EP_IN is already empty (we consumed the COMMIT
# ACK in Phase 3).  Only flush when the previous transfer failed, to clear any
# partial ACK left behind.
_prev_ok: bool = True

# Adaptive chunk sizing state
_transfer_history: deque = deque(maxlen=10)
_current_chunk_size: int = 0
_adaptive_enabled: bool = True


def _get_adaptive_chunk_size(device_block: int, verbose: bool = False) -> int:
    """Calculate optimal chunk size based on recent transfer history."""
    global _current_chunk_size, _transfer_history, _adaptive_enabled

    if not _adaptive_enabled or len(_transfer_history) < 3:
        return _current_chunk_size if _current_chunk_size > 0 else device_block

    success_rate = sum(_transfer_history) / len(_transfer_history)
    current = _current_chunk_size if _current_chunk_size > 0 else device_block

    if success_rate < 0.7 and current > 256:
        new_size = max(256, current // 2)
        if verbose and new_size != current:
            log_message(
                f"Adaptive: reducing chunk size {current} -> {new_size} (success rate: {success_rate:.1%})",
                "DEBUG", verbose
            )
        _current_chunk_size = new_size
        return new_size
    elif success_rate == 1.0 and current < device_block:
        new_size = min(device_block, int(current * 1.25))
        if verbose and new_size != current:
            log_message(
                f"Adaptive: increasing chunk size {current} -> {new_size} (success rate: 100%)",
                "DEBUG", verbose
            )
        _current_chunk_size = new_size
        return new_size

    return current


def send_image(
    device: "SerialDevice",
    image_data: bytes,
    get_next_seq: Callable[[], int],
    verbose: bool = False,
    filename: str = "image.bmp",
    chunk_delay: float = 0.001,
    fast_mode: bool = False,
    chunk_size: int = 0,
    compress: bool = False,
    compress_level: int = 6,
    adaptive: bool = True
) -> bool:
    """Send raw image data to display (synchronous)."""
    global _cached_block_size, _prev_ok, _current_chunk_size, _adaptive_enabled, _transfer_history

    if not device:
        raise RuntimeError("Device not opened.")

    if compress:
        image_data = zlib.compress(image_data, level=compress_level)
        if verbose:
            original_size = len(image_data) * 100
            compressed_size = len(image_data)
            ratio = original_size / compressed_size if compressed_size > 0 else 0
            log_message(
                f"Payload zlib-compressed (level={compress_level}): ~{ratio:.1f}% original size",
                "INFO", verbose
            )

    # Flush stale ACKs
    if fast_mode:
        if not _prev_ok:
            try:
                log_message("Fast mode: flushing stale ACK", "DEBUG", verbose)
                device.read(4096, timeout=10)
            except Exception:
                pass
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
    retries = 1 if fast_mode else 3

    # Phase 1: META
    log_message("Phase 1: META", "INFO", verbose)
    meta_body = {
        "type": "media",
        "fileSize": size,
        "fileName": filename,
    }
    if verbose:
        log_message(f"META body: {meta_body}", "DEBUG", verbose)

    ack = send_command(
        device, "POST transport", meta_body, get_next_seq(),
        verbose=verbose, desc="META", ack_timeout=ack_timeout, retries=retries
    )

    if not ack or ack.get("state") != "success":
        log_message(f"META failed: {ack}", "ERROR", verbose)
        _prev_ok = False
        return False

    device_block = ack.get("blockMaxSize") or _cached_block_size or 1024
    _cached_block_size = device_block

    _adaptive_enabled = adaptive and chunk_size == 0
    if chunk_size > 0:
        block_size = min(chunk_size, device_block)
        _current_chunk_size = block_size
    elif adaptive:
        block_size = _get_adaptive_chunk_size(device_block, verbose)
    else:
        block_size = device_block

    log_message(
        f"META OK (blockMaxSize={device_block}, using chunk={block_size}, adaptive={adaptive})",
        "INFO", verbose
    )

    # Phase 2: DATA
    log_message(f"Phase 2: DATA ({size} bytes)", "INFO", verbose)
    sent = 0
    chunk_num = 0
    write_timeout = 30000 if not fast_mode else 5000
    last_progress = 0
    start_data_time = time.time()

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

    time.sleep(0.01 if fast_mode else 0.1)

    # Phase 3: COMMIT
    log_message("Phase 3: COMMIT", "INFO", verbose)
    ack = send_command(
        device, "POST transported", {"md5": "todo", "fileName": filename},
        get_next_seq(), verbose=verbose, desc="COMMIT", ack_timeout=ack_timeout, retries=retries
    )

    if ack.get("state") != "success":
        log_message(f"COMMIT failed: {ack}", "ERROR", verbose)
        _prev_ok = False
        _transfer_history.append(False)
        return False

    log_message("Transfer complete!", "SUCCESS", verbose)
    _prev_ok = True
    _transfer_history.append(True)
    return True


async def send_image_async(
    device: "AsyncSerialDevice",
    image_data: bytes,
    get_next_seq: Callable[[], int],
    verbose: bool = False,
    filename: str = "image.bmp",
    chunk_delay: float = 0.001,
    fast_mode: bool = False,
    chunk_size: int = 0,
    compress: bool = False,
    compress_level: int = 6,
    adaptive: bool = True,
    cancellation_event: Optional[asyncio.Event] = None
) -> bool:
    """Send raw image data to display (asynchronous) with cancellation support."""
    global _cached_block_size, _prev_ok, _current_chunk_size, _adaptive_enabled, _transfer_history

    if not device:
        raise RuntimeError("Device not opened.")

    # Check for cancellation before starting
    if cancellation_event and cancellation_event.is_set():
        log_message("Transfer cancelled before start", "WARN", verbose)
        return False

    if compress:
        # Run compression in executor to avoid blocking
        loop = asyncio.get_event_loop()
        image_data = await loop.run_in_executor(
            None, lambda: zlib.compress(image_data, level=compress_level)
        )
        if verbose:
            compressed_size = len(image_data)
            log_message(
                f"Payload zlib-compressed (level={compress_level}): {compressed_size} bytes",
                "INFO", verbose
            )

    # Flush stale ACKs
    if fast_mode:
        if not _prev_ok:
            try:
                log_message("Fast mode: flushing stale ACK", "DEBUG", verbose)
                await device.read(4096, timeout=10)
            except Exception:
                pass
    else:
        try:
            flush_count = 0
            while True:
                data = await device.read(4096, timeout=50)
                if not data:
                    break
                flush_count += len(data)
            if flush_count > 0:
                log_message(f"Flushed {flush_count} bytes from input buffer", "DEBUG", verbose)
        except Exception:
            pass

    size = len(image_data)
    log_message(f"Sending {size} bytes as '{filename}' (async)", "INFO", verbose)

    ack_timeout = 500 if fast_mode else 2000
    retries = 1 if fast_mode else 3

    # Phase 1: META
    log_message("Phase 1: META (async)", "INFO", verbose)
    meta_body = {
        "type": "media",
        "fileSize": size,
        "fileName": filename,
    }

    ack = await send_command_async(
        device, "POST transport", meta_body, get_next_seq(),
        verbose=verbose, desc="META", ack_timeout=ack_timeout, retries=retries
    )

    if not ack or ack.get("state") != "success":
        log_message(f"META failed: {ack}", "ERROR", verbose)
        _prev_ok = False
        return False

    device_block = ack.get("blockMaxSize") or _cached_block_size or 1024
    _cached_block_size = device_block

    _adaptive_enabled = adaptive and chunk_size == 0
    if chunk_size > 0:
        block_size = min(chunk_size, device_block)
        _current_chunk_size = block_size
    elif adaptive:
        block_size = _get_adaptive_chunk_size(device_block, verbose)
    else:
        block_size = device_block

    log_message(
        f"META OK (blockMaxSize={device_block}, using chunk={block_size})",
        "INFO", verbose
    )

    # Phase 2: DATA
    log_message(f"Phase 2: DATA ({size} bytes, async)", "INFO", verbose)
    sent = 0
    chunk_num = 0
    write_timeout = 30000 if not fast_mode else 5000
    last_progress = 0
    start_data_time = asyncio.get_event_loop().time()

    usb_buffer_size = block_size

    while sent < size:
        # Check for cancellation
        if cancellation_event and cancellation_event.is_set():
            log_message("Transfer cancelled during DATA phase", "WARN", verbose)
            _prev_ok = False
            return False

        chunk = image_data[sent:sent + usb_buffer_size]
        chunk_num += 1
        try:
            await device.write(chunk, timeout=write_timeout)
            if chunk_delay > 0:
                await asyncio.sleep(chunk_delay)
            sent += len(chunk)

            if verbose:
                log_message(f"chunk {chunk_num}: {len(chunk)}B sent (total {sent}/{size})", "DEBUG", verbose)

            if not fast_mode:
                progress = int(100 * sent / size)
                if progress >= last_progress + 10 or sent == size:
                    log_message(f"Progress: {sent}/{size}B ({progress}%)", "INFO", verbose)
                    last_progress = progress

            # Yield control to allow other tasks to run
            await asyncio.sleep(0)

        except Exception as e:
            log_message(f"DATA error at chunk {chunk_num}: {e}", "ERROR", verbose)
            _prev_ok = False
            return False

    data_duration = asyncio.get_event_loop().time() - start_data_time
    log_message(f"DATA complete in {data_duration:.2f}s ({size/data_duration/1024:.1f} KB/s)", "INFO", verbose)

    await asyncio.sleep(0.01 if fast_mode else 0.1)

    # Phase 3: COMMIT
    log_message("Phase 3: COMMIT (async)", "INFO", verbose)
    ack = await send_command_async(
        device, "POST transported", {"md5": "todo", "fileName": filename},
        get_next_seq(), verbose=verbose, desc="COMMIT", ack_timeout=ack_timeout, retries=retries
    )

    if ack.get("state") != "success":
        log_message(f"COMMIT failed: {ack}", "ERROR", verbose)
        _prev_ok = False
        _transfer_history.append(False)
        return False

    log_message("Transfer complete!", "SUCCESS", verbose)
    _prev_ok = True
    _transfer_history.append(True)
    return True
