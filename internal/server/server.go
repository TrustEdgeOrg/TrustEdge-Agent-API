package server

import (
	"encoding/json"
	"io"
	"log"
	"net/http"
	"strings"

	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/clock"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/codec"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/config"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/constants"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/models"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/store"
)

type Server struct {
	cfg   config.APIConfig
	clock clock.Clock
	store store.EventStore
	log   *log.Logger
}

func New(cfg config.APIConfig, st store.EventStore, clk clock.Clock, logger *log.Logger) *Server {
	if clk == nil {
		clk = clock.Real{}
	}
	if logger == nil {
		logger = log.Default()
	}
	return &Server{cfg: cfg, clock: clk, store: st, log: logger}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.handleHealth)
	mux.HandleFunc("POST /v1/register", s.handleRegister)
	mux.HandleFunc("POST /v1/events", s.handleEvents)
	mux.HandleFunc("GET /v1/clients/{id}", s.handleGetClient)
	return mux
}

func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": constants.StatusOK})
}

func (s *Server) handleRegister(w http.ResponseWriter, r *http.Request) {
	if s.cfg.EnrollToken != "" && bearer(r) != s.cfg.EnrollToken {
		http.Error(w, constants.ErrUnauthorized, http.StatusUnauthorized)
		return
	}
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		http.Error(w, constants.ErrBadRequest, http.StatusBadRequest)
		return
	}
	var req models.RegisterRequest
	if len(body) > 0 {
		if err := json.Unmarshal(body, &req); err != nil {
			http.Error(w, constants.ErrInvalidJSON, http.StatusBadRequest)
			return
		}
	}
	resp, err := s.store.Register(req)
	if err != nil {
		s.log.Printf("register: %v", err)
		http.Error(w, constants.ErrInternal, http.StatusInternalServerError)
		return
	}
	s.log.Printf("registered device %s", resp.DeviceID)
	writeJSON(w, http.StatusOK, resp)
}

func (s *Server) handleEvents(w http.ResponseWriter, r *http.Request) {
	token := bearer(r)
	if token == "" {
		http.Error(w, constants.ErrUnauthorized, http.StatusUnauthorized)
		return
	}
	deviceID, ok := s.store.DeviceIDForToken(token)
	if !ok {
		http.Error(w, constants.ErrUnauthorized, http.StatusUnauthorized)
		return
	}
	body, err := readRequestBody(r)
	if err != nil {
		http.Error(w, constants.ErrBadRequest, http.StatusBadRequest)
		return
	}
	events, err := decodeEvents(body)
	if err != nil {
		http.Error(w, constants.ErrInvalidJSON, http.StatusBadRequest)
		return
	}
	if len(events) == 0 {
		http.Error(w, constants.ErrBadRequest, http.StatusBadRequest)
		return
	}
	if len(events) > constants.MaxEventsPerBatch {
		http.Error(w, constants.ErrBatchTooLarge, http.StatusBadRequest)
		return
	}

	accepted := 0
	for i := range events {
		ev := events[i]
		if ev.DeviceID == "" {
			ev.DeviceID = deviceID
		}
		if ev.DeviceID != deviceID {
			http.Error(w, constants.ErrDeviceIDMismatch, http.StatusForbidden)
			return
		}
		switch ev.Type {
		case constants.TypeClientDetails, constants.TypeNetworkSummary, constants.TypeActionSummary,
			constants.TypeProcessStart, constants.TypeProcessExit:
		default:
			http.Error(w, constants.ErrUnknownEventType, http.StatusBadRequest)
			return
		}
		if ev.TS.IsZero() {
			ev.TS = s.clock.Now()
		}
		if ev.EventID == "" {
			ev.EventID = s.clock.NewEventID(ev.TS)
		}
		if err := s.store.AddEvent(ev); err != nil {
			s.log.Printf("event: %v", err)
			http.Error(w, constants.ErrInternal, http.StatusInternalServerError)
			return
		}
		accepted++
		s.log.Printf("event %s type=%s device=%s", ev.EventID, ev.Type, ev.DeviceID)
	}
	writeJSON(w, http.StatusAccepted, map[string]any{
		"status":   constants.StatusAccepted,
		"accepted": accepted,
	})
}

func decodeEvents(body []byte) ([]models.Event, error) {
	var batch models.EventBatch
	if err := json.Unmarshal(body, &batch); err == nil && len(batch.Events) > 0 {
		return batch.Events, nil
	}
	var single models.Event
	if err := json.Unmarshal(body, &single); err != nil {
		return nil, err
	}
	if single.Type == "" {
		return nil, json.Unmarshal(body, &batch) // surface batch error if any
	}
	return []models.Event{single}, nil
}

func readRequestBody(r *http.Request) ([]byte, error) {
	raw, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		return nil, err
	}
	if !codec.IsZstd(r.Header.Get("Content-Encoding")) {
		return raw, nil
	}
	return codec.Decompress(raw)
}

func (s *Server) handleGetClient(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	view, ok := s.store.GetClient(id, 50)
	if !ok {
		http.Error(w, constants.ErrNotFound, http.StatusNotFound)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func bearer(r *http.Request) string {
	h := r.Header.Get("Authorization")
	if h == "" {
		return ""
	}
	const prefix = "Bearer "
	if !strings.HasPrefix(h, prefix) {
		return ""
	}
	return strings.TrimSpace(strings.TrimPrefix(h, prefix))
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
