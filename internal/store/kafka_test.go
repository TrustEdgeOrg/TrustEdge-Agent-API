package store

import (
	"path/filepath"
	"testing"
	"time"

	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/constants"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/models"
)

type mockPublisher struct {
	events []models.Event
}

func (m *mockPublisher) PublishEvent(ev models.Event) {
	m.events = append(m.events, ev)
}

func (m *mockPublisher) Close() error { return nil }

func TestAddEventPublishesToKafka(t *testing.T) {
	pub := &mockPublisher{}
	dir := t.TempDir()
	st, err := NewWithOptions(Options{
		DataDir:   filepath.Join(dir, "data"),
		MaxEvents: 10,
		Publisher: pub,
	})
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()

	reg, err := st.Register(models.RegisterRequest{Hostname: "test-host"})
	if err != nil {
		t.Fatal(err)
	}

	now := time.Date(2026, 7, 11, 12, 0, 0, 0, time.UTC)
	ev := models.Event{
		EventID:  "evt_kafka",
		DeviceID: reg.DeviceID,
		Type:     constants.TypeClientDetails,
		TS:       now,
		Payload:  map[string]any{"hostname": "test-host"},
	}
	if err := st.AddEvent(ev); err != nil {
		t.Fatal(err)
	}
	if len(pub.events) != 1 {
		t.Fatalf("published=%d", len(pub.events))
	}
	if pub.events[0].EventID != ev.EventID {
		t.Fatalf("event=%+v", pub.events[0])
	}
}
