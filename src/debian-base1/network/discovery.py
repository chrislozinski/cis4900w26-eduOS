#!/usr/bin/env python3
"""
mDNS teacher advertisement and student discovery via python-zeroconf.
Do not run avahi-daemon alongside this (both want UDP 5353).
"""
from __future__ import annotations

import socket
import time
from typing import Optional

from .constants import DEFAULT_TCP_PORT, MDNS_SERVICE_NAME, MDNS_SERVICE_TYPE


class TeacherAdvertiser:
    """Registers _ychitsa._tcp.local. so students can find the teacher."""

    def __init__(self, lanIp: str, tcpPort: int, classroomId: str):
        self._zc = None
        self._info = None
        self._lanIp = lanIp
        self._tcpPort = tcpPort
        self._classroomId = classroomId

    def start(self) -> bool:
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except ImportError:
            print("[discovery] python-zeroconf not installed; mDNS disabled")
            return False
        try:
            self._info = ServiceInfo(
                MDNS_SERVICE_TYPE,
                f"{MDNS_SERVICE_NAME}.{MDNS_SERVICE_TYPE}",
                addresses=[socket.inet_aton(self._lanIp)],
                port=self._tcpPort,
                properties={
                    "classroom_id": self._classroomId.encode("utf-8"),
                    "version": b"2",
                },
            )
            self._zc = Zeroconf()
            self._zc.register_service(self._info)
            print(f"[discovery] mDNS registered: {MDNS_SERVICE_NAME}.{MDNS_SERVICE_TYPE}")
            return True
        except OSError as e:
            print(f"[discovery] mDNS failed (port 5353 in use?): {e}")
            return False
        except Exception as e:
            print(f"[discovery] mDNS registration failed: {e}")
            return False

    def stop(self) -> None:
        if self._zc and self._info:
            try:
                self._zc.unregister_service(self._info)
                self._zc.close()
            except Exception:
                pass
            self._zc = None
            self._info = None


class _DiscoveryListener:
    def __init__(self):
        self.result: Optional[dict] = None

    def add_service(self, zc, type_: str, name: str) -> None:
        if self.result:
            return
        info = zc.get_service_info(type_, name)
        if not info or not info.addresses:
            return
        host = socket.inet_ntoa(info.addresses[0])
        self.result = {
            "host": host,
            "tcpPort": info.port or DEFAULT_TCP_PORT,
        }

    def remove_service(self, *_args) -> None:
        pass

    def update_service(self, *_args) -> None:
        pass


def discoverTeacher(timeoutSeconds: int = 5) -> Optional[dict]:
    """Browse mDNS for the teacher. Returns {host, tcpPort} or None."""
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except ImportError:
        return None

    listener = _DiscoveryListener()
    zc = Zeroconf()
    try:
        ServiceBrowser(zc, MDNS_SERVICE_TYPE, listener)
        deadline = time.time() + timeoutSeconds
        while time.time() < deadline:
            if listener.result:
                return listener.result
            time.sleep(0.1)
        return None
    except Exception as e:
        print(f"[discovery] mDNS browse error: {e}")
        return None
    finally:
        zc.close()


def tcpReachable(host: str, port: int, timeoutSeconds: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeoutSeconds):
            return True
    except OSError:
        return False
