# Pairing

Timed join codes and per-classroom secrets.

## Threat model

- Goal: stop using the baked-in `cis4900-dev-secret` as the live classroom secret.
- Join code is short-lived (5 minutes) and only works while the teacher has joining open.
- Traffic is still plaintext TCP on the LAN. TLS is out of scope for this pass.

## Ceremony

1. Teacher opens Classroom Manager, opens a class, Classroom Network, **Open joining**.
2. UI writes a command file. Publisher applies it and shows a 6-character code with expiry.
3. Student runs Join Classroom (or `python3 -m network.agent --join-code CODE`).
4. Agent discovers teacher, sends `join_request`.
5. Publisher verifies code hash and roster, returns `join_accept` with per-classroom secret.
6. Student saves `~/.config/cis4900/join.json`.

## Control IPC (Classroom Manager vs publisher)

These are separate processes. They share files under `/shared/cis4900-control/`:

| Path | Writer | Reader |
|------|--------|--------|
| `pairing-<id>.cmd` | Classroom Manager (`pairing.writeCommand`) | publisher control loop |
| `pairing-<id>.json` | publisher (`openJoining` / `closeJoining`) | Classroom Manager (`readStatus`) |
| `lan_ip.txt` | publisher | Classroom Manager (diagnostic) |

Commands: `open`, `close`, `refresh`.

## Secrets

Per-classroom secret: `/shared/cis4900-secrets/<classroom_id>` (mode 0640).

Created on first Open joining via `pairing.getOrCreateClassroomSecret`.

Default `cis4900-dev-secret` is for `CIS4900_DEV=1` lab images only.

## Message shapes

`join_request`:

```json
{"action":"join_request","student_id":"...","device_id":"...","code":"ABC123","classroom_id":"..."}
```

`join_accept`:

```json
{"action":"join_accept","classroom_id":"...","shared_secret":"...","teacher_ip":"...","tcp_port":49002}
```

`join_reject`: `{"action":"join_reject","reason":"bad_code|joining_closed|code_expired|not_on_roster"}`

## join.json (student)

```json
{
  "secret": "...",
  "classroom_id": "...",
  "device_id": "...",
  "last_teacher_ip": "...",
  "tcp_port": 49002
}
```

## Files

| File | Role |
|------|------|
| `pairing.py` | session state machine, secrets, IPC helpers |
| `publisher.py` | `_handleJoin`, control loop |
| `agent.py` | `runJoin` |
| `widgets/joinClassroom/join-classroom.py` | GTK UI (installed to `~/.config/launcher/` like Library/MakeCode) |
