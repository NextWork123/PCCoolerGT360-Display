"""
Display controller class for PCCooler GT360.
"""

from . import protocol
from . import device
from . import power
from . import transfer
from . import display_settings
from .device import USB_AVAILABLE
from .image_processor import ImageProcessor, PIL_AVAILABLE


class DisplayController:
    """Main controller class for PCCooler GT360 display"""
    
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.device = None
        self.seq_number = 0
        
        if not USB_AVAILABLE:
            raise RuntimeError("pyserial is required. Install with: pip install pyserial")
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow is required. Install with: pip install Pillow")
    
    def _log(self, message, level="INFO"):
        """Log message if verbose mode is enabled"""
        protocol.log_message(message, level, self.verbose)
    
    def _get_next_seq(self) -> int:
        """Increment and return sequence number"""
        self.seq_number += 1
        return self.seq_number

    def send_command(self, verb: str, body_dict: dict, seq: int = None, desc: str = "", retries: int = 3) -> dict:
        """Send a command and return ACK, with automatic retries on failure"""
        if seq is None:
            seq = self._get_next_seq()
        return protocol.send_command(self.device, verb, body_dict, seq, verbose=self.verbose, desc=desc, retries=retries)
    
    def wakeup(self) -> bool:
        """Send wakeup/resume command"""
        return power.wakeup(self.device, self._get_next_seq(), verbose=self.verbose)
    
    def sleep(self) -> bool:
        """Send sleep/suspend command"""
        return power.sleep(self.device, self._get_next_seq(), verbose=self.verbose)
    
    def recovery(self, enable: bool = True) -> bool:
        """Send recovery command"""
        return power.recovery(self.device, self._get_next_seq(), enable=enable, verbose=self.verbose)
    
    def set_timeout(self, seconds: int = 60) -> bool:
        """Set display timeout in seconds (0 = disable timeout?)"""
        return power.set_timeout(self.device, self._get_next_seq(), seconds=seconds, verbose=self.verbose)

    def set_brightness(self, level: int) -> bool:
        """Set display brightness (0-100)."""
        return display_settings.set_brightness(
            self.device, self._get_next_seq(), level, self.verbose
        )

    def set_orientation(self, angle: int) -> bool:
        """Set display orientation (0, 90, 180, 270)."""
        return display_settings.set_orientation(
            self.device, self._get_next_seq(), angle, self.verbose
        )

    def probe_orientation(self) -> dict:
        """Probe device to find correct orientation protocol."""
        return display_settings.probe_orientation_protocol(
            self.device, self._get_next_seq(), self.verbose
        )

    def connect(self) -> bool:
        """Send initial connection command"""
        return device.connect(self.device, self._get_next_seq(), verbose=self.verbose)
    
    def reset_usb_device(self):
        """Reset USB device via pyusb"""
        return device.reset_usb_device(verbose=self.verbose)
    
    def open_device(self, max_retries=10):
        """Open and initialize USB device"""
        self.device = device.open_device(max_retries=max_retries, verbose=self.verbose)
        self.seq_number = 0
        return self.device
    
    def close(self):
        """Close device and cleanup"""
        if self.device:
            device.close_device(self.device, verbose=self.verbose)
            self.device = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def send_image(self, image_data: bytes, filename: str = "image.bmp",
                   chunk_delay: float = 0.001, fast_mode: bool = False,
                   chunk_size: int = 0, compress: bool = False) -> bool:
        """Send raw image data to display.

        chunk_size: bytes per USB write (0 = device blockMaxSize).  Use a
          smaller value (e.g. 256) instead of chunk_delay > 0 to pace the MCU.
        fast_mode: skip EP_IN flush on success, tighter timeouts, no retries (screensavers).
        compress: zlib-compress payload before sending (smaller USB; device must support it).
        """
        return transfer.send_image(
            self.device, image_data, self._get_next_seq,
            verbose=self.verbose, filename=filename,
            chunk_delay=chunk_delay, fast_mode=fast_mode,
            chunk_size=chunk_size, compress=compress,
        )
