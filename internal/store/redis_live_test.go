package store

import (
	"context"
	"encoding/json"
	"path/filepath"
	"testing"
	"time"

	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/constants"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/models"
	"github.com/alicebob/miniredis/v2"
)

func TestRedisLiveMirrorsRegisterAndEvents(t *testing.T) {
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatal(err)
	}
	defer mr.Close()

	dir := t.TempDir()
	st, err := NewWithOptions(Options{
		DataDir:   filepath.Join(dir, "data"),
		MaxEvents: 10,
		RedisURL:  "redis://" + mr.Addr(),
	})
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()

	reg, err := st.Register(models.RegisterRequest{
		Hostname: "elad-mbp",
		OS:       "darwin",
	})
	if err != nil {
		t.Fatal(err)
	}
	ok, err := mr.SIsMember(constants.RedisDevicesKey, reg.DeviceID)
	if err != nil || !ok {
		t.Fatalf("device %s not in twin:devices (ok=%v err=%v)", reg.DeviceID, ok, err)
	}

	now := time.Date(2026, 7, 4, 0, 0, 0, 0, time.UTC)
	ev := models.Event{
		EventID:  "evt_1",
		DeviceID: reg.DeviceID,
		Type:     constants.TypeActionSummary,
		TS:       now,
		Payload: map[string]any{
			"presence": constants.PresenceActive,
			"focus": []any{
				map[string]any{"app_name": "Code", "bundle_id": "com.microsoft.VSCode", "duration_sec": 60.0},
			},
		},
	}
	if err := st.AddEvent(ev); err != nil {
		t.Fatal(err)
	}

	raw, err := mr.Get(latestKey(reg.DeviceID))
	if err != nil {
		t.Fatal(err)
	}
	var doc DeviceLatest
	if err := json.Unmarshal([]byte(raw), &doc); err != nil {
		t.Fatal(err)
	}
	if doc.ClientDetails["hostname"] != "elad-mbp" {
		t.Fatalf("client_details=%v", doc.ClientDetails)
	}
	if doc.ActionSummary["presence"] != constants.PresenceActive {
		t.Fatalf("action_summary=%v", doc.ActionSummary)
	}

	ctx := context.Background()
	n, err := st.live.client.ZCard(ctx, eventsKey(reg.DeviceID)).Result()
	if err != nil {
		t.Fatal(err)
	}
	if n != 1 {
		t.Fatalf("events zcard=%d", n)
	}
}
