#!/usr/bin/env python3
"""
Student state agent.

Normal run (after join):
    python3 -m network.agent

First-time join (student enters the code shown on teacher screen):
    python3 -m network.agent --join

TEACHER_IP bypass (Docker / known IP):
    TEACHER_IP=192.168.1.10 python3 -m network.agent
"""
import argparse
import gzip
import json
import os
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone

from . import apply as apply_mod
from . import schema, signing
from .constants import (
    BEACON_PREFIX,
    DEFAULT_SHARED_SECRET,
    DEFAULT_STATE_PATH,
    DEFAULT_TCP_PORT,
    DEFAULT_UDP_PORT,
    JOIN_CONFIG_PATH,
    MAX_TIMESTAMP_AGE_SECONDS,
)
from .transport import recvFramed, sendFramed

_JOIN_PATH = os.path.expanduser(JOIN_CONFIG_PATH)


# Join config written once at first-time setup
def _loadJoinConfig() -> tuple[str | None, str | None]:
    """Load secret + classroom_id from the saved join config. Returns (None, None) if not found."""
    try:
        with open(_JOIN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("secret"), data.get("classroom_id")
    except FileNotFoundError:
        return None, None


def _saveJoinConfig(secret: str, classroomId: str) -> None:
    os.makedirs(os.path.dirname(_JOIN_PATH), exist_ok=True)
    with open(_JOIN_PATH, "w", encoding="utf-8") as f:
        json.dump({"secret": secret, "classroom_id": classroomId}, f, indent=2)
    print(f"[agent] Join config saved to {_JOIN_PATH}")


def _runJoinPrompt(sharedSecretDefault: str) -> str:
    """
    Interactive first-time join.
    The teacher displays a short code on screen (8 hex chars).
    We don't store the code, the teacher's actual code is set via env/arg 
    The code just confirms the student is talking to the right classroom.
    The student saves the secret itself so future runs are automatic.
    """
    import hashlib
    print()
    print("=" * 50)
    print("  CIS4900 — First-time classroom join")
    print("  Enter the join code shown on the teacher's screen.")
    print("=" * 50)
    entered = input("  Join code: ").strip().upper()
    expected = hashlib.sha256(sharedSecretDefault.encode()).hexdigest()[:8].upper()
    if entered != expected:
        print("[agent] Join code does not match. Check the teacher screen and try again.")
        raise SystemExit(1)
    classroom_id = input("  Classroom ID (press Enter to skip): ").strip() or "_unassigned"
    _saveJoinConfig(sharedSecretDefault, classroom_id)
    print("[agent] Joined successfully.")
    return sharedSecretDefault


# State helpers
def _getCurrentStateHash(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return schema.computeStateHash(state)
    except Exception:
        return ""


def _validateTimestamp(state: dict) -> bool:
    ts = state.get("security", {}).get("timestamp")
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return False
    now = datetime.now(timezone.utc)
    return now - timedelta(seconds=MAX_TIMESTAMP_AGE_SECONDS) <= dt <= now + timedelta(seconds=30)


def _maybeRefresh() -> None:
    try:
        subprocess.Popen(["i3-msg", "restart"])
    except Exception:
        pass


# Beacon / discovery
def _waitForBeacon(udpPort: int, timeoutSeconds: int = 30) -> tuple[str, int]:
    """
    Return (teacherIp, tcpPort).
    TEACHER_IP env var skips UDP entirely — useful in Docker or when IP is known.
    """
    override = os.environ.get("TEACHER_IP")
    if override:
        port = int(os.environ.get("TEACHER_TCP_PORT", str(DEFAULT_TCP_PORT)))
        print(f"[agent] TEACHER_IP override → {override}:{port}")
        return override, port

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", udpPort))
    sock.settimeout(timeoutSeconds)
    try:
        data, _ = sock.recvfrom(4096)
    except socket.timeout:
        raise TimeoutError(
            f"No beacon received in {timeoutSeconds}s. "
            "Is the teacher publisher running? "
            "Set TEACHER_IP env var to bypass discovery."
        )
    finally:
        sock.close()

    payload = data.decode("utf-8", errors="ignore")
    if not payload.startswith(BEACON_PREFIX):
        raise ValueError(f"Unexpected beacon: {payload!r}")
    parts = payload.split("|", 2)
    if len(parts) != 3:
        raise ValueError(f"Malformed beacon: {payload!r}")
    _, host, tcpPort = parts
    return host, int(tcpPort)


# Main loop
def runAgent(studentId: str, udpPort: int, statePath: str, sharedSecret: str) -> None:
    print(f"[agent] starting — student_id={studentId}  state={statePath}")
    while True:
        try:
            host, tcpPort = _waitForBeacon(udpPort)
            hello = {"student_id": studentId, "state_hash": _getCurrentStateHash(statePath)}

            with socket.create_connection((host, tcpPort), timeout=10) as conn:
                sendFramed(conn, json.dumps(hello).encode("utf-8"))
                responseRaw = gzip.decompress(recvFramed(conn))

            response = json.loads(responseRaw.decode("utf-8"))
            if response.get("action") != "apply":
                time.sleep(5)
                continue

            state = response.get("student_state", {})
            schema.validateStudentState(state)

            if not _validateTimestamp(state):
                print("[agent] rejected: stale timestamp")
                time.sleep(3)
                continue

            sig      = state.get("security", {}).get("signature", "")
            canonical = schema.canonicalizeStudentState(state)
            if not signing.verifySignature(canonical, sig, sharedSecret):
                print("[agent] rejected: bad signature, wrong code. Re-run with --join.")
                time.sleep(3)
                continue

            apply_mod.applyStudentState(state, statePath)
            print(f"[agent] state applied for {studentId}")
            _maybeRefresh()

        except TimeoutError as e:
            print(f"[agent] {e}")
            time.sleep(5)
        except Exception as e:
            print(f"[agent] retrying after error: {e}")
            time.sleep(3)


def main() -> None:
    # Secret priority: env var > saved join config > compiled default
    join_secret, _ = _loadJoinConfig()

    parser = argparse.ArgumentParser(description="CIS4900 student state agent")
    parser.add_argument("--student-id",
        default=os.environ.get("USER", "studentuser"))
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT)
    parser.add_argument("--state-path", default=DEFAULT_STATE_PATH)
    parser.add_argument("--shared-secret",
        default=os.environ.get("CIS4900_STATE_SECRET") or join_secret or DEFAULT_SHARED_SECRET)
    parser.add_argument("--join", action="store_true",
        help="Run interactive first-time join prompt to enter the classroom code")
    args = parser.parse_args()

    if args.join:
        args.shared_secret = _runJoinPrompt(args.shared_secret)

    runAgent(args.student_id, args.udp_port, args.state_path, args.shared_secret)


if __name__ == "__main__":
    main()
