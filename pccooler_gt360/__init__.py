"""
PCCooler GT360 - USB display controller for PCCooler GT360 AIO liquid cooler.

Usage as a library:

    from pccooler_gt360 import DisplayController, ImageProcessor
    from pccooler_gt360 import DISPLAY_WIDTH, DISPLAY_HEIGHT, DISPLAY_MODES

    with DisplayController(verbose=True) as ctrl:
        ctrl.open_device()
        ctrl.wakeup()
        img = ImageProcessor.create_test_pattern("blue")
        data = ImageProcessor.create_png(img)
        ctrl.send_image(data, "test.png")
"""

from .controller import DisplayController
from .image_processor import ImageProcessor, ScreensaverGenerator, BUILTIN_IMAGE_B64, PIL_AVAILABLE
from .display_settings import set_brightness, set_orientation, probe_orientation_protocol
from .constants import (
    VENDOR_ID,
    PRODUCT_ID,
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    DISPLAY_MODES,
    PACKET_START,
    PACKET_END,
)

__all__ = [
    "DisplayController",
    "ImageProcessor",
    "ScreensaverGenerator",
    "BUILTIN_IMAGE_B64",
    "PIL_AVAILABLE",
    "set_brightness",
    "set_orientation",
    "probe_orientation_protocol",
    "VENDOR_ID",
    "PRODUCT_ID",
    "DISPLAY_WIDTH",
    "DISPLAY_HEIGHT",
    "DISPLAY_MODES",
    "PACKET_START",
    "PACKET_END",
]
__version__ = "0.1.0"
