#!/usr/bin/env python3
"""Example script using the pccooler_gt360 library. Pass-through for all features."""

import sys
import time
import argparse
from datetime import datetime

from pccooler_gt360 import DisplayController, ImageProcessor, ScreensaverGenerator, DISPLAY_MODES


def main(**kwargs):
    verbose = kwargs.pop("verbose", False)
    reset = kwargs.pop("reset", False)
    max_retries = kwargs.pop("max_retries", 10)
    resolution = kwargs.pop("resolution", "640x480")
    chunk_delay = kwargs.pop("chunk_delay", 0.001)
    image = kwargs.pop("image", None)
    pattern = kwargs.pop("pattern", None)
    system = kwargs.pop("system", False)
    wakeup = kwargs.pop("wakeup", False)
    sleep = kwargs.pop("sleep", False)
    recovery = kwargs.pop("recovery", False)
    timeout = kwargs.pop("timeout", None)
    init = kwargs.pop("init", False)
    brightness = kwargs.pop("brightness", None)
    orientation = kwargs.pop("orientation", None)
    fmt = kwargs.pop("format", "png")
    loop = kwargs.pop("loop", False)
    stop_event = kwargs.pop("stop_event", None)
    screensaver = kwargs.pop("screensaver", None)
    screensaver_quality = int(kwargs.pop("screensaver_quality", 60))
    screensaver_scale = float(kwargs.pop("screensaver_scale", 1.0))
    screensaver_fps = float(kwargs.pop("screensaver_fps", 30))

    width, height = DISPLAY_MODES[resolution]

    with DisplayController(verbose=verbose) as ctrl:
        if reset:
            ctrl.reset_usb_device()
        ctrl.open_device(max_retries=max_retries)
        time.sleep(1.0)

        # Control commands
        if wakeup:
            ok = ctrl.wakeup()
            print("✅ Display wakeup sent" if ok else "❌ Wakeup failed")
            time.sleep(0.5)
        if sleep:
            ok = ctrl.sleep()
            print("✅ Display sleep sent" if ok else "❌ Sleep failed")
            time.sleep(0.5)
        if recovery:
            ok = ctrl.recovery(enable=True)
            print("✅ Recovery mode enabled" if ok else "❌ Recovery failed")
            time.sleep(0.5)
        if timeout is not None:
            ok = ctrl.set_timeout(timeout)
            print(f"✅ Timeout set to {timeout}s" if ok else "❌ Timeout setting failed")
            time.sleep(0.3)
        if init:
            print("🚀 Running initialization sequence...")
            ctrl.connect()
            time.sleep(0.3)
            ctrl.set_timeout(60)
            time.sleep(0.3)
            ctrl.recovery(enable=True)
            time.sleep(0.3)
            ctrl.wakeup()
            time.sleep(0.5)
            print("✅ Initialization complete")

        if brightness is not None:
            ok = ctrl.set_brightness(brightness)
            print(f"✅ Brightness set to {brightness}%" if ok else "❌ Brightness failed")
            time.sleep(0.3)

        if orientation is not None:
            ok = ctrl.set_orientation(orientation)
            print(f"✅ Orientation set to {orientation}°" if ok else "❌ Orientation failed")
            time.sleep(0.3)

        # Screensaver: generate animated frames and upload in a tight loop
        if screensaver:
            import io as _io
            if screensaver_scale < 1.0 and screensaver_scale > 0:
                from PIL import Image as _PIL
            print(f"🖥️ Screensaver: {screensaver} (Ctrl+C or Stop to quit)")
            gen = ScreensaverGenerator(screensaver, width, height)
            # Reusable frame buffer to reduce GC pressure
            _frame_buffer = _io.BytesIO()
            # Pre-calculate scaled dimensions to avoid redundant calculations
            _scaled_width = None
            _scaled_height = None
            if screensaver_scale < 1.0 and screensaver_scale > 0:
                _scaled_width = int(width * screensaver_scale)
                _scaled_height = int(height * screensaver_scale)
            count = 0
            fail_count = 0
            max_failures = 5  # Stop after 5 consecutive failures
            t_start = time.monotonic()
            # FPS capping: calculate minimum time per frame (min 10 FPS)
            _target_fps = max(10, min(60, screensaver_fps))
            _frame_min_time = 1.0 / _target_fps
            _last_frame_time = t_start
            while not (stop_event and stop_event.is_set()):
                _frame_start = time.monotonic()
                try:
                    img = gen.next_frame()
                    if _scaled_width is not None:
                        img = img.resize((_scaled_width, _scaled_height), Image.Resampling.LANCZOS)
                    _frame_buffer.seek(0)
                    _frame_buffer.truncate()
                    img.convert("RGB").save(_frame_buffer, format="JPEG", quality=screensaver_quality, optimize=False)
                    image_data = _frame_buffer.getvalue()
                    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-") + str(int(datetime.now().microsecond / 1000))
                    success = ctrl.send_image(image_data, f"{ts}.jpg", chunk_delay=0,
                                    fast_mode=True)
                    if success:
                        fail_count = 0  # Reset on success
                        count += 1
                        if count % 30 == 0:
                            elapsed = time.monotonic() - t_start
                            fps = count / elapsed if elapsed > 0 else 0
                            print(f"\r🔄 Frame #{count} | {fps:.1f} fps | {len(image_data)}B", end="", flush=True)
                    else:
                        fail_count += 1
                        if verbose:
                            print(f"\n⚠️ Frame send failed ({fail_count}/{max_failures})")
                        if fail_count >= max_failures:
                            print(f"\n❌ Too many consecutive failures, stopping screensaver")
                            break
                except Exception as e:
                    fail_count += 1
                    if verbose:
                        print(f"\n⚠️ Frame error: {e} ({fail_count}/{max_failures})")
                    if fail_count >= max_failures:
                        print(f"\n❌ Too many consecutive errors, stopping screensaver")
                        break
                if stop_event and stop_event.wait(0.0):
                    break
                # FPS capping: sleep if frame completed faster than target
                if _frame_min_time > 0:
                    _frame_elapsed = time.monotonic() - _frame_start
                    _sleep_time = _frame_min_time - _frame_elapsed
                    if _sleep_time > 0:
                        time.sleep(_sleep_time)
            # Explicit cleanup of frame buffer
            _frame_buffer.close()
            del _frame_buffer
            print()
            return

        # Image / pattern / system
        # Pattern is only active if explicitly provided AND we're not sending image/system
        should_send_pattern = pattern is not None and not image and not system
        has_media = image is not None or system or should_send_pattern
        
        # Debug output
        if verbose:
            print(f"DEBUG: pattern={pattern}, image={image}, system={system}")
            print(f"DEBUG: should_send_pattern={should_send_pattern}, has_media={has_media}")
            print(f"DEBUG: brightness={brightness}, orientation={orientation}")
        
        if has_media:
            # MP4: send raw
            if image and image.lower().endswith(".mp4"):
                with open(image, "rb") as f:
                    data = f.read()
                
                def send_mp4():
                    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-") + str(int(datetime.now().microsecond / 1000))
                    filename = f"{ts}.mp4"
                    print(f"📁 Sending MP4: {len(data)} bytes ({filename})")
                    return ctrl.send_image(data, filename, chunk_delay=chunk_delay)

                success = send_mp4()
                if success:
                    print("✅ MP4 sent successfully!")
                    if timeout is not None and timeout > 5:
                        interval = timeout - 5
                        print(f"🔄 Keep-alive enabled (every {interval}s)")
                        while not (stop_event and stop_event.is_set()):
                            if stop_event:
                                if stop_event.wait(interval):
                                    break
                            else:
                                time.sleep(interval)
                            send_mp4()
                else:
                    print("❌ Failed to send MP4")
                return

            # Build image
            from PIL import Image
            if image:
                print(f"📁 Loading: {image}")
                img = ImageProcessor.load_image(image, width, height)
            elif system:
                print("🖥️ System info")
                img = ImageProcessor.create_system_info(width, height)
            elif should_send_pattern:
                print(f"🎨 Pattern: {pattern}")
                img = ImageProcessor.create_test_pattern(pattern, width, height)

            # GIF: first frame only
            if image and image.lower().endswith(".gif"):
                gif = Image.open(image)
                gif.seek(0)
                gif.thumbnail((width, height), Image.Resampling.LANCZOS)
                img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
                offset = ((width - gif.width) // 2, (height - gif.height) // 2)
                img.paste(gif.convert("RGBA"), offset)
                print(f"📁 First frame from GIF ({gif.width}x{gif.height})")

            # Encode
            if fmt == "jpeg":
                image_data = ImageProcessor.create_jpeg(img.convert("RGB"), quality=90)
                ext = "jpg"
            elif fmt == "bmp":
                image_data = ImageProcessor.create_bmp(img.convert("RGB"))
                ext = "bmp"
            elif fmt == "gif":
                image_data = ImageProcessor.create_gif(img)
                ext = "gif"
            elif fmt == "mp4":
                print("❌ Cannot convert image to MP4. Provide an .mp4 file with --image.")
                sys.exit(1)
            else:
                image_data = ImageProcessor.create_png(img.convert("RGBA"))
                ext = "png"

            def send_media():
                ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-") + str(int(datetime.now().microsecond / 1000))
                filename = f"{ts}.{ext}"
                return ctrl.send_image(image_data, filename, chunk_delay=chunk_delay)

            if loop:
                print(f"🔄 Loop mode ({fmt.upper()}, Ctrl+C to stop)")
                count = 0
                while not (stop_event and stop_event.is_set()):
                    success = send_media()
                    count += 1
                    print(f"\r🔄 Sent #{count} ({len(image_data)}B)", end="", flush=True)
                    if stop_event:
                        if stop_event.wait(1.0):
                            break
                    else:
                        time.sleep(1.0)
            else:
                print(f"📊 {fmt.upper()} size: {len(image_data)} bytes")
                success = send_media()
                if success:
                    print("✅ Image sent successfully!")
                    if timeout is not None and timeout > 5:
                        interval = timeout - 5
                        print(f"🔄 Keep-alive enabled (every {interval}s)")
                        while not (stop_event and stop_event.is_set()):
                            if stop_event:
                                if stop_event.wait(interval):
                                    break
                            else:
                                time.sleep(interval)
                            send_media()
                else:
                    print("❌ Failed to send image")
                    sys.exit(1)
        else:
            # No image/pattern/system: just wake and send default pattern if no other control
            has_control_command = any((
                wakeup, sleep, recovery, timeout is not None, init,
                brightness is not None, orientation is not None
            ))
            
            # Debug output
            if verbose:
                print(f"DEBUG (else): has_control_command={has_control_command}")
                print(f"DEBUG (else): wakeup={wakeup}, sleep={sleep}, recovery={recovery}")
                print(f"DEBUG (else): timeout={timeout}, init={init}")
                print(f"DEBUG (else): brightness={brightness}, orientation={orientation}")
            
            if not has_control_command:
                # No media, no control commands: send default blue pattern
                ctrl.wakeup()
                img = ImageProcessor.create_test_pattern("blue", width, height)
                png_data = ImageProcessor.create_png(img)
                ctrl.send_image(png_data, "example.png", chunk_delay=chunk_delay)
                print("Done (default pattern sent).")

    print("✅ Done!")


def parse_args():
    p = argparse.ArgumentParser(
        description="Example: PCCooler GT360 display (full feature pass-through).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Input
    g = p.add_mutually_exclusive_group()
    g.add_argument("--image", "-i", type=str, help="Image file to display")
    g.add_argument(
        "--pattern", "-p",
        choices=["blue", "red", "green", "white", "black", "gradient", "grid", "colors"],
        help="Test pattern",
    )
    g.add_argument("--system", "-s", action="store_true", help="Show system information")
    # Control
    p.add_argument("--wakeup", "-w", action="store_true", help="Wakeup display")
    p.add_argument("--sleep", action="store_true", help="Put display to sleep")
    p.add_argument("--recovery", action="store_true", help="Enable recovery mode")
    p.add_argument("--timeout", type=int, metavar="SEC", help="Display timeout in seconds")
    p.add_argument("--init", action="store_true", help="Init sequence (conn + timeout + recovery + wakeup)")
    p.add_argument("--reset", action="store_true", help="Reset USB device before open")
    p.add_argument("--brightness", "-b", type=int, metavar="0-100",
                   help="Set display brightness (0-100)")
    p.add_argument("--orientation", "-o", type=int, metavar="ANGLE",
                   choices=[0, 90, 180, 270],
                   help="Set display orientation (0/90/180/270)")
    # Display
    p.add_argument("--resolution", "-r", default="640x480", choices=["640x480", "480x320"], help="Resolution")
    p.add_argument("--format", "-f", default="png", choices=["jpeg", "png", "bmp", "gif", "mp4"], help="Encode format")
    p.add_argument("--loop", "-l", action="store_true", help="Continuously upload (~1s interval)")
    p.add_argument("--delay", "-d", type=float, default=0.001, dest="chunk_delay", help="Chunk delay (s)")
    p.add_argument("--max-retries", type=int, default=10, dest="max_retries", help="Open device retries")
    p.add_argument("--fps", type=float, default=30, dest="screensaver_fps",
                   metavar="10-60",
                   help="Screensaver max FPS (10-60, default: 30)")
    p.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    # Pass through all options as kwargs
    kwargs = {
        "verbose": args.verbose,
        "reset": args.reset,
        "max_retries": args.max_retries,
        "resolution": args.resolution,
        "chunk_delay": args.chunk_delay,
        "image": args.image,
        "pattern": args.pattern,
        "system": args.system,
        "wakeup": args.wakeup,
        "sleep": args.sleep,
        "recovery": args.recovery,
        "timeout": args.timeout,
        "init": args.init,
        "brightness": args.brightness,
        "orientation": args.orientation,
        "format": args.format,
        "loop": args.loop,
        "screensaver_fps": args.screensaver_fps,
    }
    main(**kwargs)
