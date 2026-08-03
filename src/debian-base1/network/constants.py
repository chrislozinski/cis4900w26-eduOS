STATE_SCHEMA_VERSION  = 1
DEFAULT_UDP_PORT      = 49001
DEFAULT_TCP_PORT      = 49002
DEFAULT_STATE_PATH    = "/var/lib/cis4900/student-state.json"
DEFAULT_SHARED_SECRET = "cis4900-dev-secret"
BEACON_PREFIX         = "cis4900-state-sync"
# 7 days: lab machines and Docker containers often have badly drifted clocks
MAX_TIMESTAMP_AGE_SECONDS = 604800
JOIN_CONFIG_PATH      = "~/.config/cis4900/join.json"

# Shared with Classroom Manager / Lesson Builder
DEFAULT_CLASSROOMS_FILE = "/shared/classrooms.json"
TEACHER_LESSONS_DIR     = "/shared/teacher-lessons"
STUDENT_LESSONS_DIR     = "/shared/teacher-lessons"

MDNS_SERVICE_TYPE = "_ychitsa._tcp.local."
MDNS_SERVICE_NAME = "ychitsa-teacher"
JOIN_CODE_TTL_SECONDS = 300

CONTROL_DIR          = "/shared/cis4900-control"
SECRETS_DIR          = "/shared/cis4900-secrets"
WORK_CACHE_DIR       = "/shared/classroom-work"
DELIVERY_DIR         = "/shared/classroom-delivery"
PAIRING_STATUS_GLOB  = "pairing-{classroom_id}.json"

# Protocol action names
ACTION_HELLO       = "hello"
ACTION_APPLY       = "apply"
ACTION_NOOP        = "noop"
ACTION_APPLY_ACK   = "apply_ack"
ACTION_JOIN_REQUEST = "join_request"
ACTION_JOIN_ACCEPT  = "join_accept"
ACTION_JOIN_REJECT  = "join_reject"
ACTION_COLLECT      = "collect"
ACTION_REPORT       = "report"
ACTION_APPLY_WORK   = "apply_work"
ACTION_PING         = "ping"
ACTION_PONG         = "pong"
