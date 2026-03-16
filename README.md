# PCCoolerGT360-Display

USB display controller for PCCooler GT360 AIO liquid cooler (3.5" IPS LCD). Send images, test patterns, system info, and control wake/sleep/recovery via USB CDC ACM serial.

## Features

- 🖼️ **Send Images & Videos** — Display custom images (PNG, JPEG, GIF, BMP) and videos (MP4)
- 🎬 **GIF to MP4 Conversion** — Animated GIFs are automatically converted to H.264 MP4 for playback
- 🎨 **Test Patterns** — Built-in patterns: Blue, Red, Green, White, Black, Gradient, Grid, Colors
- 🖥️ **System Information** — Show real-time CPU/GPU stats on the display
- ✨ **Animated Screensavers** — Bounce, Mystify, Starfield, Pipes 3D, Cat + Pipes
- ⚡ **Device Control** — Wakeup, Sleep, Recovery, Init, Reset commands
- 🌓 **Modern UI** — Windows 11 Fluent Design with light/dark theme support
- 🚀 **Async Support** — Native asyncio support for non-blocking operations

## Install

**Requirements:** Python 3.10+

```bash
pip install -e .
```

Dependencies: `wireio` (modern serial library), `Pillow`, `pywebview` (for GUI)

### Optional: FFmpeg for GIF Conversion

To enable automatic conversion of animated GIFs to MP4 videos, install FFmpeg:

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**Arch:**
```bash
pacman -S ffmpeg
```

**Verification:**
```bash
ffmpeg -version
```

## USB Connection

This library uses **wireio** (modern replacement for pyserial) to communicate with the device via CDC ACM (serial port). The device will appear as a serial port (`/dev/ttyACM0` on Linux, `COMx` on Windows).

```python
from pccooler_gt360 import DisplayController

with DisplayController(verbose=True) as ctrl:
    ctrl.open_device()  # Auto-detects port by VID/PID
    ctrl.wakeup()
```

**Features:**
- Auto-detects serial port by USB VID/PID
- Standard serial port interface
- Works on Linux, Windows, and macOS
- Native async support via `AsyncDisplayController`

## Async API (New)

For non-blocking operations, use `AsyncDisplayController`:

```python
import asyncio
from pccooler_gt360 import AsyncDisplayController, ImageProcessor

async def main():
    async with AsyncDisplayController(verbose=True) as ctrl:
        await ctrl.open_device()
        await ctrl.wakeup()
        
        img = ImageProcessor.create_test_pattern("blue")
        data = ImageProcessor.create_png(img)
        
        # Non-blocking send - can cancel mid-transfer
        await ctrl.send_image(data, "test.png")

asyncio.run(main())
```

### Async Features

- **Non-blocking operations** — UI remains responsive during transfers
- **Cancellation support** — Cancel long transfers gracefully
- **Concurrent operations** — Monitor device while sending images
- **Better performance** — No polling loops, efficient async I/O

```python
async def send_with_cancellation(ctrl):
    cancellation_event = asyncio.Event()
    
    # Start transfer
    task = asyncio.create_task(
        ctrl.send_image(large_data, "big.png", cancellation_event=cancellation_event)
    )
    
    # Cancel after 5 seconds if not complete
    await asyncio.sleep(5)
    if not task.done():
        cancellation_event.set()
    
    return await task
```

## GUI Application

Launch the modern Windows 11-style interface:

```bash
python ui.py
```

### GUI Features

- **Segmented Source Selection** — Quickly switch between Image, Pattern, System Info, or Screensaver
- **Visual Pattern Grid** — Click-to-select pattern with live preview
- **Theme Support** — Toggle between light and dark modes ( persists preference)
- **InfoBar Notifications** — Non-intrusive status messages with success/error states
- **Quick Actions** — One-click device control buttons
- **Keyboard Shortcuts:**
  - `Ctrl+Enter` — Send to display
  - `Ctrl+.` — Stop operation

### UI Components

| Component | Description |
|-----------|-------------|
| Segmented Control | Tab-like interface for source selection |
| Pattern Grid | Visual selection of 8 built-in patterns |
| Toggle Switches | Windows 11 style on/off toggles |
| Sliders | Quality, scale, and delay adjustments |
| InfoBar | Status feedback with icons and colors |
| Status Bar | Connection state and app info |

## CLI

After install, run:

```bash
pccooler-gt360 --pattern blue --wakeup
pccooler-gt360 --image photo.png
pccooler-gt360 --system
pccooler-gt360 --help
```

## GIF to MP4 Conversion

Animated GIFs are automatically converted to H.264-encoded MP4 videos when FFmpeg is installed. This allows smooth playback of animated content on the display.

### How it works

- **Automatic detection**: The system detects if a GIF has multiple frames
- **FFmpeg conversion**: Converts to H.264 MP4 with optimized settings (baseline profile, yuv420p)
- **Graceful fallback**: If FFmpeg is not available, the first frame is displayed as a static image

### Usage Examples

**CLI with GIF:**
```bash
# Automatically converts animated GIF to MP4
pccooler-gt360 --image animation.gif
```

**Library usage:**
```python
from pccooler_gt360 import DisplayController, ImageProcessor

with DisplayController() as ctrl:
    ctrl.open_device()
    ctrl.wakeup()
    
    # Check if GIF is animated
    if ImageProcessor.is_gif_animated("animation.gif"):
        # Convert to MP4
        mp4_data = ImageProcessor.convert_gif_to_mp4("animation.gif")
        ctrl.send_image(mp4_data, "animation.mp4")
    else:
        # Handle as static image
        img = ImageProcessor.load_image("animation.gif")
        ctrl.send_image(ImageProcessor.create_png(img), "frame.png")
```

### Limitations

- **Duration**: GIFs longer than 60 seconds may take significant time to convert
- **Transparency**: Converted to black background (H.264 limitation)
- **Resolution**: Upscaling low-res GIFs may look pixelated
- **FFmpeg required**: Conversion only works if FFmpeg is installed

## Library Usage

### Synchronous API

```python
from pccooler_gt360 import DisplayController, ImageProcessor, DISPLAY_WIDTH, DISPLAY_HEIGHT

with DisplayController(verbose=True) as ctrl:
    ctrl.open_device()
    ctrl.wakeup()
    img = ImageProcessor.create_test_pattern("blue")
    data = ImageProcessor.create_png(img)
    ctrl.send_image(data, "test.png")
```

### Asynchronous API

```python
import asyncio
from pccooler_gt360 import AsyncDisplayController, ImageProcessor

async def display_system_info():
    async with AsyncDisplayController(verbose=True) as ctrl:
        await ctrl.open_device()
        await ctrl.wakeup()
        
        # Create and send image
        img = ImageProcessor.create_system_info(DISPLAY_WIDTH, DISPLAY_HEIGHT)
        data = ImageProcessor.create_png(img)
        await ctrl.send_image(data, "system.png")

asyncio.run(display_system_info())
```

## Testing

Test the connection:

```bash
python -c "from pccooler_gt360 import DisplayController; print('OK')"
```

List available serial ports:

```python
from wireio import list_ports

for port in list_ports():
    print(f"{port.device}: {port.description} [{port.hwid}]")
```

## Migration from pyserial

This project now uses **wireio** instead of pyserial. WireIO provides:

- Built-in async support with `AsyncSerial`
- Full type hints (PEP 561)
- Modern Python 3.10+ features
- Drop-in replacement for pyserial

The `DisplayController` API remains unchanged — existing code continues to work.

## Credits
- [Shiberal](https://github.com/Shiberal) — For help with the library and UI.
