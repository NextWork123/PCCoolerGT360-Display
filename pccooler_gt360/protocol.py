"""
Protocol implementation for PCCooler GT360 display.
Supports both synchronous and asynchronous operations.
"""

from __future__ import annotations

import asyncio
import json
import re
import struct
import time
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from .constants import PACKET_START, PACKET_END

if TYPE_CHECKING:
    from .device import SerialDevice, AsyncSerialDevice


def log_message(message: str, level: str = "INFO", verbose: bool = False) -> None:
    """Log message if verbose mode is enabled."""
    if verbose or level in ["ERROR", "SUCCESS"]:
        prefix = {"INFO": "ℹ️", "ERROR": "❌", "SUCCESS": "✅", "WARN": "⚠️", "DEBUG": "🔍"}.get(level, "ℹ️")
        print(f"{prefix} {message}")


def build_packet(verb: str, seq: int, body: bytes, verbose: bool = False) -> bytes:
    """Build protocol packet with headers and checksum."""
    ts = int(datetime.now().timestamp() * 1000)

    header = (
        f"{verb} 1\r\n"
        f"SeqNumber={seq}\r\n"
        f"Date={ts}\r\n"
        f"ContentType=json\r\n"
        f"ContentLength={len(body)}\r\n\r\n"
    ).encode()

    payload = header + body
    total = 3 + len(payload) + 2
    length_field = struct.pack(">H", total)
    checksum = sum(length_field + payload) & 0xFF

    packet = bytes([PACKET_START]) + length_field + payload + bytes([checksum]) + bytes([PACKET_END])

    if verbose:
        log_message(f"Packet: verb='{verb}' seq={seq} len={len(packet)}", "DEBUG", verbose)
        log_message(f"Packet hex: {packet.hex()}", "DEBUG", verbose)

    return packet


def _parse_ack_response(raw: bytes, verbose: bool = False) -> dict:
    """Parse raw ACK response bytes into dict."""
    if not raw:
        return {}

    if verbose:
        log_message(f"Raw ACK ({len(raw)}B): {raw.hex()}", "DEBUG", verbose)

    text = raw.decode('ascii', errors='replace')

    # Try to parse JSON response
    if '\r\n\r\n' in text:
        headers, body = text.split('\r\n\r\n', 1)
        if body and '{' in body:
            try:
                log_message("Attempting JSON parse...", "DEBUG", verbose)
                end = body.rfind('}')
                if end >= 0:
                    result = json.loads(body[:end+1])
                    log_message(f"JSON parse success: {result}", "DEBUG", verbose)
                    return result
            except json.JSONDecodeError:
                log_message("JSON parse failed", "DEBUG", verbose)

        # Simple success detection
        if '200' in headers:
            log_message("Detected '200' in headers", "DEBUG", verbose)
            ack_match = re.search(r'AckNumber=(\d+)', headers)
            return {
                'state': 'success',
                'ackNumber': int(ack_match.group(1)) if ack_match else 0,
                'raw': text[:100]
            }

    if '200' in text[:50] or 'success' in text.lower():
        log_message("Detected '200' or 'success' in text", "DEBUG", verbose)
        return {'state': 'success', 'raw': text[:100]}

    return {}


def read_ack(device: "SerialDevice", timeout: int = 2000, verbose: bool = False) -> dict:
    """Read and parse device acknowledgment (synchronous)."""
    try:
        if verbose:
            log_message(f"Reading ACK (timeout={timeout}ms)...", "DEBUG", verbose)

        raw = b""
        deadline = time.time() + (timeout / 1000.0)

        poll_ms = 10
        while time.time() < deadline:
            chunk = device.read(4096, timeout=poll_ms)
            if chunk:
                raw += chunk
                poll_ms = 10
                if b'\r\n\r\n' in raw:
                    text = raw.decode('ascii', errors='replace')
                    if '{' in text and '}' in text:
                        break
                    if '200' in text and len(raw) > 20:
                        break
            else:
                poll_ms = min(poll_ms * 2, 100)

        if not raw:
            log_message(f"Timeout waiting for ACK ({timeout}ms)", "WARN", verbose)
            return {}

        return _parse_ack_response(raw, verbose)

    except Exception as e:
        log_message(f"ACK read error: {e}", "ERROR", verbose)

    return {}


async def read_ack_async(device: "AsyncSerialDevice", timeout: int = 2000, verbose: bool = False) -> dict:
    """Read and parse device acknowledgment (asynchronous)."""
    try:
        if verbose:
            log_message(f"Reading ACK async (timeout={timeout}ms)...", "DEBUG", verbose)

        raw = b""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + (timeout / 1000.0)

        while loop.time() < deadline:
            chunk = await device.read(4096, timeout=10)
            if chunk:
                raw += chunk
                if b'\r\n\r\n' in raw:
                    text = raw.decode('ascii', errors='replace')
                    if '{' in text and '}' in text:
                        break
                    if '200' in text and len(raw) > 20:
                        break
            else:
                # Use asyncio.sleep instead of blocking
                await asyncio.sleep(0.01)

        if not raw:
            log_message(f"Timeout waiting for ACK ({timeout}ms)", "WARN", verbose)
            return {}

        return _parse_ack_response(raw, verbose)

    except Exception as e:
        log_message(f"ACK read error (async): {e}", "ERROR", verbose)

    return {}


def send_command(
    device: "SerialDevice",
    verb: str,
    body_dict: dict,
    seq: int,
    verbose: bool = False,
    desc: str = "",
    retries: int = 3,
    ack_timeout: int = 2000
) -> dict:
    """Send a command and return ACK, with automatic retries (synchronous)."""
    from wireio import SerialError

    body = json.dumps(body_dict).encode()
    pkt = build_packet(verb, seq, body, verbose=verbose)
    desc = desc or verb

    for attempt in range(retries):
        log_message(f"→ {desc}: {body}" + (f" (retry {attempt})" if attempt > 0 else ""),
                    "INFO" if verbose else "DEBUG", verbose)
        try:
            start_write = time.time()
            device.write(pkt, timeout=5000)
            write_duration = (time.time() - start_write) * 1000
            if verbose:
                log_message(f"Write took {write_duration:.1f}ms", "DEBUG", verbose)

            ack = read_ack(device, timeout=ack_timeout, verbose=verbose)
            log_message(f"← ACK: {ack}", "INFO" if verbose else "DEBUG", verbose)
            if ack:
                return ack
        except SerialError as e:
            log_message(f"← ERR: {e}" + (f" (attempt {attempt+1}/{retries})" if retries > 1 else ""), "ERROR", verbose)

        if attempt < retries - 1:
            time.sleep(0.1)

    return {}


async def send_command_async(
    device: "AsyncSerialDevice",
    verb: str,
    body_dict: dict,
    seq: int,
    verbose: bool = False,
    desc: str = "",
    retries: int = 3,
    ack_timeout: int = 2000
) -> dict:
    """Send a command and return ACK, with automatic retries (asynchronous)."""
    from wireio import SerialError

    body = json.dumps(body_dict).encode()
    pkt = build_packet(verb, seq, body, verbose=verbose)
    desc = desc or verb

    for attempt in range(retries):
        log_message(f"→ {desc}: {body}" + (f" (retry {attempt})" if attempt > 0 else ""),
                    "INFO" if verbose else "DEBUG", verbose)
        try:
            start_write = asyncio.get_event_loop().time()
            await device.write(pkt, timeout=5000)
            write_duration = (asyncio.get_event_loop().time() - start_write) * 1000
            if verbose:
                log_message(f"Write took {write_duration:.1f}ms", "DEBUG", verbose)

            ack = await read_ack_async(device, timeout=ack_timeout, verbose=verbose)
            log_message(f"← ACK: {ack}", "INFO" if verbose else "DEBUG", verbose)
            if ack:
                return ack
        except SerialError as e:
            log_message(f"← ERR: {e}" + (f" (attempt {attempt+1}/{retries})" if retries > 1 else ""), "ERROR", verbose)

        if attempt < retries - 1:
            await asyncio.sleep(0.1)

    return {}
