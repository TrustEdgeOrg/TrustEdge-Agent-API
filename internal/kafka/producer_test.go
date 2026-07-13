package kafka

import (
	"testing"

	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/models"
)

func TestNewProducerEmptyBrokers(t *testing.T) {
	p, err := NewProducer("", "trustedge.agent.events", nil)
	if err != nil {
		t.Fatal(err)
	}
	if p != nil {
		t.Fatal("expected nil producer")
	}
}

func TestSplitBrokers(t *testing.T) {
	got := splitBrokers(" redpanda:9092 , kafka:9093 ")
	if len(got) != 2 || got[0] != "redpanda:9092" || got[1] != "kafka:9093" {
		t.Fatalf("splitBrokers=%v", got)
	}
}

func TestProducerNilSafe(t *testing.T) {
	var p *Producer
	p.PublishEvent(models.Event{DeviceID: "dev_1"})
	if err := p.Close(); err != nil {
		t.Fatal(err)
	}
}
