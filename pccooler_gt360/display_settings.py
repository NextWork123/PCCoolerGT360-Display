"""Display settings control: brightness and orientation."""

from .protocol import log_message, send_command


def set_brightness(device, seq: int, level: int, verbose: bool = False) -> bool:
    """Set display brightness level (0-100).

    Args:
        device: Serial device wrapper
        seq: Sequence number for packet
        level: Brightness level 0-100 (0=off, 100=max)
        verbose: Enable verbose logging

    Returns:
        True if command succeeded
    """
    level = max(0, min(100, level))  # Clamp to valid range
    log_message(f"Setting brightness to {level}%...", "INFO", verbose)
    ack = send_command(
        device,
        "POST brightness",
        {"value": level},
        seq,
        verbose=verbose,
        desc="BRIGHTNESS"
    )
    return ack.get("state") == "success"


def set_orientation(device, seq: int, angle: int, verbose: bool = False) -> bool:
    """Set display orientation/rotation angle.

    Protocol discovered via PCAP probe:
        POST rotate {"degree": N} where N is 0, 90, 180, or 270

    Args:
        device: Serial device wrapper
        seq: Sequence number for packet
        angle: Rotation angle (0, 90, 180, 270)
        verbose: Enable verbose logging

    Returns:
        True if command succeeded
    """
    if angle not in (0, 90, 180, 270):
        log_message(f"Invalid angle {angle}, must be 0/90/180/270", "ERROR", verbose)
        return False

    log_message(f"Setting orientation to {angle}°...", "INFO", verbose)

    # Primary protocol: POST rotate with degree field (discovered via probe)
    ack = send_command(
        device,
        "POST rotate",
        {"degree": angle},
        seq,
        verbose=verbose,
        desc="ORIENTATION"
    )
    return ack.get("state") == "success"


def probe_orientation_protocol(device, seq: int, verbose: bool = False) -> dict:
    """Probe the device to find the correct orientation protocol.

    This is a diagnostic function to help identify which protocol
    variant the device supports.

    Args:
        device: Serial device wrapper
        seq: Starting sequence number
        verbose: Enable verbose logging

    Returns:
        Dictionary with results for each protocol variant
    """
    # Extended list of variants to try
    variants = [
        ("POST rotate", {"degree": 0}),          # Discovered working protocol
        ("POST orientation", {"degree": 0}),
        ("POST display", {"degree": 0}),
        ("POST config", {"degree": 0}),
        ("POST screen", {"degree": 0}),
        ("POST lcd", {"degree": 0}),
        ("POST mode", {"degree": 0}),
        ("POST orientation", {"angle": 0}),
        ("POST rotate", {"rotation": 0}),
        ("POST display", {"orient": 0}),
        ("POST config", {"rotate": 0}),
        ("POST orientation", {"rotate": 0}),
        ("POST mode", {"orientation": 0}),
    ]

    results = {}
    for idx, (endpoint, body) in enumerate(variants):
        log_message(f"Probing: {endpoint} {body}...", "INFO", verbose)
        ack = send_command(
            device,
            endpoint,
            body,
            seq + idx,
            verbose=verbose,
            desc="PROBE"
        )
        key = f"{endpoint} {body}"
        results[key] = ack
        if ack.get("state") == "success":
            log_message(f"  -> SUCCESS!", "SUCCESS", verbose)
        else:
            log_message(f"  -> Failed: {ack}", "DEBUG", verbose)

    return results
