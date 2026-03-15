"""
Serial device management for PCCooler GT360 display (CDC ACM).
"""

import time
import sys
import subprocess

from .constants import VENDOR_ID, PRODUCT_ID
from .protocol import log_message, send_command

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# Kept for backward compatibility with cli.py and controller.py
USB_AVAILABLE = SERIAL_AVAILABLE


class SerialDevice:
    """Wrapper so protocol/transfer code can use read(size, timeout=ms) and write(data, timeout=ms)."""

    def __init__(self, ser):
        self._ser = ser

    def read(self, size, timeout=None):
        """Read up to size bytes. timeout in milliseconds. Returns b'' on timeout (no exception)."""
        if timeout is not None:
            ms = max(timeout, 10)  # pyserial treats 0 as non-blocking; floor at 10ms
            self._ser.timeout = ms / 1000.0
        res = self._ser.read(size)
        # Debug: log every read
        # log_message(f"serial.read({size}, timeout={timeout}ms) -> got {len(res)}B", "DEBUG", True)
        return res

    def write(self, data, timeout=None):
        """Write data. timeout in milliseconds."""
        if timeout is not None:
            self._ser.write_timeout = timeout / 1000.0
        # Debug: log every write
        # log_message(f"serial.write({len(data)}B, write_timeout={timeout}ms)", "DEBUG", True)
        self._ser.write(bytes(data))


def _find_serial_port(verbose=False):
    """Return first serial port matching VID/PID, or None."""
    if verbose:
        log_message("Scanning available serial ports...", "DEBUG", verbose)
    
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if verbose:
            vid_str = f"{port.vid:04x}" if port.vid is not None else "None"
            pid_str = f"{port.pid:04x}" if port.pid is not None else "None"
            log_message(f"Checking port: {port.device} (VID={vid_str}, PID={pid_str}, HWID={port.hwid})", "DEBUG", verbose)
        
        # Exact match
        if port.vid == VENDOR_ID and port.pid == PRODUCT_ID:
            return port
            
        # Linux Foundation VID (1d6b) often used for generic/simulated devices
        # If the user is seeing the device in lsusb but not here, we might need to match by HWID string
        if port.hwid and f"{VENDOR_ID:04x}:{PRODUCT_ID:04x}" in port.hwid.lower():
            return port
            
    return None


def reset_usb_device(verbose=False):
    """Reset device by closing and reopening (pyserial has no USB-level reset)."""
    try:
        port_info = _find_serial_port(verbose=verbose)
        if port_info is not None:
            port = port_info.device
            log_message(f"Resetting device {port} (close/reopen)...", "INFO", verbose)
            try:
                ser = serial.Serial(port, baudrate=115200)
                ser.close()
                time.sleep(0.5)
            except Exception:
                pass
            time.sleep(2)
            log_message("Device reset complete", "INFO", verbose)
            return True
        log_message("Device not found for reset", "WARN", verbose)
    except Exception as e:
        log_message(f"Reset failed: {e}", "WARN", verbose)
    return False


def open_device(max_retries=10, verbose=False):
    """Open and initialize serial device (CDC ACM at 115200)."""
    log_message("Searching for device...", "INFO", verbose)

    port_info = None
    for attempt in range(max_retries):
        port_info = _find_serial_port(verbose=verbose)
        if port_info is not None:
            break
        log_message(f"Waiting for device... ({attempt+1}/{max_retries})", "WARN", verbose)
        time.sleep(0.5)
    else:
        raise RuntimeError(f"Device not found (VID={VENDOR_ID:04x}, PID={PRODUCT_ID:04x})")

    port = port_info.device
    log_message(f"Found device: {port} ({port_info.description})", "INFO", verbose)

    ser = serial.Serial(
        port=port,
        baudrate=115200,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.2,
        write_timeout=5.0,
    )
    log_message("Serial opened: baudrate=115200 timeout=0.2", "DEBUG", verbose)

    # Some devices reset on DTR assertion. For GT360, we should keep them False.
    try:
        ser.dtr = False
        ser.rts = False
        log_message("DTR/RTS set to False to prevent MCU reset", "DEBUG", verbose)
        time.sleep(0.2)
    except Exception as e:
        log_message(f"Failed to set DTR/RTS: {e}", "WARN", verbose)

    # Flush input buffer
    ser.reset_input_buffer()
    log_message("Input buffer flushed", "DEBUG", verbose)
    time.sleep(0.1)

    wrapper = SerialDevice(ser)
    return wrapper


def close_device(device, verbose=False):
    """Close device and cleanup."""
    if device and hasattr(device, "_ser"):
        try:
            device._ser.close()
        except Exception:
            pass
        if sys.platform == "linux":
            subprocess.run(["modprobe", "cdc_acm"], capture_output=True)
        log_message("Device closed", "INFO", verbose)


def connect(device, seq: int, verbose: bool = False) -> bool:
    """Send initial connection command"""
    log_message("Sending CONN command...", "INFO", verbose)
    ack = send_command(device, "POST conn", {}, seq, verbose=verbose, desc="CONN")
    return ack.get("state") == "success"
