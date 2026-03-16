"""
Display controller classes for PCCooler GT360.
Supports both synchronous and asynchronous operations.
"""

from __future__ import annotations

import asyncio
from typing import Optional, Callable

from . import protocol
from . import device
from . import power
from . import transfer
from . import display_settings
from .device import WIREIO_AVAILABLE, AsyncSerialDevice, SerialDevice
from .image_processor import ImageProcessor, PIL_AVAILABLE


class AsyncDisplayController:
    """Asynchronous display controller for PCCooler GT360.
    
    Provides non-blocking operations for all display commands.
    Use this for GUI applications or when you need concurrent operations.
    """

    def __init__(self, verbose: bool = False) -> None:
        self.verbose: bool = verbose
        self.device: Optional[AsyncSerialDevice] = None
        self.seq_number: int = 0
        self._lock = asyncio.Lock()  # Prevent concurrent command interleaving

        if not WIREIO_AVAILABLE:
            raise RuntimeError("wireio is required. Install with: pip install wireio")
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow is required. Install with: pip install Pillow")

    def _log(self, message: str, level: str = "INFO") -> None:
        """Log message if verbose mode is enabled."""
        protocol.log_message(message, level, self.verbose)

    def _get_next_seq(self) -> int:
        """Increment and return sequence number."""
        self.seq_number += 1
        return self.seq_number

    async def open_device(self, max_retries: int = 10) -> AsyncSerialDevice:
        """Open and initialize USB device asynchronously."""
        self.device = await device.open_device_async(
            max_retries=max_retries, verbose=self.verbose
        )
        self.seq_number = 0
        return self.device

    async def close(self) -> None:
        """Close device and cleanup asynchronously."""
        if self.device:
            await device.close_device_async(self.device, verbose=self.verbose)
            self.device = None

    async def send_command(self, verb: str, body_dict: dict, seq: Optional[int] = None) -> dict:
        """Send a command and return ACK asynchronously (thread-safe)."""
        async with self._lock:
            if seq is None:
                seq = self._get_next_seq()
            return await protocol.send_command_async(
                self.device, verb, body_dict, seq, verbose=self.verbose
            )

    async def wakeup(self) -> bool:
        """Send wakeup/resume command asynchronously."""
        async with self._lock:
            self.seq_number += 1
            return await power.wakeup_async(self.device, self.seq_number, verbose=self.verbose)

    async def sleep(self) -> bool:
        """Send sleep/suspend command asynchronously."""
        async with self._lock:
            self.seq_number += 1
            return await power.sleep_async(self.device, self.seq_number, verbose=self.verbose)

    async def recovery(self, enable: bool = True) -> bool:
        """Send recovery command asynchronously."""
        async with self._lock:
            self.seq_number += 1
            return await power.recovery_async(self.device, self.seq_number, enable=enable, verbose=self.verbose)

    async def set_timeout(self, seconds: int = 60) -> bool:
        """Set display timeout in seconds asynchronously."""
        async with self._lock:
            self.seq_number += 1
            return await power.set_timeout_async(self.device, self.seq_number, seconds=seconds, verbose=self.verbose)

    async def set_brightness(self, level: int) -> bool:
        """Set display brightness (0-100) asynchronously."""
        async with self._lock:
            self.seq_number += 1
            return await display_settings.set_brightness_async(
                self.device, self.seq_number, level, self.verbose
            )

    async def set_orientation(self, angle: int) -> bool:
        """Set display orientation (0, 90, 180, 270) asynchronously."""
        async with self._lock:
            self.seq_number += 1
            return await display_settings.set_orientation_async(
                self.device, self.seq_number, angle, self.verbose
            )

    async def probe_orientation(self) -> dict:
        """Probe device to find correct orientation protocol asynchronously."""
        async with self._lock:
            self.seq_number += 1
            return await display_settings.probe_orientation_protocol_async(
                self.device, self.seq_number, self.verbose
            )

    async def connect(self) -> bool:
        """Send initial connection command asynchronously."""
        async with self._lock:
            self.seq_number += 1
            return await device.connect_async(self.device, self.seq_number, verbose=self.verbose)

    async def reset_usb_device(self) -> bool:
        """Reset USB device via wireio (runs in executor)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, device.reset_usb_device, self.verbose
        )

    async def send_image(
        self,
        image_data: bytes,
        filename: str = "image.bmp",
        chunk_delay: float = 0.001,
        fast_mode: bool = False,
        chunk_size: int = 0,
        compress: bool = False,
        compress_level: int = 6,
        adaptive: bool = True,
        cancellation_event: Optional[asyncio.Event] = None
    ) -> bool:
        """Send raw image data to display asynchronously.

        Args:
            image_data: Raw bytes to send
            filename: Filename to report to device
            chunk_delay: Delay between chunks in seconds
            fast_mode: Skip EP_IN flush on success, tighter timeouts
            chunk_size: Bytes per USB write (0 = device blockMaxSize)
            compress: Zlib-compress payload before sending
            compress_level: Zlib compression level (1-9)
            adaptive: Dynamically adjust chunk size
            cancellation_event: Optional event to cancel transfer

        Returns:
            True if transfer succeeded
        """
        async with self._lock:
            return await transfer.send_image_async(
                self.device, image_data, self._get_next_seq,
                verbose=self.verbose, filename=filename,
                chunk_delay=chunk_delay, fast_mode=fast_mode,
                chunk_size=chunk_size, compress=compress,
                compress_level=compress_level, adaptive=adaptive,
                cancellation_event=cancellation_event
            )

    async def __aenter__(self) -> AsyncDisplayController:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Optional[type], exc_val: Optional[BaseException],
                        exc_tb: Optional[object]) -> bool:
        """Async context manager exit."""
        await self.close()
        return False


class DisplayController:
    """Synchronous display controller for PCCooler GT360.
    
    This is a backward-compatible wrapper around AsyncDisplayController.
    All operations run the async versions in an event loop.
    """

    def __init__(self, verbose: bool = False) -> None:
        self._async_ctrl = AsyncDisplayController(verbose=verbose)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def verbose(self) -> bool:
        """Get verbose mode setting."""
        return self._async_ctrl.verbose

    @verbose.setter
    def verbose(self, value: bool) -> None:
        """Set verbose mode."""
        self._async_ctrl.verbose = value

    @property
    def device(self) -> Optional[SerialDevice]:
        """Get device (returns sync wrapper)."""
        # The async device is AsyncSerialDevice, we return it as-is
        # since caller expects the device interface
        return self._async_ctrl.device

    def _run_sync(self, coro) -> any:
        """Run a coroutine synchronously."""
        try:
            # Check if there's already a running loop
            loop = asyncio.get_running_loop()
            # We're in an async context - this shouldn't happen in normal usage
            # but if it does, we need to schedule it properly
            raise RuntimeError(
                "Cannot run sync controller from within an async context. "
                "Use AsyncDisplayController instead."
            )
        except RuntimeError as e:
            if "no running event loop" in str(e):
                # No running loop - safe to use asyncio.run
                return asyncio.run(coro)
            raise

    def open_device(self, max_retries: int = 10) -> Optional[SerialDevice]:
        """Open and initialize USB device."""
        return self._run_sync(self._async_ctrl.open_device(max_retries=max_retries))

    def close(self) -> None:
        """Close device and cleanup."""
        self._run_sync(self._async_ctrl.close())

    def send_command(self, verb: str, body_dict: dict, seq: Optional[int] = None,
                     desc: str = "", retries: int = 3) -> dict:
        """Send a command and return ACK."""
        if seq is None:
            seq = self._async_ctrl._get_next_seq()
        return self._run_sync(self._async_ctrl.send_command(verb, body_dict, seq))

    def wakeup(self) -> bool:
        """Send wakeup/resume command."""
        return self._run_sync(self._async_ctrl.wakeup())

    def sleep(self) -> bool:
        """Send sleep/suspend command."""
        return self._run_sync(self._async_ctrl.sleep())

    def recovery(self, enable: bool = True) -> bool:
        """Send recovery command."""
        return self._run_sync(self._async_ctrl.recovery(enable=enable))

    def set_timeout(self, seconds: int = 60) -> bool:
        """Set display timeout in seconds."""
        return self._run_sync(self._async_ctrl.set_timeout(seconds=seconds))

    def set_brightness(self, level: int) -> bool:
        """Set display brightness (0-100)."""
        return self._run_sync(self._async_ctrl.set_brightness(level))

    def set_orientation(self, angle: int) -> bool:
        """Set display orientation (0, 90, 180, 270)."""
        return self._run_sync(self._async_ctrl.set_orientation(angle))

    def probe_orientation(self) -> dict:
        """Probe device to find correct orientation protocol."""
        return self._run_sync(self._async_ctrl.probe_orientation())

    def connect(self) -> bool:
        """Send initial connection command."""
        return self._run_sync(self._async_ctrl.connect())

    def reset_usb_device(self) -> bool:
        """Reset USB device."""
        return self._run_sync(self._async_ctrl.reset_usb_device())

    def send_image(
        self,
        image_data: bytes,
        filename: str = "image.bmp",
        chunk_delay: float = 0.001,
        fast_mode: bool = False,
        chunk_size: int = 0,
        compress: bool = False,
        compress_level: int = 6,
        adaptive: bool = True
    ) -> bool:
        """Send raw image data to display."""
        return self._run_sync(self._async_ctrl.send_image(
            image_data, filename=filename,
            chunk_delay=chunk_delay, fast_mode=fast_mode,
            chunk_size=chunk_size, compress=compress,
            compress_level=compress_level, adaptive=adaptive
        ))

    def __enter__(self) -> DisplayController:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Optional[type], exc_val: Optional[BaseException],
                 exc_tb: Optional[object]) -> bool:
        """Context manager exit."""
        self.close()
        return False
