"""
Serial device management for PCCooler GT360 display (CDC ACM).
Supports both synchronous and asynchronous operations via wireio.
"""

from __future__ import annotations

import asyncio
import os
import sys
import subprocess
import time
from typing import Optional, Union

from .constants import (
    VENDOR_ID, PRODUCT_IDS, DEFAULT_RESOLUTION, AUTO_RESOLUTION, model_for_ids,
)
from .protocol import log_message

try:
    from wireio import Serial, AsyncSerial, list_ports, SerialError
    WIREIO_AVAILABLE = True
except ImportError:
    WIREIO_AVAILABLE = False

# Backward compatibility alias
USB_AVAILABLE = WIREIO_AVAILABLE
SERIAL_AVAILABLE = WIREIO_AVAILABLE


class SerialDevice:
    """Synchronous wrapper for wireio Serial."""

    def __init__(self, ser: Serial) -> None:
        self._ser = ser

    def read(self, size: int, timeout: Optional[int] = None) -> bytes:
        """Read up to size bytes. timeout in milliseconds. Returns b'' on timeout."""
        if timeout is not None:
            ms = max(timeout, 10)
            self._ser.timeout = ms / 1000.0
        return self._ser.read(size)

    def write(self, data: bytes, timeout: Optional[int] = None) -> None:
        """Write data. timeout in milliseconds."""
        if timeout is not None:
            self._ser.write_timeout = timeout / 1000.0
        self._ser.write(bytes(data))


class AsyncSerialDevice:
    """Asynchronous wrapper for wireio AsyncSerial."""

    def __init__(self, ser: AsyncSerial) -> None:
        self._ser = ser

    async def read(self, size: int, timeout: Optional[int] = None) -> bytes:
        """Async read up to size bytes. timeout in milliseconds."""
        if timeout is not None:
            self._ser.timeout = timeout / 1000.0
        return await self._ser.read(size)

    async def write(self, data: bytes, timeout: Optional[int] = None) -> None:
        """Async write data. timeout in milliseconds."""
        if timeout is not None:
            self._ser.write_timeout = timeout / 1000.0
        await self._ser.write(bytes(data))

    async def close(self) -> None:
        """Async close the serial port."""
        await self._ser.close()


# Type alias for device handle
DeviceType = Union[SerialDevice, AsyncSerialDevice]


def _sysfs_usb_ids(device: str) -> tuple[Optional[int], Optional[int]]:
    """Read USB VID/PID of a tty from sysfs (Linux). wireio does not report them there."""
    if not sys.platform.startswith("linux") or not device:
        return None, None
    path = os.path.realpath(f"/sys/class/tty/{os.path.basename(device)}/device")
    # Walk up from the USB interface to the USB device node holding idVendor/idProduct
    while path.startswith("/sys/") and path != "/sys":
        try:
            with open(os.path.join(path, "idVendor")) as f:
                vid = int(f.read().strip(), 16)
            with open(os.path.join(path, "idProduct")) as f:
                pid = int(f.read().strip(), 16)
            return vid, pid
        except (OSError, ValueError):
            path = os.path.dirname(path)
    return None, None


def _port_ids(port) -> tuple[Optional[int], Optional[int]]:
    """Return (vid, pid) for a port, falling back to sysfs when not reported."""
    if port.vid is not None and port.pid is not None:
        return port.vid, port.pid
    return _sysfs_usb_ids(port.device)


def _is_known_device(port) -> bool:
    vid, pid = _port_ids(port)
    if vid == VENDOR_ID and pid in PRODUCT_IDS:
        return True
    hwid = (port.hwid or "").lower()
    return any(f"{VENDOR_ID:04x}:{p:04x}" in hwid for p in PRODUCT_IDS)


def _is_fallback_device(port) -> bool:
    """CDC ACM ports that might be the display when VID/PID can't be determined."""
    if port.description and "cdc_acm" in port.description.lower():
        return True
    return bool(port.device and "/dev/ttyACM" in port.device)


def _select_port(ports, verbose: bool = False) -> Optional[object]:
    """Pick the display port: known VID/PID first, then generic CDC ACM fallback."""
    for port in ports:
        if verbose:
            vid, pid = _port_ids(port)
            vid_str = f"{vid:04x}" if vid is not None else "None"
            pid_str = f"{pid:04x}" if pid is not None else "None"
            log_message(
                f"Checking port: {port.device} (VID={vid_str}, PID={pid_str}, HWID={port.hwid})",
                "DEBUG", verbose
            )
        if _is_known_device(port):
            return port

    for port in ports:
        if _is_fallback_device(port):
            if verbose:
                log_message(f"Found CDC ACM device by fallback: {port.device}", "DEBUG", verbose)
            return port

    return None


def _find_serial_port(verbose: bool = False) -> Optional[object]:
    """Return first serial port matching a known VID/PID, or None."""
    if verbose:
        log_message("Scanning available serial ports...", "DEBUG", verbose)
    return _select_port(list_ports(), verbose=verbose)


async def find_serial_port_async(verbose: bool = False) -> Optional[object]:
    """Async port discovery - runs list_ports in executor."""
    if verbose:
        log_message("Scanning available serial ports (async)...", "DEBUG", verbose)

    loop = asyncio.get_event_loop()
    ports = await loop.run_in_executor(None, list_ports)
    return _select_port(ports, verbose=verbose)


def detect_model(verbose: bool = False) -> Optional[dict]:
    """Return info of the connected display model (name, resolution, pid), or None."""
    port = _find_serial_port(verbose=verbose)
    if port is None:
        return None
    vid, pid = _port_ids(port)
    model = model_for_ids(vid, pid)
    if model is None:
        return None
    return {**model, "pid": pid, "port": port.device}


def resolve_resolution(resolution: Optional[str] = AUTO_RESOLUTION, verbose: bool = False) -> str:
    """Resolve 'auto' (or None) to the detected model's resolution."""
    if resolution and resolution != AUTO_RESOLUTION:
        return resolution
    try:
        model = detect_model(verbose=verbose)
    except Exception as e:
        log_message(f"Model detection failed: {e}", "WARN", verbose)
        model = None
    if model:
        log_message(f"Detected PCCooler {model['name']} -> {model['resolution']}", "INFO", verbose)
        return model["resolution"]
    log_message(f"Unknown model, using default resolution {DEFAULT_RESOLUTION}", "WARN", verbose)
    return DEFAULT_RESOLUTION


def reset_usb_device(verbose: bool = False) -> bool:
    """Reset device by closing and reopening."""
    try:
        port_info = _find_serial_port(verbose=verbose)
        if port_info is not None:
            port = port_info.device
            log_message(f"Resetting device {port} (close/reopen)...", "INFO", verbose)
            try:
                ser = Serial(port, baudrate=115200)
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


def open_device(max_retries: int = 10, verbose: bool = False) -> SerialDevice:
    """Open and initialize serial device (synchronous)."""
    log_message("Searching for device...", "INFO", verbose)

    port_info = None
    for attempt in range(max_retries):
        port_info = _find_serial_port(verbose=verbose)
        if port_info is not None:
            break
        log_message(f"Waiting for device... ({attempt+1}/{max_retries})", "WARN", verbose)
        time.sleep(0.5)
    else:
        raise RuntimeError(f"Device not found (VID={VENDOR_ID:04x}, PID={'/'.join(f'{p:04x}' for p in PRODUCT_IDS)})")

    port = port_info.device
    log_message(f"Found device: {port} ({port_info.description})", "INFO", verbose)

    ser = Serial(
        port=port,
        baudrate=115200,
        timeout=0.2,
        write_timeout=5.0,
    )
    log_message("Serial opened: baudrate=115200 timeout=0.2", "DEBUG", verbose)

    # Configure DTR/RTS
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

    return SerialDevice(ser)


async def open_device_async(max_retries: int = 10, verbose: bool = False) -> AsyncSerialDevice:
    """Open and initialize serial device (asynchronous)."""
    log_message("Searching for device (async)...", "INFO", verbose)

    port_info = None
    for attempt in range(max_retries):
        port_info = await find_serial_port_async(verbose=verbose)
        if port_info is not None:
            break
        log_message(f"Waiting for device... ({attempt+1}/{max_retries})", "WARN", verbose)
        await asyncio.sleep(0.5)
    else:
        raise RuntimeError(f"Device not found (VID={VENDOR_ID:04x}, PID={'/'.join(f'{p:04x}' for p in PRODUCT_IDS)})")

    port = port_info.device
    log_message(f"Found device: {port} ({port_info.description})", "INFO", verbose)

    ser = AsyncSerial(
        port=port,
        baudrate=115200,
        timeout=0.2,
        write_timeout=5.0,
    )
    await ser.open()
    log_message("AsyncSerial opened: baudrate=115200 timeout=0.2", "DEBUG", verbose)

    # Configure DTR/RTS
    try:
        ser.dtr = False
        ser.rts = False
        log_message("DTR/RTS set to False to prevent MCU reset", "DEBUG", verbose)
        await asyncio.sleep(0.2)
    except Exception as e:
        log_message(f"Failed to set DTR/RTS: {e}", "WARN", verbose)

    log_message("Device opened (async)", "DEBUG", verbose)
    await asyncio.sleep(0.1)

    return AsyncSerialDevice(ser)


def close_device(device: DeviceType, verbose: bool = False) -> None:
    """Close device and cleanup (synchronous)."""
    if device and hasattr(device, "_ser"):
        try:
            device._ser.close()
        except Exception:
            pass
        if sys.platform == "linux":
            subprocess.run(["modprobe", "cdc_acm"], capture_output=True)
        log_message("Device closed", "INFO", verbose)


async def close_device_async(device: AsyncSerialDevice, verbose: bool = False) -> None:
    """Close device and cleanup (asynchronous)."""
    if device:
        try:
            await device.close()
        except Exception:
            pass
        if sys.platform == "linux":
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: subprocess.run(["modprobe", "cdc_acm"], capture_output=True)
            )
        log_message("Device closed (async)", "INFO", verbose)


def connect(device: SerialDevice, seq: int, verbose: bool = False) -> bool:
    """Send initial connection command (synchronous)."""
    from .protocol import send_command
    log_message("Sending CONN command...", "INFO", verbose)
    ack = send_command(device, "POST conn", {}, seq, verbose=verbose, desc="CONN")
    return ack.get("state") == "success"


async def connect_async(device: AsyncSerialDevice, seq: int, verbose: bool = False) -> bool:
    """Send initial connection command (asynchronous)."""
    from .protocol import send_command_async
    log_message("Sending CONN command (async)...", "INFO", verbose)
    ack = await send_command_async(device, "POST conn", {}, seq, verbose=verbose, desc="CONN")
    return ack.get("state") == "success"
