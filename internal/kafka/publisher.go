package kafka

import "github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/models"

// Publisher publishes ingested events to Kafka. Implementations must be nil-safe.
type Publisher interface {
	PublishEvent(ev models.Event)
	Close() error
}
