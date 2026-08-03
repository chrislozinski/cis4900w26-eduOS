# Join Classroom

Student app for one-time classroom pairing.

## Source

`join-classroom.py` in this folder.

Installed for the launcher like Library and MakeCode:

- build copies it to `/etc/skel/.config/launcher/join-classroom.py`
- runtime command: `python3 ~/.config/launcher/join-classroom.py`

## Behavior

Calls `network.agent.runJoin` with the roster username and the teacher's timed join code.
Writes `~/.config/cis4900/join.json`. The background `student-agent@user` service then syncs using that secret.
