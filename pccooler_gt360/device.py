"""
Serial device management for PCCooler GT360 display (CDC ACM).
Supports both synchronous and asynchronous operations via wireio.
"""

from __future__ import annotations

import asyncio
import sys
import subprocess
import time
from typing import Optional, Union

from .constants import VENDOR_ID, PRODUCT_ID
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


def _find_serial_port(verbose: bool = False) -> Optional[object]:
    """Return first serial port matching VID/PID, or None."""
    if verbose:
        log_message("Scanning available serial ports...", "DEBUG", verbose)

    ports = list_ports()
    for port in ports:
        if verbose:
            vid_str = f"{port.vid:04x}" if port.vid is not None else "None"
            pid_str = f"{port.pid:04x}" if port.pid is not None else "None"
            log_message(
                f"Checking port: {port.device} (VID={vid_str}, PID={pid_str}, HWID={port.hwid})",
                "DEBUG", verbose
            )

        # Exact match
        if port.vid == VENDOR_ID and port.pid == PRODUCT_ID:
            return port

        # Linux Foundation VID (1d6b) often used for generic/simulated devices
        if port.hwid and f"{VENDOR_ID:04x}:{PRODUCT_ID:04x}" in port.hwid.lower():
            return port
        
        # Fallback: Some CDC ACM devices don't report VID/PID via pyserial
        # Match by description containing "cdc_acm" or device pattern
        if port.description and "cdc_acm" in port.description.lower():
            if verbose:
                log_message(f"Found CDC ACM device by description: {port.device}", "DEBUG", verbose)
            return port
        
        # Also match /dev/ttyACM* pattern on Linux
        if port.device and "/dev/ttyACM" in port.device:
            if verbose:
                log_message(f"Found ACM device by path: {port.device}", "DEBUG", verbose)
            return port

    return None


async def find_serial_port_async(verbose: bool = False) -> Optional[object]:
    """Async port discovery - runs list_ports in executor."""
    if verbose:
        log_message("Scanning available serial ports (async)...", "DEBUG", verbose)

    loop = asyncio.get_event_loop()
    ports = await loop.run_in_executor(None, list_ports)

    for port in ports:
        if verbose:
            vid_str = f"{port.vid:04x}" if port.vid is not None else "None"
            pid_str = f"{port.pid:04x}" if port.pid is not None else "None"
            log_message(
                f"Checking port: {port.device} (VID={vid_str}, PID={pid_str})",
                "DEBUG", verbose
            )

        if port.vid == VENDOR_ID and port.pid == PRODUCT_ID:
            return port

        if port.hwid and f"{VENDOR_ID:04x}:{PRODUCT_ID:04x}" in port.hwid.lower():
            return port
        
        # Fallback: Some CDC ACM devices don't report VID/PID
        if port.description and "cdc_acm" in port.description.lower():
            if verbose:
                log_message(f"Found CDC ACM device by description: {port.device}", "DEBUG", verbose)
            return port
        
        if port.device and "/dev/ttyACM" in port.device:
            if verbose:
                log_message(f"Found ACM device by path: {port.device}", "DEBUG", verbose)
            return port

    return None


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
        raise RuntimeError(f"Device not found (VID={VENDOR_ID:04x}, PID={PRODUCT_ID:04x})")

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
        raise RuntimeError(f"Device not found (VID={VENDOR_ID:04x}, PID={PRODUCT_ID:04x})")

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
