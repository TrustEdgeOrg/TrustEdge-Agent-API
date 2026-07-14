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
TYPE_ACTION_SUMMARY = "action_summary"
TYPE_PROCESS_START = "process_start"
TYPE_PROCESS_EXIT = "process_exit"

ALLOWED_EVENT_TYPES = frozenset(
    {
        TYPE_CLIENT_DETAILS,
        TYPE_NETWORK_SUMMARY,
        TYPE_ACTION_SUMMARY,
        TYPE_PROCESS_START,
        TYPE_PROCESS_EXIT,
    }
)

CONTENT_ENCODING_ZSTD = "zstd"
