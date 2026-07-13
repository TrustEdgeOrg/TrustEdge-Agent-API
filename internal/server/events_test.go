package server

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/codec"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/constants"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/models"
)

func TestDecodeEventsSingle(t *testing.T) {
	body := []byte(`{"type":"client_details","payload":{"hostname":"x"}}`)
	events, err := decodeEvents(body)
	if err != nil || len(events) != 1 || events[0].Type != constants.TypeClientDetails {
		t.Fatalf("events=%+v err=%v", events, err)
	}
}

func TestDecodeEventsBatch(t *testing.T) {
	body := []byte(`{"events":[{"type":"process_start","payload":{"pid":1}},{"type":"process_exit","payload":{"pid":1}}]}`)
	events, err := decodeEvents(body)
	if err != nil || len(events) != 2 {
		t.Fatalf("events=%+v err=%v", events, err)
	}
}

func TestDecodeEventsBatchModel(t *testing.T) {
	raw, _ := json.Marshal(models.EventBatch{
		Events: []models.Event{{Type: constants.TypeProcessStart}},
	})
	events, err := decodeEvents(raw)
	if err != nil || len(events) != 1 {
		t.Fatalf("events=%+v err=%v", events, err)
	}
}

func TestReadRequestBodyZstd(t *testing.T) {
	plain, _ := json.Marshal(models.EventBatch{
		Events: []models.Event{{Type: constants.TypeProcessStart, Payload: map[string]any{"pid": 1}}},
	})
	compressed, err := codec.Compress(plain)
	if err != nil {
		t.Fatal(err)
	}
	req := httptest.NewRequest(http.MethodPost, "/v1/events", bytes.NewReader(compressed))
	req.Header.Set("Content-Encoding", codec.ContentEncoding)
	body, err := readRequestBody(req)
	if err != nil {
		t.Fatal(err)
	}
	events, err := decodeEvents(body)
	if err != nil || len(events) != 1 {
		t.Fatalf("events=%+v err=%v", events, err)
	}
}
