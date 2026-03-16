"""
Power and display state control for PCCooler GT360 display.
Supports both synchronous and asynchronous operations.
"""

from __future__ import annotations

from .protocol import log_message, send_command, send_command_async
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .device import SerialDevice, AsyncSerialDevice


def wakeup(device: "SerialDevice", seq: int, verbose: bool = False) -> bool:
    """Send wakeup/resume command (synchronous)."""
    log_message("Sending WAKEUP command...", "INFO", verbose)
    ack = send_command(device, "POST power", {"event": "resume"}, seq, verbose=verbose, desc="WAKEUP")
    return ack.get("state") == "success"


async def wakeup_async(device: "AsyncSerialDevice", seq: int, verbose: bool = False) -> bool:
    """Send wakeup/resume command (asynchronous)."""
    log_message("Sending WAKEUP command (async)...", "INFO", verbose)
    ack = await send_command_async(device, "POST power", {"event": "resume"}, seq, verbose=verbose, desc="WAKEUP")
    return ack.get("state") == "success"


def sleep(device: "SerialDevice", seq: int, verbose: bool = False) -> bool:
    """Send sleep/suspend command (synchronous)."""
    log_message("Sending SLEEP command...", "INFO", verbose)
    ack = send_command(device, "POST power", {"event": "suspend"}, seq, verbose=verbose, desc="SLEEP")
    return ack.get("state") == "success"


async def sleep_async(device: "AsyncSerialDevice", seq: int, verbose: bool = False) -> bool:
    """Send sleep/suspend command (asynchronous)."""
    log_message("Sending SLEEP command (async)...", "INFO", verbose)
    ack = await send_command_async(device, "POST power", {"event": "suspend"}, seq, verbose=verbose, desc="SLEEP")
    return ack.get("state") == "success"


def recovery(device: "SerialDevice", seq: int, enable: bool = True, verbose: bool = False) -> bool:
    """Send recovery command (synchronous)."""
    log_message(f"Sending RECOVERY command (enable={enable})...", "INFO", verbose)
    ack = send_command(device, "POST recovery", {"enable": enable}, seq, verbose=verbose, desc="RECOVERY")
    return ack.get("state") == "success"


async def recovery_async(device: "AsyncSerialDevice", seq: int, enable: bool = True, verbose: bool = False) -> bool:
    """Send recovery command (asynchronous)."""
    log_message(f"Sending RECOVERY command (enable={enable}, async)...", "INFO", verbose)
    ack = await send_command_async(device, "POST recovery", {"enable": enable}, seq, verbose=verbose, desc="RECOVERY")
    return ack.get("state") == "success"


def set_timeout(device: "SerialDevice", seq: int, seconds: int = 60, verbose: bool = False) -> bool:
    """Set display timeout in seconds (synchronous)."""
    log_message(f"Setting timeout to {seconds} seconds...", "INFO", verbose)
    ack = send_command(device, "POST timeout", {"value": seconds}, seq, verbose=verbose, desc="TIMEOUT")
    return ack.get("state") == "success"


async def set_timeout_async(device: "AsyncSerialDevice", seq: int, seconds: int = 60, verbose: bool = False) -> bool:
    """Set display timeout in seconds (asynchronous)."""
    log_message(f"Setting timeout to {seconds} seconds (async)...", "INFO", verbose)
    ack = await send_command_async(device, "POST timeout", {"value": seconds}, seq, verbose=verbose, desc="TIMEOUT")
    return ack.get("state") == "success"
