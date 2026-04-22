# State Sync Network

This system synchronizes classroom configurations (apps, lessons, and web restrictions) from a teacher’s machine to student devices over a local network with no wifi

## Components
- `publisher.py`: teacher service that broadcasts UDP beacons so students can find the teacher and serves signed state data over TCP
 - `agent.py`: student service that discovers the teacher, verifies data authenticity, and updates local configuration files
- `schema.py`: Defines the JSON structure and handles data hashing to detect changes
- `signing.py`: Provides HMAC-SHA256 signing to ensure only authorized teachers can update student devices
- `transport.py`: UDP/TCP framing 
- `apply.py`: Performs atomic file writes to ensure local configurations are never corrupted during an update

## Guide
### Teacher (Publisher)
- The teacher machine acts as the beacon for the system
  - Run the publisher: `bash network.sh`
  - Make note the 8-character Join Code displayed in the terminal. Provide this to students for their initial setup.

### Student (Agent)
- First-time setup: Run `python3 -m network.agent --join` and enter the teacher's Join Code. This saves the shared secret locally.
- Normal operation: The agent runs as a systemd service (student-agent@username.service) and handles updates in the background.

## How it Works
- Discovery: The teacher broadcasts a UDP beacon every 2 seconds on port 49001.
- Connection: The student hears the beacon and connects to the teacher via TCP on port 49002.
- Validation: The student sends its current state hash. If the teacher has newer data, it sends a gzip-compressed, HMAC-signed JSON payload.
- Application: The student verifies the signature and timestamp. If valid, it writes the new state to ~/.cache/cis4900/student-state.json and /var/lib/cis4900/student-state.json.

## Security and Reliability
- Authentication: All data is signed with HMAC-SHA256. Unauthorized payloads are rejected.
- Replay Protection: Payloads include a UTC timestamp. Students reject any message older than 5 minutes.
- Atomic Writes: Data is written to a temporary file before being moved to the final destination, preventing partial writes if the process is interrupted.

## Troubleshooting
- Docker: If running the teacher in Docker, you must use --network host so the UDP broadcast can reach the physical network.
- Discovery Failures: If UDP is blocked on your network, you can bypass discovery by setting the teacher's IP manually:
  - TEACHER_IP=192.168.1.10 python3 -m network.agent
- Logs: Use journalctl -u student-agent -f to monitor sync activity on student machines.