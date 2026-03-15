"""
Power and display state control for PCCooler GT360 display.
"""

from .protocol import log_message, send_command


def wakeup(device, seq: int, verbose: bool = False) -> bool:
    """Send wakeup/resume command"""
    log_message("Sending WAKEUP command...", "INFO", verbose)
    ack = send_command(device, "POST power", {"event": "resume"}, seq, verbose=verbose, desc="WAKEUP")
    return ack.get("state") == "success"


def sleep(device, seq: int, verbose: bool = False) -> bool:
    """Send sleep/suspend command"""
    log_message("Sending SLEEP command...", "INFO", verbose)
    ack = send_command(device, "POST power", {"event": "suspend"}, seq, verbose=verbose, desc="SLEEP")
    return ack.get("state") == "success"


def recovery(device, seq: int, enable: bool = True, verbose: bool = False) -> bool:
    """Send recovery command"""
    log_message(f"Sending RECOVERY command (enable={enable})...", "INFO", verbose)
    ack = send_command(device, "POST recovery", {"enable": enable}, seq, verbose=verbose, desc="RECOVERY")
    return ack.get("state") == "success"


def set_timeout(device, seq: int, seconds: int = 60, verbose: bool = False) -> bool:
    """Set display timeout in seconds (0 = disable timeout?)"""
    log_message(f"Setting timeout to {seconds} seconds...", "INFO", verbose)
    ack = send_command(device, "POST timeout", {"value": seconds}, seq, verbose=verbose, desc="TIMEOUT")
    return ack.get("state") == "success"
