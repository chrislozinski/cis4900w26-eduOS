# Protocol catalog

Ports and TCP message actions for Ychitsa classroom networking.

## Ports

| Port | Proto | Role |
|------|-------|------|
| 49001 | UDP | Beacon fallback |
| 49002 | TCP | All framed messages (config, pairing, work, delivery ack) |
| 5353 | UDP | mDNS (owned by python-zeroconf) |

There is **no HTTP API** in v1.

Framing: 4-byte big-endian length + payload (`transport.sendFramed` / `recvFramed`). Many payloads are gzip JSON.

Students connect **outbound** to the teacher. Students do not listen.

On one hello, the teacher may send **collect**, then **apply_work**, then **apply** or **noop** before the socket closes. Agent `_handleSession` loops until apply/noop finishes.

## Classrooms file

Default: `/shared/classrooms.json` (`CIS4900_CLASSROOMS_FILE`).

Same file as Classroom Manager and Lesson Builder.

## Message actions

| action | Direction | Purpose | Detail doc |
|--------|-----------|---------|------------|
| hello | student to teacher | student_id + state_hash | DELIVERY |
| apply | teacher to student | signed student_state (+ optional lessons_tar_b64) | DELIVERY, ARCHIVE |
| noop | teacher to student | already current | DELIVERY |
| apply_ack | student to teacher | confirm apply ok/fail | DELIVERY |
| join_request | student to teacher | timed code pairing | PAIRING |
| join_accept | teacher to student | secret + classroom_id | PAIRING |
| join_reject | teacher to student | reason | PAIRING |
| collect | teacher to student | please REPORT work | ARCHIVE |
| report | student to teacher | work.json + part files b64 | ARCHIVE |
| apply_work | teacher to student | restore work bundle | ARCHIVE |
| ping / pong | either | reachability | DISCOVERY |

## Control files (not on the wire)

Under `/shared/cis4900-control/`: pairing commands/status, `lan_ip.txt`.

See PAIRING.md.

## Related paths

| Path | Role |
|------|------|
| `/shared/cis4900-secrets/` | per-classroom HMAC secrets |
| `/shared/classroom-work/` | collected student work cache |
| `/shared/classroom-delivery/` | delivery ACK store |
| `/shared/teacher-lessons/` | published lesson bodies |
