"""
Command-line interface for PCCooler GT360 display controller.
"""

import sys

from .image_processor import PIL_AVAILABLE
from .device import USB_AVAILABLE


def main():
    """CLI entry point - delegates to example.py for actual implementation."""
    # Check requirements first
    if not USB_AVAILABLE or not PIL_AVAILABLE:
        print("Missing dependencies. Install with:")
        print("  pip install pyserial Pillow")
        sys.exit(1)
    
    # Import here to avoid circular imports
    from example import parse_args, main as example_main
    
    args = parse_args()
    
    # Convert argparse namespace to kwargs for example_main
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
    
    try:
        example_main(**kwargs)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
