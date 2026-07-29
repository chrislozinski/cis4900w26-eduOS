# State Sync Network

Classroom config sync, timed pairing, mDNS discovery, delivery status, and student work collect/export.

## Docs

| Doc | Topic |
|-----|-------|
| [docs/DISCOVERY.md](docs/DISCOVERY.md) | mDNS, UDP, Docker host networking, VLAN limit |
| [docs/PAIRING.md](docs/PAIRING.md) | Join codes, secrets, IPC |
| [docs/ARCHIVE.md](docs/ARCHIVE.md) | Export/import, work parts, MakeCode restore |
| [docs/DELIVERY.md](docs/DELIVERY.md) | APPLY_ACK, Pending/Delivered, Resend |
| [docs/PROTOCOL.md](docs/PROTOCOL.md) | Ports and message catalog |

## Architecture

```text
Teacher                          Student
-------                          -------
Classroom Manager
  pairing / delivery / archive control files
publisher.py
  mDNS + UDP beacon
  TCP 49002  <----------------  agent.py (waterfall discovery)
  apply / collect / apply_work
```

## Quick start

### Teacher

```bash
# systemd on ISO
systemctl start teacher-publisher

# or
CIS4900_CLASSROOMS_FILE=/shared/classrooms.json python3 -m network.publisher
```

Open **Classrooms** (Classroom Manager): Open joining, show code, Collect work, Export.

### Student

```bash
python3 -m network.agent --join-code ABC123
# or use the Join Classroom app
```

Agent continues in the background (systemd `student-agent@user`).

### Docker

Bridge + published ports so Remote Desktop works (including Windows Docker Desktop).

```bash
# Teacher + RDP
docker compose up
# Remote Desktop → localhost:3389

# Student only (set TEACHER_IP — bridge mode has no mDNS to the LAN)
TEACHER_IP=192.168.1.20 docker compose --profile student-agent up student-agent
```

**mDNS on a Windows PC:** use a **Linux VM** with **bridged** networking (VM gets a real LAN IP), install Docker *inside the VM*, then:

```bash
docker compose --profile mdns up debian-mdns
# RDP → <vm-lan-ip>:3389
# Student on another device: leave TEACHER_IP unset so mDNS/UDP can find it
```

Classrooms file: `/shared/classrooms.json` (volume `./shared:/shared`).

## Components

| Module | Role | Notes |
|--------|------|-------|
| `publisher.py` | Teacher server | Extended in place (not a replacement) |
| `agent.py` | Student client | Extended in place |
| `schema.py` / `signing.py` / `apply.py` / `transport.py` | Original config-sync core | Kept and still used every apply |
| `pairing.py` | Join session | New |
| `discovery.py` | mDNS | New |
| `delivery.py` | ACK store | New |
| `workpack.py` | Work parts + lesson tars | New |
| `archive.py` | Timestamped export/import | New |
| `constants.py` | Ports, paths, action names | Extended in place |

Nothing in this package is a dead duplicate of another file. Older modules were updated or left as shared primitives; newer modules add pairing, discovery, delivery, and work.

## Security notes

- HMAC-SHA256 on student_state.
- Per-classroom secrets under `/shared/cis4900-secrets/`.
- Default `cis4900-dev-secret` only with `CIS4900_DEV=1`.
- LAN plaintext TCP (no TLS in this pass).
