# Delivery

Enrolled-list status for classroom config (apps, lessons) after publish.

## Purpose

Teacher publishes a lesson at night. Offline students are **Pending**. In the morning their agent connects, applies full current state, sends APPLY_ACK, and become **Delivered**. Teacher does not have to click Resend for that path.

## Store

Path: `/shared/classroom-delivery/<classroom_id>.json`

Module: `network.delivery`

```json
{
  "classroom_id": "biology-p3",
  "target_state_hash": "abc...",
  "collect_all": false,
  "students": {
    "alice": {
      "acked_hash": "abc...",
      "acked_at": "2026-07-20T15:48:32-04:00",
      "last_error": null,
      "force_resend": false,
      "collect_requested": false,
      "last_seen_ip": "192.168.1.50"
    }
  }
}
```

## Protocol (not HTTP 200)

After a successful local apply, the agent sends on the **same TCP connection**:

```json
{"action":"apply_ack","student_id":"...","state_hash":"...","ok":true}
```

Publisher calls `delivery.recordAck`.

## Automatic Pending path

1. Classroom config changes (publish lesson, toggle apps).
2. Publisher recomputes `target_state_hash` via `schema.computeClassroomConfigHash` (shared by all students; ignores per-student id and timestamps).
3. Offline students show Pending in Classroom Manager.
4. Student agent connects with hello (`state_hash` = `schema.computeContentHash` of local state).
5. If content hash differs or `force_resend`, publisher sends apply (plus optional lessons tar).
6. Agent applies, sends apply_ack.
7. Publisher records `acked_hash` = classroom config hash. UI shows Delivered.

## UI statuses

| Label | Meaning |
|-------|---------|
| Delivered · time | acked_hash matches target |
| Pending · not yet synced | never acked |
| Pending · last ok: time | older ack, new target |
| Failed · time | last ack ok false |

## New student

Added to roster as Pending. First successful sync gets the **full current** classroom state (not a queue of old pushes). Same as apps today.

## Resend

`delivery.markForceResend` / `markForceResendAllPending` only set flags.

Students do not run a TCP server. The teacher cannot dial them. Clearance is on the next agent hello.

## Code map

| Piece | Role |
|-------|------|
| `delivery.py` | store + uiStatus |
| `publisher._handleClient` | apply + wait for apply_ack |
| `agent._handleSession` | apply then apply_ack (socket stays open) |
| `classroom_manager.py` | enrolled list + poll every 2s |
