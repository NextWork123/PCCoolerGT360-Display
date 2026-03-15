"""Utility functions for PCCooler GT360 display controller."""

import sys
from datetime import datetime
from typing import Optional, List, Tuple


def load_system_fonts(font_sizes: List[int]) -> List:
    """Load system fonts for different sizes.
    
    Args:
        font_sizes: List of font sizes to load
        
    Returns:
        List of ImageFont objects (one per size), or default fonts if loading fails
    """
    try:
        from PIL import ImageFont
    except ImportError:
        return [None] * len(font_sizes)
    
    fonts = []
    
    # Platform-specific font paths
    if sys.platform == 'darwin':
        font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/Library/Fonts/Arial.ttf",
        ]
    else:
        # Linux
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
    
    # Try to load fonts for each size
    for size in font_sizes:
        font = None
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, size)
                break
            except Exception:
                continue
        
        # Fallback to default font
        if font is None:
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
        
        fonts.append(font)
    
    return fonts


def generate_timestamp() -> str:
    """Generate a unique timestamp string for filenames.
    
    Format: YYYY-MM-DD_HH-MM-SS-mmm (milliseconds)
    """
    now = datetime.now()
    ms = int(now.microsecond / 1000)
    return now.strftime("%Y-%m-%d_%H-%M-%S-") + str(ms)


def format_bytes(size_bytes: int) -> str:
    """Format byte size to human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 KB", "2.3 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def encode_image(img, fmt: str, image_processor):
    """Encode an image to the specified format.
    
    Args:
        img: PIL Image object
        fmt: Format string ('jpeg', 'png', 'bmp', 'gif')
        image_processor: ImageProcessor class/instance
        
    Returns:
        Tuple of (encoded_bytes, extension_string)
        
    Raises:
        ValueError: If format is not supported
    """
    fmt_lower = fmt.lower()
    
    if fmt_lower == 'jpeg' or fmt_lower == 'jpg':
        return image_processor.create_jpeg(img.convert('RGB'), quality=90), 'jpg'
    elif fmt_lower == 'bmp':
        return image_processor.create_bmp(img.convert('RGB')), 'bmp'
    elif fmt_lower == 'gif':
        return image_processor.create_gif(img), 'gif'
    elif fmt_lower == 'png':
        return image_processor.create_png(img.convert('RGBA')), 'png'
    else:
        raise ValueError(f"Unsupported format: {fmt}")


def handle_control_commands(ctrl, wakeup: bool = False, sleep: bool = False, 
                           recovery: bool = False, timeout: Optional[int] = None,
                           init: bool = False, verbose: bool = False):
    """Handle control commands for the display.
    
    Args:
        ctrl: DisplayController instance
        wakeup: Whether to wakeup the display
        sleep: Whether to put the display to sleep
        recovery: Whether to enable recovery mode
        timeout: Timeout value in seconds (None to skip)
        init: Whether to run initialization sequence
        verbose: Whether to print verbose output
        
    Returns:
        True if all commands succeeded, False otherwise
    """
    import time
    success = True
    
    if wakeup:
        ok = ctrl.wakeup()
        if verbose:
            print("✅ Display wakeup sent" if ok else "❌ Wakeup failed")
        success = success and ok
        time.sleep(0.5)
    
    if sleep:
        ok = ctrl.sleep()
        if verbose:
            print("✅ Display sleep sent" if ok else "❌ Sleep failed")
        success = success and ok
        time.sleep(0.5)
    
    if recovery:
        ok = ctrl.recovery(enable=True)
        if verbose:
            print("✅ Recovery mode enabled" if ok else "❌ Recovery failed")
        success = success and ok
        time.sleep(0.5)
    
    if timeout is not None:
        ok = ctrl.set_timeout(timeout)
        if verbose:
            print(f"✅ Timeout set to {timeout}s" if ok else "❌ Timeout setting failed")
        success = success and ok
        time.sleep(0.3)
    
    if init:
        if verbose:
            print("🚀 Running initialization sequence...")
        ctrl.connect()
        time.sleep(0.3)
        ctrl.set_timeout(60)
        time.sleep(0.3)
        ctrl.recovery(enable=True)
        time.sleep(0.3)
        ctrl.wakeup()
        time.sleep(0.5)
        if verbose:
            print("✅ Initialization complete")
    
    return success


def send_mp4_file(ctrl, image_path: str, chunk_delay: float, 
                  verbose: bool = False) -> bool:
    """Send an MP4 file to the display.
    
    Args:
        ctrl: DisplayController instance
        image_path: Path to the MP4 file
        chunk_delay: Delay between chunks in seconds
        verbose: Whether to print verbose output
        
    Returns:
        True if successful, False otherwise
    """
    with open(image_path, 'rb') as f:
        mp4_data = f.read()
    
    filename = generate_timestamp() + ".mp4"
    
    if verbose:
        print(f"📁 Sending MP4: {len(mp4_data)} bytes ({filename})")
    
    success = ctrl.send_image(mp4_data, filename, chunk_delay=chunk_delay)
    
    if verbose:
        if success:
            print("✅ MP4 sent successfully!")
        else:
            print("❌ Failed to send MP4")
    
    return success
