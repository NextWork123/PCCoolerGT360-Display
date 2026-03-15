#!/usr/bin/env python3
"""Example script using the pccooler_gt360 library. Pass-through for all features."""

import sys
import time
import argparse

from pccooler_gt360 import DisplayController, ImageProcessor, ScreensaverGenerator, DISPLAY_MODES


def main(**kwargs):
    verbose = kwargs.pop("verbose", False)
    reset = kwargs.pop("reset", False)
    max_retries = kwargs.pop("max_retries", 10)
    resolution = kwargs.pop("resolution", "640x480")
    chunk_delay = kwargs.pop("chunk_delay", 0.001)
    image = kwargs.pop("image", None)
    pattern = kwargs.pop("pattern", "blue")
    system = kwargs.pop("system", False)
    wakeup = kwargs.pop("wakeup", False)
    sleep = kwargs.pop("sleep", False)
    recovery = kwargs.pop("recovery", False)
    timeout = kwargs.pop("timeout", None)
    init = kwargs.pop("init", False)
    fmt = kwargs.pop("format", "png")
    loop = kwargs.pop("loop", False)
    stop_event = kwargs.pop("stop_event", None)
    screensaver = kwargs.pop("screensaver", None)
    screensaver_quality = int(kwargs.pop("screensaver_quality", 60))
    screensaver_scale = float(kwargs.pop("screensaver_scale", 1.0))

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

        # Screensaver: generate animated frames and upload in a tight loop
        if screensaver:
            import io as _io
            if screensaver_scale < 1.0 and screensaver_scale > 0:
                from PIL import Image as _PIL
            print(f"🖥️ Screensaver: {screensaver} (Ctrl+C or Stop to quit)")
            gen = ScreensaverGenerator(screensaver, width, height)
            buf = _io.BytesIO()
            count = 0
            t_start = time.monotonic()
            while not (stop_event and stop_event.is_set()):
                img = gen.next_frame()
                if screensaver_scale < 1.0 and screensaver_scale > 0:
                    w, h = img.size
                    img = img.resize((int(w * screensaver_scale), int(h * screensaver_scale)), _PIL.Resampling.LANCZOS)
                buf.seek(0)
                buf.truncate()
                img.convert("RGB").save(buf, format="JPEG", quality=screensaver_quality, optimize=False)
                image_data = buf.getvalue()
                ts = generate_timestamp()
                ctrl.send_image(image_data, f"{ts}.jpg", chunk_delay=0,
                                fast_mode=True)
                count += 1
                if count % 30 == 0:
                    elapsed = time.monotonic() - t_start
                    fps = count / elapsed if elapsed > 0 else 0
                    print(f"\r🔄 Frame #{count} | {fps:.1f} fps | {len(image_data)}B", end="", flush=True)
                if stop_event and stop_event.wait(0.0):
                    break
            print()
            return

        # Image / pattern / system
        has_media = image is not None or pattern is not None or system
        if has_media:
            # MP4: send raw
            if image and image.lower().endswith(".mp4"):
                with open(image, "rb") as f:
                    data = f.read()
                
                def send_mp4():
                    ts = generate_timestamp()
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
            else:
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
                ts = generate_timestamp()
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
            if not any((wakeup, sleep, recovery, timeout is not None, init)):
                ctrl.wakeup()
                img = ImageProcessor.create_test_pattern(pattern, width, height)
                png_data = ImageProcessor.create_png(img)
                ctrl.send_image(png_data, "example.png", chunk_delay=chunk_delay)
                print("Done (default pattern sent).")

    print("✅ Done!")


def parse_args():
    """Parse command line arguments for the PCCooler GT360 CLI."""
    p = argparse.ArgumentParser(
        description="PCCooler GT360 Image Display Controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send an image file
  %(prog)s --image /path/to/image.png

  # Send blue test pattern
  %(prog)s --pattern blue

  # Show system info
  %(prog)s --system

  # Wakeup the display
  %(prog)s --wakeup

  # Initialize display (conn + timeout + recovery + wakeup)
  %(prog)s --init

  # Set display timeout to 60 seconds
  %(prog)s --timeout 60

  # Send image and wakeup
  %(prog)s --pattern blue --wakeup

  # Debug mode with verbose output
  %(prog)s --pattern blue --verbose
        """
    )
    
    # Input options (mutually exclusive)
    input_group = p.add_mutually_exclusive_group()
    input_group.add_argument("--image", "-i", type=str, help="Image file to display")
    input_group.add_argument(
        "--pattern", "-p",
        default="blue",
        choices=["blue", "red", "green", "white", "black", "gradient", "grid", "colors"],
        help="Test pattern (default: blue)",
    )
    input_group.add_argument("--system", "-s", action="store_true", help="Show system information")
    
    # Control commands
    p.add_argument("--wakeup", "-w", action="store_true", help="Wakeup display")
    p.add_argument("--sleep", action="store_true", help="Put display to sleep")
    p.add_argument("--recovery", action="store_true", help="Enable recovery mode")
    p.add_argument("--timeout", type=int, metavar="SEC", help="Display timeout in seconds (0=disable)")
    p.add_argument("--init", action="store_true", help="Init sequence (conn + timeout + recovery + wakeup)")
    p.add_argument("--reset", action="store_true", help="Reset USB device before open")
    
    # Display options
    p.add_argument("--resolution", "-r", default="640x480", choices=["640x480", "480x320"], help="Resolution")
    p.add_argument("--format", "-f", default="png", choices=["jpeg", "png", "bmp", "gif", "mp4"], help="Encode format")
    p.add_argument("--loop", "-l", action="store_true", help="Continuously upload (~1s interval)")
    p.add_argument("--delay", "-d", type=float, default=0.001, dest="chunk_delay", help="Chunk delay (s)")
    p.add_argument("--max-retries", type=int, default=10, dest="max_retries", help="Open device retries")
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
        "format": args.format,
        "loop": args.loop,
    }
    main(**kwargs)
