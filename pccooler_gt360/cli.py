"""
Command-line interface for PCCooler GT360 display controller.
"""

import sys
import time
import argparse
from datetime import datetime

from .controller import DisplayController
from .image_processor import ImageProcessor, PIL_AVAILABLE
from .constants import DISPLAY_MODES
from .device import USB_AVAILABLE


def main():
    parser = argparse.ArgumentParser(
        description='PCCooler GT360 Image Display Controller',
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
    
    # Input options
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument('--image', '-i', type=str, help='Image file to display')
    input_group.add_argument('--pattern', '-p', 
                           choices=['blue', 'red', 'green', 'white', 'black', 'gradient', 'grid', 'colors'],
                           help='Generate test pattern')
    input_group.add_argument('--system', '-s', action='store_true', help='Show system information')
    
    # Control commands
    parser.add_argument('--wakeup', '-w', action='store_true', help='Wakeup the display')
    parser.add_argument('--sleep', action='store_true', help='Put display to sleep')
    parser.add_argument('--recovery', action='store_true', help='Enable recovery mode')
    parser.add_argument('--timeout', type=int, metavar='SEC', help='Set display timeout in seconds (0=disable?)')
    parser.add_argument('--init', action='store_true', help='Send initialization sequence (conn + timeout + recovery)')
    
    # Display options
    parser.add_argument('--resolution', '-r', default='640x480', choices=['640x480', '480x320'],
                       help='Display resolution (default: 640x480)')
    parser.add_argument('--format', '-f', default='png', choices=['jpeg', 'png', 'bmp', 'gif', 'mp4'],
                       help='Image encoding format (default: png)')

    # Control options
    parser.add_argument('--reset', action='store_true', help='Reset USB device before sending')
    parser.add_argument('--loop', '-l', action='store_true',
                       help='Continuously upload image (~1s interval, like CPS software)')
    parser.add_argument('--delay', '-d', type=float, default=0.001,
                       help='Delay between chunks in seconds (default: 0.001 = 1ms, try 0.01 for GIFs)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Check requirements
    if not USB_AVAILABLE or not PIL_AVAILABLE:
        print("Missing dependencies. Install with:")
        print("  pip install pyserial Pillow")
        sys.exit(1)
    
    try:
        with DisplayController(verbose=args.verbose) as ctrl:
            if args.reset:
                ctrl.reset_usb_device()
            
            ctrl.open_device()
            time.sleep(1.0)
            
            # Handle control commands
            if args.wakeup:
                if ctrl.wakeup():
                    print("✅ Display wakeup sent")
                else:
                    print("❌ Wakeup failed")
                time.sleep(0.5)
            
            if args.sleep:
                if ctrl.sleep():
                    print("✅ Display sleep sent")
                else:
                    print("❌ Sleep failed")
                time.sleep(0.5)
            
            if args.recovery:
                if ctrl.recovery(enable=True):
                    print("✅ Recovery mode enabled")
                else:
                    print("❌ Recovery failed")
                time.sleep(0.5)
            
            if args.timeout is not None:
                if ctrl.set_timeout(args.timeout):
                    print(f"✅ Timeout set to {args.timeout}s")
                else:
                    print("❌ Timeout setting failed")
                time.sleep(0.3)
            
            if args.init:
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
            
            # Handle image display
            if args.image or args.pattern or args.system:
                width, height = DISPLAY_MODES[args.resolution]
                
                # Handle MP4 video files first (send directly)
                if args.image and args.image.lower().endswith('.mp4'):
                    with open(args.image, 'rb') as f:
                        mp4_data = f.read()
                    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-") + str(int(datetime.now().microsecond / 1000))
                    filename = f"{ts}.mp4"
                    print(f"📁 Sending MP4 directly: {len(mp4_data)} bytes ({filename})")
                    success = ctrl.send_image(mp4_data, filename, chunk_delay=args.delay)
                    if success:
                        print("\n✅ MP4 sent successfully!")
                    else:
                        print("\n❌ Failed to send MP4")
                    return
                
                # Generate image
                from PIL import Image
                if args.image:
                    print(f"📁 Loading: {args.image}")
                    img = ImageProcessor.load_image(args.image, width, height)
                elif args.pattern:
                    print(f"🎨 Pattern: {args.pattern}")
                    img = ImageProcessor.create_test_pattern(args.pattern, width, height)
                elif args.system:
                    print("🖥️ System info")
                    img = ImageProcessor.create_system_info(width, height)
                
                # GIF: extract first frame
                if args.image and args.image.lower().endswith('.gif'):
                    gif = Image.open(args.image)
                    gif.seek(0)
                    gif.thumbnail((width, height), Image.Resampling.LANCZOS)
                    img = Image.new('RGBA', (width, height), (0, 0, 0, 255))
                    offset = ((width - gif.width) // 2, (height - gif.height) // 2)
                    img.paste(gif.convert('RGBA'), offset)
                    print(f"📁 Extracted first frame from GIF ({gif.width}x{gif.height})")
                
                # Encode
                if args.format == 'jpeg':
                    image_data = ImageProcessor.create_jpeg(img.convert('RGB'), quality=90)
                    ext = 'jpg'
                elif args.format == 'bmp':
                    image_data = ImageProcessor.create_bmp(img.convert('RGB'))
                    ext = 'bmp'
                elif args.format == 'gif':
                    image_data = ImageProcessor.create_gif(img)
                    ext = 'gif'
                elif args.format == 'mp4':
                    print("❌ Cannot convert image to MP4. Please provide an .mp4 file directly.")
                    sys.exit(1)
                else:
                    image_data = ImageProcessor.create_png(img.convert('RGBA'))
                    ext = 'png'
                
                if args.loop:
                    print(f"🔄 Loop mode with {args.format.upper()} (Ctrl+C to stop)")
                    count = 0
                    while True:
                        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-") + str(int(datetime.now().microsecond / 1000))
                        filename = f"{ts}.{ext}"
                        ctrl.send_image(image_data, filename, chunk_delay=args.delay)
                        count += 1
                        print(f"\r🔄 Sent #{count} ({len(image_data)}B as {filename})", end="", flush=True)
                        time.sleep(1.0)
                else:
                    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-") + str(int(datetime.now().microsecond / 1000))
                    filename = f"{ts}.{ext}"
                    print(f"📊 {args.format.upper()} size: {len(image_data)} bytes ({filename})")
                    success = ctrl.send_image(image_data, filename, chunk_delay=args.delay)
                    if success:
                        print("\n✅ Image sent successfully!")
                        print("   If screen is blank, try: --loop (CPS sends continuously)")
                    else:
                        print("\n❌ Failed to send image")
                        sys.exit(1)
                
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    print("\n✅ Done!")

if __name__ == "__main__":
    main()
