package constants

// Plain-text HTTP error bodies returned by trustedge-agent-api.
const (
	ErrUnauthorized   = "unauthorized"
	ErrBadRequest     = "bad request"
	ErrInvalidJSON    = "invalid json"
	ErrInternal       = "internal error"
	ErrNotFound       = "not found"
	ErrDeviceIDMismatch = "device_id mismatch"
	ErrUnknownEventType = "unknown event type"
	ErrBatchTooLarge    = "batch too large"
)

// MaxEventsPerBatch is the ingest limit for POST /v1/events batch payloads.
const MaxEventsPerBatch = 100

// status field values in JSON HTTP responses.
const (
	StatusOK       = "ok"
	StatusAccepted = "accepted"
)
