"""
Protocol implementation for PCCooler GT360 display.
"""

import json
import struct
import time
import re
from datetime import datetime

from .constants import PACKET_START, PACKET_END


def log_message(message, level="INFO", verbose=False):
    """Log message if verbose mode is enabled"""
    if verbose or level in ["ERROR", "SUCCESS"]:
        prefix = {"INFO": "ℹ️", "ERROR": "❌", "SUCCESS": "✅", "WARN": "⚠️", "DEBUG": "🔍"}.get(level, "ℹ️")
        print(f"{prefix} {message}")


def build_packet(verb: str, seq: int, body: bytes, verbose: bool = False) -> bytes:
    """Build protocol packet with headers and checksum"""
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
        # Debug: full hex dump
        log_message(f"Packet hex: {packet.hex()}", "DEBUG", verbose)
    
    return packet


def read_ack(device, timeout: int = 2000, verbose: bool = False) -> dict:
    """Read and parse device acknowledgment"""
    try:
        if verbose:
            log_message(f"Reading ACK (timeout={timeout}ms)...", "DEBUG", verbose)

        raw = b""
        deadline = time.time() + (timeout / 1000.0)

        # Loop-read until we have a full response or timeout.
        # Start with a short poll window (10ms) and double it each empty read
        # up to 100ms so an ACK that arrives quickly is caught fast, while we
        # don't spin-waste CPU when the device is slow to respond.
        poll_ms = 10
        while time.time() < deadline:
            chunk = device.read(4096, timeout=poll_ms)
            if chunk:
                raw += chunk
                poll_ms = 10  # reset on progress
                # Check if we have a complete response
                if b'\r\n\r\n' in raw:
                    text = raw.decode('ascii', errors='replace')
                    # Complete JSON body
                    if '{' in text and '}' in text:
                        break
                    # Header-only 200 OK (no JSON body)
                    if '200' in text and len(raw) > 20:
                        break
            else:
                poll_ms = min(poll_ms * 2, 100)  # back-off up to 100ms

        if not raw:
            log_message(f"Timeout waiting for ACK ({timeout}ms)", "WARN", verbose)
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
                        res = json.loads(body[:end+1])
                        log_message(f"JSON parse success: {res}", "DEBUG", verbose)
                        return res
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
            
    except Exception as e:
        log_message(f"ACK read error: {e}", "ERROR", verbose)
    
    return {}


def send_command(device, verb: str, body_dict: dict, seq: int, verbose: bool = False,
                 desc: str = "", retries: int = 3, ack_timeout: int = 2000) -> dict:
    """Send a command and return ACK, with automatic retries on failure"""
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
        except Exception as e:
            log_message(f"← ERR: {e}" + (f" (attempt {attempt+1}/{retries})" if retries > 1 else ""), "ERROR", verbose)

        if attempt < retries - 1:
            time.sleep(0.1)

    return {}
