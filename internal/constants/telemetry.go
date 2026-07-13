package constants

// Event envelope types (POST /v1/events).
const (
	TypeClientDetails  = "client_details"
	TypeNetworkSummary = "network_summary"
	TypeActionSummary  = "action_summary"
	TypeProcessStart   = "process_start"
	TypeProcessExit    = "process_exit"
)

// action_summary.presence values.
const (
	PresenceActive = "active"
	PresenceIdle   = "idle"
)

// client_details.status values.
const (
	StatusOnline = "online"
)

// network_summary.network_type values.
const (
	NetworkTypeWiFi     = "wifi"
	NetworkTypeEthernet = "ethernet"
	NetworkTypeUnknown  = "unknown"
)
