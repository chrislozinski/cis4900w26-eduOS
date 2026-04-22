#!/usr/bin/env python3
"""
Teacher state publisher.

On startup:
  - Prints the classroom join code to the terminal (students enter this once).
  - Broadcasts a UDP beacon every 2 s on the local network.
  - Serves signed, gzip-compressed student state over TCP.

Usage:
    python3 -m network.publisher
    CIS4900_IFACE=wlan0 python3 -m network.publisher
"""
import argparse
import gzip
import json
import os
import socket
import threading
import time

from . import schema, signing
from .constants import BEACON_PREFIX, DEFAULT_SHARED_SECRET, DEFAULT_TCP_PORT, DEFAULT_UDP_PORT
from .transport import recvFramed, sendFramed

CLASSROOMS_FILE = os.environ.get(
    "CIS4900_CLASSROOMS_FILE",
    "/var/lib/cis4900/classrooms.json",
)


# Network utilities
def _getLanIp(ifaceName: str | None = None) -> str:
    """
    Return the real LAN IP, not the bind address 0.0.0.0.
    Tries the named interface first, falls back to default-route detection.
    """
    if ifaceName:
        try:
            import fcntl, struct
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            result = fcntl.ioctl(s.fileno(), 0x8915, struct.pack("256s", ifaceName[:15].encode()))
            return socket.inet_ntoa(result[20:24])
        except Exception:
            pass
    # Try routing, works on local nets even without internet, as long as a default gateway is configured
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
 
    # Fallback: enumerate bound addresses that works on ad-hoc/hotspot with no gateway at all.
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ip = info[4][0]
        if not ip.startswith("127."):
            return ip
 
    return "127.0.0.1"
 

def _getBroadcastAddr(ifaceName: str | None = None) -> str:
    """
    Return the directed broadcast for ifaceName (e.g. 192.168.1.255),
    or 255.255.255.255 if not specified.

    Using the directed broadcast pins the UDP packet to the correct interface
    when the machine has both wlan0 and eth0 active.
    """
    if not ifaceName:
        return "255.255.255.255"
    try:
        import ipaddress, subprocess
        out = subprocess.check_output(
            ["ip", "-4", "addr", "show", ifaceName], stderr=subprocess.DEVNULL
        ).decode()
        for line in out.splitlines():
            if line.strip().startswith("inet "):
                net = ipaddress.IPv4Network(line.strip().split()[1], strict=False)
                return str(net.broadcast_address)
    except Exception:
        pass
    return "255.255.255.255"


# Join code
def _printJoinCode(secret: str, classroomId: str) -> None:
    """
    Print a short join code to the terminal.
    Students type this once into the student machine's join prompt.
    The code is the first 8 hex chars of SHA-256(secret), short enough to read in a room, 
    not meant to be the secret itself
    """
    import hashlib
    display_code = hashlib.sha256(secret.encode()).hexdigest()[:8].upper()
    print()
    print("=" * 50)
    print(f"  Classroom : {classroomId}")
    print(f"  Join code : {display_code}")
    print("=" * 50)
    print("  Students: run  python3 -m network.agent --join")
    print("  and enter this code when prompted.")
    print("=" * 50)
    print()


# State builder
def _buildStudentStates(sharedSecret: str) -> dict:
    with open(CLASSROOMS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    byStudent = {}
    for classroom in data.get("classrooms", []):
        for studentId in classroom.get("students", []):
            state = schema.buildStudentState(studentId, classroom)
            canonical = schema.canonicalizeStudentState(state)
            state["security"]["signature"] = signing.signState(canonical, sharedSecret)
            byStudent[studentId] = state
    return byStudent


# Beacon loop
def _beaconLoop(lanIp: str, udpPort: int, tcpPort: int, broadcastAddr: str, stop: threading.Event) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    beacon = f"{BEACON_PREFIX}|{lanIp}|{tcpPort}".encode("utf-8")
    while not stop.is_set():
        sock.sendto(beacon, (broadcastAddr, udpPort))
        time.sleep(2)
    sock.close()


# Client handler
def _handleClient(conn: socket.socket, addr: tuple, sharedSecret: str) -> None:
    try:
        hello = json.loads(recvFramed(conn).decode("utf-8"))
        studentId  = hello.get("student_id", "")
        studentHash = hello.get("state_hash", "")

        try:
            states = _buildStudentStates(sharedSecret)
        except FileNotFoundError:
            print(f"[publisher] ERROR: classrooms file not found: {CLASSROOMS_FILE}")
            sendFramed(conn, gzip.compress(json.dumps({"action": "noop", "reason": "no-classrooms"}).encode()))
            return

        state = states.get(studentId)
        if not state:
            print(f"[publisher] unknown student: {studentId!r}")
            sendFramed(conn, gzip.compress(json.dumps({"action": "noop"}).encode()))
            return

        serverHash = schema.computeStateHash(state)
        if studentHash == serverHash:
            response = {"action": "noop", "reason": "already-current"}
        else:
            response = {"action": "apply", "student_state": state, "state_hash": serverHash}

        sendFramed(conn, gzip.compress(json.dumps(response).encode("utf-8")))
        print(f"[publisher] {studentId} ({addr[0]}) -> {response['action']}")
    except Exception as e:
        print(f"[publisher] error handling {addr}: {e}")


# Entry point
def runPublisher(host: str, udpPort: int, tcpPort: int, sharedSecret: str, ifaceName: str | None = None) -> None:
    lanIp = _getLanIp(ifaceName)
    broadcastAddr = _getBroadcastAddr(ifaceName)
    print(f"[publisher] LAN IP: {lanIp}  broadcast: {broadcastAddr}  TCP: {tcpPort}")

    # Print classroom join code for students
    try:
        with open(CLASSROOMS_FILE) as f:
            classroomId = json.load(f).get("classrooms", [{}])[0].get("id", "classroom")
    except Exception:
        classroomId = "classroom"
    _printJoinCode(sharedSecret, classroomId)

    stop = threading.Event()
    threading.Thread(
        target=_beaconLoop,
        args=(lanIp, udpPort, tcpPort, broadcastAddr, stop),
        daemon=True,
    ).start()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, tcpPort))
    server.listen(32)
    print(f"[publisher] TCP server ready on {host}:{tcpPort}")

    try:
        while True:
            conn, addr = server.accept()
            with conn:
                _handleClient(conn, addr, sharedSecret)
    finally:
        stop.set()
        server.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="CIS4900 teacher state publisher")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT)
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT)
    parser.add_argument("--shared-secret",
        default=os.environ.get("CIS4900_STATE_SECRET", DEFAULT_SHARED_SECRET))
    parser.add_argument("--iface",
        default=os.environ.get("CIS4900_IFACE"),
        help="Network interface for beacon (e.g. wlan0). Defaults to default-route interface.")
    args = parser.parse_args()
    runPublisher(args.host, args.udp_port, args.tcp_port, args.shared_secret, args.iface)


if __name__ == "__main__":
    main()
