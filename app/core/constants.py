"""Shared constants for ingest API."""

MAX_EVENTS_PER_BATCH = 100

STATUS_OK = "ok"
STATUS_ACCEPTED = "accepted"

ERR_UNAUTHORIZED = "unauthorized"
ERR_BAD_REQUEST = "bad request"
ERR_INVALID_JSON = "invalid json"
ERR_INTERNAL = "internal error"
ERR_NOT_FOUND = "not found"
ERR_DEVICE_ID_MISMATCH = "device_id mismatch"
ERR_UNKNOWN_EVENT_TYPE = "unknown event type"
ERR_BATCH_TOO_LARGE = "batch too large"

TYPE_CLIENT_DETAILS = "client_details"
TYPE_NETWORK_SUMMARY = "network_summary"
TYPE_NETWORK_CONNECTION = "network_connection"
TYPE_ACTION_SUMMARY = "action_summary"
TYPE_PROCESS_START = "process_start"
TYPE_PROCESS_EXIT = "process_exit"
TYPE_FILE_OPEN = "file_open"
TYPE_DRIVER_LOAD = "driver_load"
TYPE_SERVICE_INSTALL = "service_install"
TYPE_REGISTRY_PERSIST = "registry_persistence"
TYPE_KNOWN_AI_APP = "known_ai_app"

ALLOWED_EVENT_TYPES = frozenset(
    {
        TYPE_CLIENT_DETAILS,
        TYPE_NETWORK_SUMMARY,
        TYPE_NETWORK_CONNECTION,
        TYPE_ACTION_SUMMARY,
        TYPE_PROCESS_START,
        TYPE_PROCESS_EXIT,
        TYPE_FILE_OPEN,
        TYPE_DRIVER_LOAD,
        TYPE_SERVICE_INSTALL,
        TYPE_REGISTRY_PERSIST,
        TYPE_KNOWN_AI_APP,
    }
)

CONTENT_ENCODING_ZSTD = "zstd"
