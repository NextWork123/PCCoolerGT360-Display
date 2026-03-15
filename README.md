# PCCoolerGT360-Display

USB display controller for PCCooler GT360 AIO liquid cooler (3.5" IPS LCD). Send images, test patterns, system info, and control wake/sleep/recovery via USB CDC ACM serial.

## Features

- 🖼️ **Send Images & Videos** — Display custom images (PNG, JPEG, GIF, BMP) and videos (MP4)
- 🎨 **Test Patterns** — Built-in patterns: Blue, Red, Green, White, Black, Gradient, Grid, Colors
- 🖥️ **System Information** — Show real-time CPU/GPU stats on the display
- ✨ **Animated Screensavers** — Bounce, Mystify, Starfield, Pipes 3D, Cat + Pipes
- ⚡ **Device Control** — Wakeup, Sleep, Recovery, Init, Reset commands
- 🌓 **Modern UI** — Windows 11 Fluent Design with light/dark theme support

## Install

```bash
pip install -e .
```

Dependencies: `pyserial`, `Pillow`, `pywebview` (for GUI)

## USB Connection

This library uses **pyserial** to communicate with the device via CDC ACM (serial port). The device will appear as a serial port (`/dev/ttyACM0` on Linux, `COMx` on Windows).

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

## Library Usage

```python
from pccooler_gt360 import DisplayController, ImageProcessor, DISPLAY_WIDTH, DISPLAY_HEIGHT

with DisplayController(verbose=True) as ctrl:
    ctrl.open_device()
    ctrl.wakeup()
    img = ImageProcessor.create_test_pattern("blue")
    data = ImageProcessor.create_png(img)
    ctrl.send_image(data, "test.png")
```

## Testing

Test the connection:

```bash
python -c "from pccooler_gt360 import DisplayController; print('OK')"
```

List available serial ports:

```python
from serial.tools.list_ports import comports
for p in comports():
    print(f"{p.device}: {p.description} [{p.hwid}]")
```

## Credits
- [Shiberal](https://github.com/Shiberal) — For help with the library and UI.
