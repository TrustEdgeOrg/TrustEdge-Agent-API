package store

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/models"
	"github.com/alicebob/miniredis/v2"
)

func TestDisableDiskPersistenceSkipsJSONFiles(t *testing.T) {
	dir := t.TempDir()
	dataDir := filepath.Join(dir, "data")

	mr, err := miniredis.Run()
	if err != nil {
		t.Fatal(err)
	}
	defer mr.Close()

	st, err := NewWithOptions(Options{
		DataDir:                dataDir,
		MaxEvents:              10,
		DisableDiskPersistence: true,
		RedisURL:               "redis://" + mr.Addr(),
	})
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()

	if _, err := st.Register(models.RegisterRequest{Hostname: "test-host"}); err != nil {
		t.Fatal(err)
	}
	if err := st.AddEvent(models.Event{
		EventID:  "evt_1",
		DeviceID: "dev_test",
		Type:     "client_details",
		Payload:  map[string]any{"hostname": "test-host"},
	}); err != nil {
		t.Fatal(err)
	}

	if _, err := os.Stat(filepath.Join(dataDir, "devices.json")); !os.IsNotExist(err) {
		t.Fatalf("devices.json should not exist, err=%v", err)
	}
	if _, err := os.Stat(filepath.Join(dataDir, "events.jsonl")); !os.IsNotExist(err) {
		t.Fatalf("events.jsonl should not exist, err=%v", err)
	}
}

func TestDisableDiskPersistenceRestoresAuthFromRedis(t *testing.T) {
	dir := t.TempDir()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatal(err)
	}
	defer mr.Close()

	redisURL := "redis://" + mr.Addr()
	st1, err := NewWithOptions(Options{
		DataDir:                filepath.Join(dir, "data"),
		DisableDiskPersistence: true,
		RedisURL:               redisURL,
	})
	if err != nil {
		t.Fatal(err)
	}
	reg, err := st1.Register(models.RegisterRequest{Hostname: "persist-me"})
	if err != nil {
		t.Fatal(err)
	}
	if err := st1.Close(); err != nil {
		t.Fatal(err)
	}

	st2, err := NewWithOptions(Options{
		DataDir:                filepath.Join(dir, "data2"),
		DisableDiskPersistence: true,
		RedisURL:               redisURL,
	})
	if err != nil {
		t.Fatal(err)
	}
	defer st2.Close()

	id, ok := st2.DeviceIDForToken(reg.DeviceToken)
	if !ok || id != reg.DeviceID {
		t.Fatalf("token not restored from redis: id=%q ok=%v", id, ok)
	}
}
