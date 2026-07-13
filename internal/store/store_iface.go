package store

import "github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/models"

// EventStore persists device registration and telemetry events.
type EventStore interface {
	Register(req models.RegisterRequest) (*models.RegisterResponse, error)
	DeviceIDForToken(token string) (string, bool)
	AddEvent(ev models.Event) error
	GetClient(deviceID string, limit int) (*models.ClientView, bool)
	RedisEnabled() bool
	Close() error
}
