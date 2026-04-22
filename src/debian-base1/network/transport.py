#!/usr/bin/env python3
"""Low-level UDP broadcast and TCP framing helpers."""
import socket
import struct


def broadcastBeacon(message: str, udpPort: int, broadcastAddr: str = "255.255.255.255") -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.sendto(message.encode("utf-8"), (broadcastAddr, udpPort))
    sock.close()


def listenForBeacon(udpPort: int, expectedPrefix: str, timeoutSeconds: int = 10):
    """Block until a beacon is received. Returns (text, senderIp)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", udpPort))
    sock.settimeout(timeoutSeconds)
    data, addr = sock.recvfrom(4096)
    sock.close()
    text = data.decode("utf-8", errors="ignore")
    if not text.startswith(expectedPrefix):
        raise ValueError(f"Unexpected beacon payload: {text!r}")
    return text, addr[0]


def sendFramed(sock: socket.socket, payload: bytes) -> None:
    sock.sendall(struct.pack("!I", len(payload)))
    sock.sendall(payload)


def recvFramed(sock: socket.socket) -> bytes:
    header = _recvExactly(sock, 4)
    length = struct.unpack("!I", header)[0]
    return _recvExactly(sock, length)


def _recvExactly(sock: socket.socket, length: int) -> bytes:
    chunks, remaining = [], length
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Socket closed before payload was complete")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
