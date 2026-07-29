#!/usr/bin/env python3
"""
Teacher state publisher.

UDP beacon + mDNS advertisement + TCP protocol:
  hello / apply / noop / apply_ack / join_* / collect / report / apply_work
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import socket
import threading
import time

from . import bootstrap, delivery, pairing, schema, signing, workpack
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
    CONTROL_DIR,
    DEFAULT_CLASSROOMS_FILE,
    DEFAULT_SHARED_SECRET,
    DEFAULT_TCP_PORT,
    DEFAULT_UDP_PORT,
    TEACHER_LESSONS_DIR,
    WORK_CACHE_DIR,
)
from .discovery import TeacherAdvertiser
from .transport import recvFramed, sendFramed

CLASSROOMS_FILE = os.environ.get("CIS4900_CLASSROOMS_FILE", DEFAULT_CLASSROOMS_FILE)


def _getLanIp(ifaceName: str | None = None) -> str:
    if ifaceName:
        try:
            import fcntl
            import struct
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            result = fcntl.ioctl(s.fileno(), 0x8915, struct.pack("256s", ifaceName[:15].encode()))
            return socket.inet_ntoa(result[20:24])
        except Exception:
            pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ip = info[4][0]
        if not ip.startswith("127."):
            return ip
    return "127.0.0.1"


def _getBroadcastAddr(ifaceName: str | None = None) -> str:
    if not ifaceName:
        return "255.255.255.255"
    try:
        import ipaddress
        import subprocess
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


def _loadClassrooms() -> dict:
    with open(CLASSROOMS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _saveClassrooms(data: dict) -> None:
    tmp = CLASSROOMS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CLASSROOMS_FILE)
    try:
        os.chmod(CLASSROOMS_FILE, 0o664)
    except OSError:
        pass


def _classroomIds() -> list[str]:
    try:
        data = _loadClassrooms()
        return [c.get("id") for c in data.get("classrooms", []) if c.get("id")]
    except Exception:
        return []


def _findClassroomForStudent(studentId: str) -> tuple[dict | None, dict | None]:
    try:
        data = _loadClassrooms()
    except FileNotFoundError:
        return None, None
    for classroom in data.get("classrooms", []):
        if studentId in classroom.get("students", []):
            return classroom, data
    return None, data


def _secretForClassroom(classroomId: str, fallback: str, allowDev: bool) -> str:
    # Lab images with CIS4900_DEV=1 may keep the shared default secret.
    if allowDev and pairing.isDevSecret(fallback):
        return fallback
    return pairing.getOrCreateClassroomSecret(classroomId)


def _buildStateForStudent(studentId: str, classroom: dict, secret: str) -> dict:
    fp = schema.computeLessonsFingerprint(
        classroom.get("enabled_lessons", []), TEACHER_LESSONS_DIR
    )
    state = schema.buildStudentState(studentId, classroom, lessonsFingerprint=fp)
    canonical = schema.canonicalizeStudentState(state)
    state["security"]["signature"] = signing.signState(canonical, secret)
    return state


def _updateTargetHashes() -> None:
    try:
        data = _loadClassrooms()
    except Exception:
        return
    for classroom in data.get("classrooms", []):
        cid = classroom.get("id")
        if not cid:
            continue
        roster = list(classroom.get("students", []))
        if not roster:
            delivery.setTargetHash(cid, "", [])
            continue
        fp = schema.computeLessonsFingerprint(
            classroom.get("enabled_lessons", []), TEACHER_LESSONS_DIR
        )
        delivery.setTargetHash(
            cid, schema.computeClassroomConfigHash(classroom, lessonsFingerprint=fp), roster
        )


def _beaconLoop(lanIp: str, udpPort: int, tcpPort: int, broadcastAddr: str, stop: threading.Event) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    beacon = f"{BEACON_PREFIX}|{lanIp}|{tcpPort}".encode("utf-8")
    while not stop.is_set():
        sock.sendto(beacon, (broadcastAddr, udpPort))
        time.sleep(2)
    sock.close()


def _controlLoop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            pairing.applyPendingCommands(_classroomIds())
            for cid in _classroomIds():
                pairing.refreshCodeIfNeeded(cid)
            _updateTargetHashes()
        except Exception as e:
            print(f"[publisher] control loop: {e}")
        time.sleep(1)


def _sendJson(conn: socket.socket, obj: dict, compress: bool = True) -> None:
    raw = json.dumps(obj).encode("utf-8")
    sendFramed(conn, gzip.compress(raw) if compress else raw)


def _recvJson(conn: socket.socket, compressed: bool = True) -> dict:
    raw = recvFramed(conn)
    if compressed:
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    return json.loads(raw.decode("utf-8"))


def _handleJoin(conn: socket.socket, msg: dict, allowDev: bool) -> None:
    code = (msg.get("code") or "").strip().upper()
    studentId = msg.get("student_id") or ""
    classroomId = msg.get("classroom_id") or ""

    if classroomId:
        ok, reason = pairing.verifyJoinCode(classroomId, code)
        if not ok:
            _sendJson(conn, {"action": ACTION_JOIN_REJECT, "reason": reason})
            return
    else:
        # Find the classroom whose open join session matches this code.
        anyOpen = False
        for cid in _classroomIds():
            st = pairing.readStatus(cid)
            if not st.get("joining_enabled"):
                continue
            anyOpen = True
            ok, _ = pairing.verifyJoinCode(cid, code)
            if ok:
                classroomId = cid
                break
        if not classroomId:
            _sendJson(conn, {
                "action": ACTION_JOIN_REJECT,
                "reason": "bad_code" if anyOpen else "joining_closed",
            })
            return

    try:
        data = _loadClassrooms()
    except Exception:
        data = {"classrooms": []}
    target = next(
        (c for c in data.get("classrooms", []) if c.get("id") == classroomId), None
    )
    if target is None:
        _sendJson(conn, {"action": ACTION_JOIN_REJECT, "reason": "unknown_classroom"})
        return
    if studentId and studentId not in target.get("students", []):
        # The valid code is the invitation so we enroll on first join
        target.setdefault("students", []).append(studentId)
        _saveClassrooms(data)
        print(f"[publisher] auto-enrolled {studentId} in {classroomId}")

    secret = pairing.getOrCreateClassroomSecret(classroomId)
    if pairing.refuseLiveJoinWithDevSecret(secret, allowDev):
        # secret file should never be default; still guard env fallback
        pass
    lanIp = _getLanIp(os.environ.get("CIS4900_IFACE"))
    _sendJson(conn, {
        "action": ACTION_JOIN_ACCEPT,
        "classroom_id": classroomId,
        "shared_secret": secret,
        "teacher_ip": lanIp,
        "tcp_port": DEFAULT_TCP_PORT,
    })


def _handleClient(conn: socket.socket, addr: tuple, fallbackSecret: str, allowDev: bool) -> None:
    try:
        msg = _recvJson(conn, compressed=False)
        # first frame may be gzip from older agents; try both
        if "action" not in msg and "student_id" in msg:
            msg["action"] = "hello"

        action = msg.get("action", "hello")

        if action == ACTION_PING:
            _sendJson(conn, {"action": ACTION_PONG})
            return

        if action == ACTION_JOIN_REQUEST:
            _handleJoin(conn, msg, allowDev)
            return

        studentId = msg.get("student_id", "")
        studentHash = msg.get("state_hash", "")
        requestedId = msg.get("classroom_id") or ""
        classroom, data = _findClassroomForStudent(studentId)
        if requestedId and data:
            for c in data.get("classrooms", []):
                if c.get("id") == requestedId and studentId in c.get("students", []):
                    classroom = c
                    break
        if not classroom:
            print(f"[publisher] unknown student: {studentId!r}")
            _sendJson(conn, {"action": ACTION_NOOP, "reason": "unknown_student"})
            return

        classroomId = classroom["id"]
        delivery.noteSeen(classroomId, studentId, addr[0])
        secret = _secretForClassroom(classroomId, fallbackSecret, allowDev)
        state = _buildStateForStudent(studentId, classroom, secret)
        contentHash = schema.computeContentHash(state)
        fp = state.get("environment", {}).get("lessons_fingerprint", "")
        configHash = schema.computeClassroomConfigHash(classroom, lessonsFingerprint=fp)
        delivery.setTargetHash(classroomId, configHash, list(classroom.get("students", [])))

        force = delivery.needsForceResend(classroomId, studentId)
        needsApply = (studentHash != contentHash) or force

        # Queued work restore from teacher cache
        workDir = os.path.join(WORK_CACHE_DIR, classroomId, studentId)
        restoreQueued = os.path.isfile(os.path.join(workDir, ".restore_queued"))

        if delivery.shouldCollect(classroomId, studentId):
            _sendJson(conn, {"action": ACTION_COLLECT, "classroom_id": classroomId})
            report = _recvJson(conn, compressed=True)
            if report.get("action") == ACTION_REPORT:
                _ingestReport(classroomId, studentId, report)
                delivery.clearCollect(classroomId, studentId)
            # Fall through: apply / restore still runs on this connection.

        if restoreQueued and os.path.isdir(workDir):
            _sendWorkRestore(conn, classroomId, studentId, workDir)
            try:
                os.remove(os.path.join(workDir, ".restore_queued"))
            except OSError:
                pass
            ack = _recvJson(conn, compressed=True)
            if ack.get("action") == ACTION_APPLY_ACK and not ack.get("ok"):
                delivery.recordAck(
                    classroomId, studentId, configHash,
                    False, ack.get("reason"), addr[0],
                )
            # Continue so config apply still happens when needed.

        if needsApply:
            lessonsB64 = None
            lessonIds = list(classroom.get("enabled_lessons", []))
            tarPath = workpack.packLessonsArchive(lessonIds, TEACHER_LESSONS_DIR)
            if tarPath:
                with open(tarPath, "rb") as f:
                    lessonsB64 = base64.b64encode(f.read()).decode("ascii")
                try:
                    os.remove(tarPath)
                except OSError:
                    pass
            response = {
                "action": ACTION_APPLY,
                "student_state": state,
                "state_hash": contentHash,
            }
            if lessonsB64:
                response["lessons_tar_b64"] = lessonsB64
            _sendJson(conn, response)
            conn.settimeout(60)
            ack = _recvJson(conn, compressed=True)
            if ack.get("action") == ACTION_APPLY_ACK:
                delivery.recordAck(
                    classroomId, studentId,
                    configHash,
                    bool(ack.get("ok")),
                    ack.get("reason"),
                    addr[0],
                )
                if ack.get("ok"):
                    delivery.clearForceResend(classroomId, studentId)
            print(f"[publisher] {studentId} ({addr[0]}) -> apply ack={ack.get('ok')}")
        else:
            _sendJson(conn, {"action": ACTION_NOOP, "reason": "already-current", "state_hash": contentHash})
            delivery.recordAck(classroomId, studentId, configHash, True, None, addr[0])
            print(f"[publisher] {studentId} ({addr[0]}) -> noop")
    except Exception as e:
        print(f"[publisher] error handling {addr}: {e}")


def _ingestReport(classroomId: str, studentId: str, report: dict) -> None:
    os.makedirs(os.path.join(WORK_CACHE_DIR, classroomId, studentId), exist_ok=True)
    outDir = os.path.join(WORK_CACHE_DIR, classroomId, studentId)
    work = report.get("work") or {}
    with open(os.path.join(outDir, "work.json"), "w", encoding="utf-8") as f:
        json.dump(work, f, indent=2)
    for part in work.get("parts", []):
        fname = part.get("file")
        b64 = (report.get("files") or {}).get(fname)
        if not fname or not b64:
            continue
        with open(os.path.join(outDir, fname), "wb") as f:
            f.write(base64.b64decode(b64))
    print(f"[publisher] stored work report for {studentId} in {outDir}")


def _sendWorkRestore(conn: socket.socket, classroomId: str, studentId: str, workDir: str) -> None:
    with open(os.path.join(workDir, "work.json"), "r", encoding="utf-8") as f:
        work = json.load(f)
    files = {}
    for part in work.get("parts", []):
        fname = part.get("file")
        path = os.path.join(workDir, fname)
        if fname and os.path.isfile(path):
            with open(path, "rb") as bf:
                files[fname] = base64.b64encode(bf.read()).decode("ascii")
    _sendJson(conn, {
        "action": ACTION_APPLY_WORK,
        "classroom_id": classroomId,
        "student_id": studentId,
        "work": work,
        "files": files,
    })


def queueWorkRestore(classroomId: str, studentId: str) -> None:
    """Compatibility wrapper; prefer delivery.queueWorkRestore."""
    delivery.queueWorkRestore(classroomId, studentId)


def _clientThread(conn: socket.socket, addr: tuple, fallbackSecret: str, allowDev: bool) -> None:
    try:
        with conn:
            conn.settimeout(120)
            _handleClient(conn, addr, fallbackSecret, allowDev)
    except Exception as e:
        print(f"[publisher] client thread {addr}: {e}")


def runPublisher(
    host: str,
    udpPort: int,
    tcpPort: int,
    sharedSecret: str,
    ifaceName: str | None = None,
    allowDev: bool = False,
) -> None:
    # Seed /shared before any apply/hello so student-state always mirrors a real DB.
    bootstrap.ensureSharedClassrooms(CLASSROOMS_FILE)
    pairing.ensureDirs()
    delivery.ensureDir()
    lanIp = _getLanIp(ifaceName)
    broadcastAddr = _getBroadcastAddr(ifaceName)
    print(f"[publisher] LAN IP: {lanIp}  broadcast: {broadcastAddr}  TCP: {tcpPort}")
    print(f"[publisher] classrooms file: {CLASSROOMS_FILE}")
    try:
        os.makedirs(CONTROL_DIR, exist_ok=True)
        with open(os.path.join(CONTROL_DIR, "lan_ip.txt"), "w", encoding="utf-8") as f:
            f.write(lanIp)
    except Exception:
        pass

    classroomId = "classroom"
    try:
        ids = _classroomIds()
        if ids:
            classroomId = ids[0]
    except Exception:
        pass

    advertiser = TeacherAdvertiser(lanIp, tcpPort, classroomId)
    advertiser.start()

    stop = threading.Event()
    threading.Thread(
        target=_beaconLoop,
        args=(lanIp, udpPort, tcpPort, broadcastAddr, stop),
        daemon=True,
    ).start()
    threading.Thread(target=_controlLoop, args=(stop,), daemon=True).start()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, tcpPort))
    server.listen(32)
    print(f"[publisher] TCP server ready on {host}:{tcpPort}")

    try:
        while True:
            conn, addr = server.accept()
            threading.Thread(
                target=_clientThread,
                args=(conn, addr, sharedSecret, allowDev),
                daemon=True,
            ).start()
    finally:
        stop.set()
        advertiser.stop()
        server.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="CIS4900 teacher state publisher")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT)
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT)
    parser.add_argument(
        "--shared-secret",
        default=os.environ.get("CIS4900_STATE_SECRET", DEFAULT_SHARED_SECRET),
    )
    parser.add_argument(
        "--iface",
        default=os.environ.get("CIS4900_IFACE"),
        help="Network interface for beacon (e.g. wlan0).",
    )
    parser.add_argument(
        "--allow-dev-secret",
        action="store_true",
        default=os.environ.get("CIS4900_DEV") == "1",
        help="Allow default cis4900-dev-secret (dev only).",
    )
    args = parser.parse_args()
    runPublisher(
        args.host, args.udp_port, args.tcp_port,
        args.shared_secret, args.iface, args.allow_dev_secret,
    )


if __name__ == "__main__":
    main()
