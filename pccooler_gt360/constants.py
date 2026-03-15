"""
Constants and shared configuration for PCCooler GT360 display controller.
"""

# Device Configuration
VENDOR_ID = 0x1d6b
PRODUCT_ID = 0x011e

# Display Specifications (PCCooler GT360: 3.5" IPS LCD 640x480@60Hz)
DISPLAY_WIDTH = 640
DISPLAY_HEIGHT = 480
DISPLAY_MODES = {
    '640x480': (640, 480),
    '480x320': (480, 320),
}

# Protocol Constants
PACKET_START = 0x5A
PACKET_END = 0x5A
