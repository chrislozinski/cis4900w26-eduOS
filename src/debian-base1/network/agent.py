#!/usr/bin/env python3
"""
Student state agent.

Discovery waterfall: TEACHER_IP -> mDNS -> last_teacher_ip -> UDP beacon.
Handles apply (+ lesson tar), apply_ack, collect/report, apply_work, join.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import socket
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone

from . import apply as apply_mod
from . import discovery, schema, signing, workpack
from .constants import (
    ACTION_APPLY,
    ACTION_APPLY_ACK,
    ACTION_APPLY_WORK,
    ACTION_COLLECT,
    ACTION_JOIN_ACCEPT,
    ACTION_JOIN_REJECT,
    ACTION_JOIN_REQUEST,
    ACTION_NOOP,
    ACTION_PING,
    ACTION_PONG,
    ACTION_REPORT,
    BEACON_PREFIX,
    DEFAULT_SHARED_SECRET,
    DEFAULT_STATE_PATH,
    DEFAULT_TCP_PORT,
    DEFAULT_UDP_PORT,
    JOIN_CONFIG_PATH,
    MAX_TIMESTAMP_AGE_SECONDS,
    STUDENT_LESSONS_DIR,
)
from .transport import recvFramed, sendFramed

_JOIN_PATH = os.path.expanduser(JOIN_CONFIG_PATH)


def _loadJoinConfig() -> dict:
    try:
        with open(_JOIN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _saveJoinConfig(data: dict) -> None:
    os.makedirs(os.path.dirname(_JOIN_PATH), exist_ok=True)
    with open(_JOIN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[agent] Join config saved to {_JOIN_PATH}")


def _deviceId() -> str:
    cfg = _loadJoinConfig()
    if cfg.get("device_id"):
        return cfg["device_id"]
    did = str(uuid.uuid4())
    cfg["device_id"] = did
    _saveJoinConfig(cfg)
    return did


def _getCurrentStateHash(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return schema.computeContentHash(state)
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
    """Reload the sidebar for new enabled_apps. Do not restart i3 (destroys layout)."""
    launcher = os.path.expanduser("~/.config/launcher/launcher.py")
    if not os.path.isfile(launcher):
        return
    # Match launcher with absolute script path that waits for kill
    try:
        subprocess.run(
            ["pkill", "-u", str(os.getuid()), "-f", f"python3 {launcher}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    time.sleep(0.4)  # let the swallow placeholder settle before remapping
    try:
        subprocess.Popen(
            ["python3", launcher],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.path.expanduser("~"),
            env=os.environ.copy(),  # keep DISPLAY / XDG_RUNTIME_DIR from the session
        )
    except Exception:
        pass


def _sendJson(conn: socket.socket, obj: dict, compress: bool = True) -> None:
    raw = json.dumps(obj).encode("utf-8")
    sendFramed(conn, gzip.compress(raw) if compress else raw)


def _recvJson(conn: socket.socket) -> dict:
    raw = recvFramed(conn)
    try:
        raw = gzip.decompress(raw)
    except Exception:
        pass
    return json.loads(raw.decode("utf-8"))


def _waitForBeacon(udpPort: int, timeoutSeconds: int = 30) -> tuple[str, int]:
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
            "Set TEACHER_IP to bypass discovery."
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


def discoverTeacherHost(udpPort: int) -> tuple[str, int]:
    """TEACHER_IP -> last_teacher_ip (verified) -> mDNS -> UDP beacon."""
    override = os.environ.get("TEACHER_IP")
    if override:
        port = int(os.environ.get("TEACHER_TCP_PORT", str(DEFAULT_TCP_PORT)))
        print(f"[agent] TEACHER_IP override → {override}:{port}")
        return override, port

    # A joined student stays sticky to its teacher. Checking join.json before
    # mDNS also stops the Docker desktop's own publisher from hijacking the
    # agent (the container advertises itself over mDNS).
    cfg = _loadJoinConfig()
    lastIp = cfg.get("last_teacher_ip")
    lastPort = int(cfg.get("tcp_port") or DEFAULT_TCP_PORT)
    if lastIp and discovery.tcpReachable(lastIp, lastPort):
        print(f"[agent] last_teacher_ip → {lastIp}:{lastPort}")
        return lastIp, lastPort

    mdns = discovery.discoverTeacher(timeoutSeconds=4)
    if mdns:
        print(f"[agent] mDNS → {mdns['host']}:{mdns['tcpPort']}")
        return mdns["host"], int(mdns["tcpPort"])

    return _waitForBeacon(udpPort)


def _applyState(response: dict, statePath: str, sharedSecret: str, studentId: str) -> tuple[bool, str, str]:
    state = response.get("student_state", {})
    try:
        schema.validateStudentState(state)
    except Exception as e:
        return False, str(e), ""
    if not _validateTimestamp(state):
        return False, "stale_timestamp", ""
    sig = state.get("security", {}).get("signature", "")
    canonical = schema.canonicalizeStudentState(state)
    if not signing.verifySignature(canonical, sig, sharedSecret):
        return False, "bad_signature", ""
    apply_mod.applyStudentState(state, statePath)

    lessonsB64 = response.get("lessons_tar_b64")
    if lessonsB64:
        fd, tarPath = tempfile.mkstemp(suffix="-lessons.tar.gz")
        os.close(fd)
        try:
            with open(tarPath, "wb") as f:
                f.write(base64.b64decode(lessonsB64))
            # Prefer shared path; fall back to home if not writable
            dest = STUDENT_LESSONS_DIR
            try:
                os.makedirs(dest, exist_ok=True)
                test = os.path.join(dest, ".write_test")
                with open(test, "w") as tf:
                    tf.write("ok")
                os.remove(test)
            except OSError:
                dest = os.path.expanduser("~/.local/share/cis4900/teacher-lessons")
                os.makedirs(dest, exist_ok=True)
            ok, reason = workpack.unpackLessonsArchive(tarPath, dest)
            if not ok:
                print(f"[agent] lesson unpack warning: {reason}")
        finally:
            try:
                os.remove(tarPath)
            except OSError:
                pass

    h = schema.computeContentHash(state)
    return True, "ok", h


def _handleSession(
    conn: socket.socket,
    studentId: str,
    statePath: str,
    sharedSecret: str,
    classroomId: str,
) -> None:
    hello = {
        "action": "hello",
        "student_id": studentId,
        "state_hash": _getCurrentStateHash(statePath),
        "classroom_id": classroomId,
    }
    _sendJson(conn, hello, compress=False)

    # Publisher may send collect and/or apply_work before apply/noop on one connection.
    while True:
        response = _recvJson(conn)
        action = response.get("action")

        if action == ACTION_COLLECT:
            cid = response.get("classroom_id") or classroomId
            tmp = tempfile.mkdtemp(prefix="ychitsa-work-")
            try:
                work = workpack.collectWorkBundle(studentId, cid, tmp)
                files = {}
                for part in work.get("parts", []):
                    fname = part.get("file")
                    path = os.path.join(tmp, fname)
                    if fname and os.path.isfile(path):
                        with open(path, "rb") as bf:
                            files[fname] = base64.b64encode(bf.read()).decode("ascii")
                _sendJson(conn, {
                    "action": ACTION_REPORT,
                    "student_id": studentId,
                    "classroom_id": cid,
                    "work": work,
                    "files": files,
                })
            finally:
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)
            continue

        if action == ACTION_APPLY_WORK:
            cid = response.get("classroom_id") or classroomId
            tmp = tempfile.mkdtemp(prefix="ychitsa-restore-")
            try:
                work = response.get("work") or {}
                with open(os.path.join(tmp, "work.json"), "w", encoding="utf-8") as f:
                    json.dump(work, f, indent=2)
                for fname, b64 in (response.get("files") or {}).items():
                    with open(os.path.join(tmp, fname), "wb") as bf:
                        bf.write(base64.b64decode(b64))
                results = workpack.applyWorkBundle(studentId, cid, tmp)
                ok = all(r.get("ok") for r in results) if results else True
                _sendJson(conn, {
                    "action": ACTION_APPLY_ACK,
                    "student_id": studentId,
                    "state_hash": _getCurrentStateHash(statePath),
                    "ok": ok,
                    "reason": json.dumps(results),
                })
            finally:
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)
            continue

        if action == ACTION_NOOP:
            return

        if action != ACTION_APPLY:
            print(f"[agent] unexpected action: {action}")
            return

        ok, reason, stateHash = _applyState(response, statePath, sharedSecret, studentId)
        _sendJson(conn, {
            "action": ACTION_APPLY_ACK,
            "student_id": studentId,
            "state_hash": stateHash or response.get("state_hash") or "",
            "ok": ok,
            "reason": reason,
        })
        if ok:
            print(f"[agent] state applied for {studentId}")
            _maybeRefresh()
        elif reason == "bad_signature" and not _loadJoinConfig().get("secret"):
            # Expected until the join ceremony hands over the classroom secret
            print("[agent] No class joined. Use the Join Classroom app to join a class.")
        else:
            print(f"[agent] apply failed: {reason}")
        return


def runAgent(studentId: str, udpPort: int, statePath: str, sharedSecret: str) -> None:
    print(f"[agent] starting — student_id={studentId}  state={statePath}")
    while True:
        try:
            cfg = _loadJoinConfig()
            classroomId = cfg.get("classroom_id") or "_unassigned"
            # Prefer join.json secret so Join Classroom works without restarting the agent
            secret = cfg.get("secret") or sharedSecret
            host, tcpPort = discoverTeacherHost(udpPort)
            if cfg.get("last_teacher_ip") != host or cfg.get("tcp_port") != tcpPort:
                cfg["last_teacher_ip"] = host
                cfg["tcp_port"] = tcpPort
                _saveJoinConfig(cfg)
            with socket.create_connection((host, tcpPort), timeout=15) as conn:
                conn.settimeout(120)
                _handleSession(conn, studentId, statePath, secret, classroomId)
            time.sleep(5)
        except TimeoutError as e:
            print(f"[agent] {e}")
            time.sleep(5)
        except Exception as e:
            print(f"[agent] retrying after error: {e}")
            time.sleep(3)


def runJoin(studentId: str, code: str, classroomIdHint: str = "") -> None:
    """Network join ceremony using timed teacher code."""
    host, tcpPort = discoverTeacherHost(DEFAULT_UDP_PORT)
    msg = {
        "action": ACTION_JOIN_REQUEST,
        "student_id": studentId,
        "device_id": _deviceId(),
        "code": code.strip().upper(),
        "classroom_id": classroomIdHint,
    }
    with socket.create_connection((host, tcpPort), timeout=15) as conn:
        conn.settimeout(30)
        _sendJson(conn, msg, compress=False)
        resp = _recvJson(conn)
    if resp.get("action") != ACTION_JOIN_ACCEPT:
        raise SystemExit(f"Join rejected: {resp.get('reason', resp)}")
    data = {
        "secret": resp["shared_secret"],
        "classroom_id": resp["classroom_id"],
        "device_id": _deviceId(),
        "last_teacher_ip": resp.get("teacher_ip") or host,
        "tcp_port": resp.get("tcp_port") or tcpPort,
    }
    _saveJoinConfig(data)
    print(f"[agent] Joined classroom {data['classroom_id']}")


def main() -> None:
    cfg = _loadJoinConfig()
    join_secret = cfg.get("secret")

    parser = argparse.ArgumentParser(description="CIS4900 student state agent")
    parser.add_argument("--student-id", default=os.environ.get("USER", "studentuser"))
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT)
    parser.add_argument("--state-path", default=DEFAULT_STATE_PATH)
    parser.add_argument(
        "--shared-secret",
        default=os.environ.get("CIS4900_STATE_SECRET") or join_secret or DEFAULT_SHARED_SECRET,
    )
    parser.add_argument("--join", action="store_true", help="Interactive join with teacher code")
    parser.add_argument("--join-code", default="", help="Non-interactive join code")
    parser.add_argument("--classroom-id", default="", help="Optional classroom id hint for join")
    args = parser.parse_args()

    if args.join or args.join_code:
        code = args.join_code
        if args.join and not code:
            print("Enter the join code from the teacher's Classroom Network panel.")
            code = input("Join code: ").strip()
        runJoin(args.student_id, code, args.classroom_id)
        cfg = _loadJoinConfig()
        args.shared_secret = cfg.get("secret") or args.shared_secret

    runAgent(args.student_id, args.udp_port, args.state_path, args.shared_secret)


if __name__ == "__main__":
    main()
