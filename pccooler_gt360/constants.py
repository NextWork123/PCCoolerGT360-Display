"""
Constants and shared configuration for PCCooler GT360 display controller.
"""

from typing import Optional

# Device Configuration
VENDOR_ID = 0x1d6b
PRODUCT_ID = 0x011e  # PCCooler GT360 (kept for backward compatibility)

# Known PCCooler display models sharing the same CDC ACM protocol, keyed by USB PID.
DEVICE_MODELS = {
    0x011e: {"name": "GT360", "resolution": "640x480"},  # 3.5" IPS 640x480
    0x0112: {"name": "DC360", "resolution": "240x320"},  # 2.4" IPS 240x320 (portrait)
}
PRODUCT_IDS = tuple(DEVICE_MODELS)

# Display Specifications (PCCooler GT360: 3.5" IPS LCD 640x480@60Hz)
DISPLAY_WIDTH = 640
DISPLAY_HEIGHT = 480
DISPLAY_MODES = {
    '640x480': (640, 480),
    '480x320': (480, 320),
    '240x320': (240, 320),
}
DEFAULT_RESOLUTION = '640x480'
# Special resolution value: pick the resolution of the detected model.
AUTO_RESOLUTION = 'auto'
RESOLUTION_CHOICES = [AUTO_RESOLUTION, *DISPLAY_MODES]


def model_for_ids(vid: Optional[int], pid: Optional[int]) -> Optional[dict]:
    """Return the known model info for a VID/PID pair, or None."""
    if vid != VENDOR_ID:
        return None
    return DEVICE_MODELS.get(pid)

# Protocol Constants
PACKET_START = 0x5A
PACKET_END = 0x5A
