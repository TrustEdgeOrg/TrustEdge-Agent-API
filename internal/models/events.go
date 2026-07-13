package models

import (
	"time"

	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/clock"
)

func NewEvent(clk clock.Clock, deviceID, typ string, payload map[string]any) Event {
	if clk == nil {
		clk = clock.Real{}
	}
	now := clk.Now()
	return Event{
		EventID:  clk.NewEventID(now),
		DeviceID: deviceID,
		Type:     typ,
		TS:       now,
		Payload:  payload,
	}
}

type Event struct {
	EventID  string         `json:"event_id"`
	DeviceID string         `json:"device_id"`
	Type     string         `json:"type"`
	TS       time.Time      `json:"ts"`
	Payload  map[string]any `json:"payload"`
}

type EventBatch struct {
	Events []Event `json:"events"`
}

type ClientDetails struct {
	Hostname     string `json:"hostname"`
	OS           string `json:"os"`
	OSVersion    string `json:"os_version"`
	Arch         string `json:"arch"`
	AgentVersion string `json:"agent_version"`
	Timezone     string `json:"timezone"`
	Status       string `json:"status"`
	UptimeSec    int64  `json:"uptime_sec"`
}

type PortCount struct {
	Port  int `json:"port"`
	Count int `json:"count"`
}

type NetworkSummary struct {
	PublicIP                 string      `json:"public_ip"`
	NetworkType              string      `json:"network_type"`
	ListeningCount           int         `json:"listening_count"`
	EstablishedCount         int         `json:"established_count"`
	TopRemotePorts           []PortCount `json:"top_remote_ports"`
	ForegroundAppConnections int         `json:"foreground_app_connections"`
}

type AppFocus struct {
	AppName     string  `json:"app_name"`
	BundleID    string  `json:"bundle_id"`
	DurationSec float64 `json:"duration_sec"`
}

type ActionSummary struct {
	WindowStart time.Time  `json:"window_start"`
	WindowEnd   time.Time  `json:"window_end"`
	Focus       []AppFocus `json:"focus"`
	Presence    string     `json:"presence"`
	IdleSec     float64    `json:"idle_sec"`
	AppSwitches int        `json:"app_switches"`
}

type RegisterRequest struct {
	DeviceID     string `json:"device_id,omitempty"`
	Hostname     string `json:"hostname,omitempty"`
	OS           string `json:"os,omitempty"`
	OSVersion    string `json:"os_version,omitempty"`
	Arch         string `json:"arch,omitempty"`
	AgentVersion string `json:"agent_version,omitempty"`
}

type RegisterResponse struct {
	DeviceID    string `json:"device_id"`
	DeviceToken string `json:"device_token"`
}

type ClientView struct {
	DeviceID     string         `json:"device_id"`
	LastDetails  map[string]any `json:"last_details,omitempty"`
	LastSeenAt   *time.Time     `json:"last_seen_at,omitempty"`
	RecentEvents []Event        `json:"recent_events"`
}
