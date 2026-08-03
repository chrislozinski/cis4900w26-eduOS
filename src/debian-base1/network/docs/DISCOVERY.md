# Discovery

How students find the teacher on the LAN.

## Architecture

```text
Teacher                          Student
-------                          -------
publisher.py
  TeacherAdvertiser (mDNS)
  UDP beacon 49001
  TCP listen 49002  <---------  agent discovers then connects
```

## Why UDP alone was not enough

The old agent listened for a UDP broadcast beacon. That fails when:

- Docker bridge mode drops or isolates broadcast
- The teacher DHCP address changes and the student only remembered an IP that is gone
- The student briefly left the room and needs to reconnect without standing next to the teacher

## Discovery waterfall (student)

Implemented in `network.agent.discoverTeacherHost`:

1. `TEACHER_IP` env (and optional `TEACHER_TCP_PORT`)
2. mDNS browse for `_ychitsa._tcp.local.` via `network.discovery.discoverTeacher`
3. `last_teacher_ip` from `~/.config/cis4900/join.json` plus a TCP connect check
4. UDP beacon on port 49001 (original path)

## mDNS vs Avahi

We use **python-zeroconf** (`TeacherAdvertiser` / `discoverTeacher`).

Do **not** enable `avahi-daemon` at the same time. Both want UDP 5353.

Optional: `avahi-utils` for manual `avahi-browse` diagnostics only.

## Docker

Default compose uses **bridge** and publishes:

- `3389` — xrdp Remote Desktop
- `49002` — teacher TCP

mDNS/UDP do not leave the Docker bridge. For laptop↔container sync on Docker Desktop, set `TEACHER_IP`.

To test mDNS from a Windows machine: run a **Linux VM with bridged networking**, run Docker inside that VM, then:

`docker compose --profile mdns up debian-mdns`

That uses `network_mode: host` on the VM’s LAN interface. RDP to `<vm-ip>:3389`.

## Honest limit (VLANs)

mDNS needs multicast on the same LAN segment.

If school VLANs filter multicast between rooms, students will not see the teacher via mDNS. Use `last_teacher_ip`, `TEACHER_IP`, or a later school server. That is network policy, not a bug in this code.

## Files

| File | Role |
|------|------|
| `discovery.py` | mDNS register/browse, `tcpReachable` |
| `agent.py` | waterfall |
| `publisher.py` | starts `TeacherAdvertiser`, UDP beacon loop |
| `constants.py` | `MDNS_SERVICE_TYPE`, ports |
