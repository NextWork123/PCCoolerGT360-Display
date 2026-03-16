"""
PCCooler GT360 - USB display controller for PCCooler GT360 AIO liquid cooler.

Usage as a library (synchronous):

    from pccooler_gt360 import DisplayController, ImageProcessor
    from pccooler_gt360 import DISPLAY_WIDTH, DISPLAY_HEIGHT, DISPLAY_MODES

    with DisplayController(verbose=True) as ctrl:
        ctrl.open_device()
        ctrl.wakeup()
        img = ImageProcessor.create_test_pattern("blue")
        data = ImageProcessor.create_png(img)
        ctrl.send_image(data, "test.png")

Usage as a library (asynchronous):

    import asyncio
    from pccooler_gt360 import AsyncDisplayController, ImageProcessor

    async def main():
        async with AsyncDisplayController(verbose=True) as ctrl:
            await ctrl.open_device()
            await ctrl.wakeup()
            img = ImageProcessor.create_test_pattern("blue")
            data = ImageProcessor.create_png(img)
            await ctrl.send_image(data, "test.png")

    asyncio.run(main())
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Lightweight constants - safe to import immediately
from .constants import (
    VENDOR_ID,
    PRODUCT_ID,
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    DISPLAY_MODES,
    PACKET_START,
    PACKET_END,
)

# Lazy import machinery for heavy modules
_module_cache: dict = {}


def __getattr__(name: str):
    """Lazy import heavy modules on first access."""
    if name in _module_cache:
        return _module_cache[name]

    if name == "DisplayController":
        from .controller import DisplayController
        _module_cache[name] = DisplayController
        return DisplayController

    if name == "AsyncDisplayController":
        from .controller import AsyncDisplayController
        _module_cache[name] = AsyncDisplayController
        return AsyncDisplayController

    if name == "ImageProcessor":
        from .image_processor import ImageProcessor
        _module_cache[name] = ImageProcessor
        return ImageProcessor

    if name == "ScreensaverGenerator":
        from .image_processor import ScreensaverGenerator
        _module_cache[name] = ScreensaverGenerator
        return ScreensaverGenerator

    if name == "BUILTIN_IMAGE_B64":
        from .image_processor import BUILTIN_IMAGE_B64
        _module_cache[name] = BUILTIN_IMAGE_B64
        return BUILTIN_IMAGE_B64

    if name == "PIL_AVAILABLE":
        from .image_processor import PIL_AVAILABLE
        _module_cache[name] = PIL_AVAILABLE
        return PIL_AVAILABLE

    if name in ("set_brightness", "set_orientation", "probe_orientation_protocol"):
        from . import display_settings
        func = getattr(display_settings, name)
        _module_cache[name] = func
        return func

    if name == "Config":
        from .config import Config
        _module_cache[name] = Config
        return Config

    if name == "setup_logging":
        from .logger import setup_logging
        _module_cache[name] = setup_logging
        return setup_logging

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Classes (lazy loaded)
    "DisplayController",
    "AsyncDisplayController",
    "ImageProcessor",
    "ScreensaverGenerator",
    "Config",
    # Constants (immediate)
    "VENDOR_ID",
    "PRODUCT_ID",
    "DISPLAY_WIDTH",
    "DISPLAY_HEIGHT",
    "DISPLAY_MODES",
    "PACKET_START",
    "PACKET_END",
    # Data
    "BUILTIN_IMAGE_B64",
    "PIL_AVAILABLE",
    # Functions (lazy loaded)
    "set_brightness",
    "set_orientation",
    "probe_orientation_protocol",
    "setup_logging",
]
__version__ = "0.1.0"
