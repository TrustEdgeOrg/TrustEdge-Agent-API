package store

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/clock"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/constants"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/models"
	"github.com/redis/go-redis/v9"
)

// DeviceLatest is the live per-device document TrustEdge reads.
type DeviceLatest struct {
	DeviceID       string         `json:"device_id"`
	LastSeenAt     *time.Time     `json:"last_seen_at,omitempty"`
	ClientDetails  map[string]any `json:"client_details,omitempty"`
	NetworkSummary map[string]any `json:"network_summary,omitempty"`
	ActionSummary  map[string]any `json:"action_summary,omitempty"`
}

type redisLive struct {
	client    *redis.Client
	clock     clock.Clock
	maxEvents int
	log       *log.Logger
}

func newRedisLive(redisURL string, maxEvents int, logger *log.Logger, clk clock.Clock) (*redisLive, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("parse redis url: %w", err)
	}
	client := redis.NewClient(opts)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		_ = client.Close()
		return nil, fmt.Errorf("redis ping: %w", err)
	}
	if logger == nil {
		logger = log.Default()
	}
	if clk == nil {
		clk = clock.Real{}
	}
	return &redisLive{client: client, clock: clk, maxEvents: maxEvents, log: logger}, nil
}

func (r *redisLive) Close() error {
	if r == nil || r.client == nil {
		return nil
	}
	return r.client.Close()
}

func latestKey(deviceID string) string { return fmt.Sprintf(constants.RedisLatestKeyFmt, deviceID) }
func eventsKey(deviceID string) string { return fmt.Sprintf(constants.RedisEventsKeyFmt, deviceID) }
func deviceAuthKey(deviceID string) string {
	return fmt.Sprintf("twin:device:%s:auth", deviceID)
}

func (r *redisLive) SaveDeviceAuth(rec *deviceRecord) error {
	if r == nil || rec == nil || rec.DeviceID == "" {
		return nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	data, err := json.Marshal(rec)
	if err != nil {
		return err
	}
	pipe := r.client.Pipeline()
	pipe.Set(ctx, deviceAuthKey(rec.DeviceID), data, 0)
	if rec.DeviceToken != "" {
		pipe.HSet(ctx, constants.RedisDeviceTokensKey, rec.DeviceToken, rec.DeviceID)
	}
	_, err = pipe.Exec(ctx)
	return err
}

func (r *redisLive) LoadDeviceAuth() ([]*deviceRecord, error) {
	if r == nil {
		return nil, nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	tokenMap, err := r.client.HGetAll(ctx, constants.RedisDeviceTokensKey).Result()
	if err != nil {
		return nil, err
	}
	seen := map[string]struct{}{}
	var records []*deviceRecord
	for _, deviceID := range tokenMap {
		if deviceID == "" {
			continue
		}
		if _, ok := seen[deviceID]; ok {
			continue
		}
		seen[deviceID] = struct{}{}
		raw, err := r.client.Get(ctx, deviceAuthKey(deviceID)).Bytes()
		if err != nil || len(raw) == 0 {
			continue
		}
		var rec deviceRecord
		if err := json.Unmarshal(raw, &rec); err != nil {
			continue
		}
		records = append(records, &rec)
	}
	return records, nil
}

func (r *redisLive) loadLatest(ctx context.Context, deviceID string) DeviceLatest {
	raw, err := r.client.Get(ctx, latestKey(deviceID)).Bytes()
	if err != nil || len(raw) == 0 {
		return DeviceLatest{DeviceID: deviceID}
	}
	var doc DeviceLatest
	if err := json.Unmarshal(raw, &doc); err != nil {
		return DeviceLatest{DeviceID: deviceID}
	}
	doc.DeviceID = deviceID
	return doc
}

func (r *redisLive) saveLatest(ctx context.Context, doc DeviceLatest) error {
	data, err := json.Marshal(doc)
	if err != nil {
		return err
	}
	pipe := r.client.Pipeline()
	pipe.SAdd(ctx, constants.RedisDevicesKey, doc.DeviceID)
	pipe.Set(ctx, latestKey(doc.DeviceID), data, 0)
	_, err = pipe.Exec(ctx)
	return err
}

func (r *redisLive) UpsertRegister(deviceID string, details map[string]any, seenAt time.Time) {
	if r == nil {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	doc := r.loadLatest(ctx, deviceID)
	doc.LastSeenAt = &seenAt
	if doc.ClientDetails == nil {
		doc.ClientDetails = map[string]any{}
	}
	for k, v := range details {
		if v == nil {
			continue
		}
		if s, ok := v.(string); ok && s == "" {
			continue
		}
		doc.ClientDetails[k] = v
	}
	if err := r.saveLatest(ctx, doc); err != nil {
		r.log.Printf("redis register %s: %v", deviceID, err)
	}
}

func (r *redisLive) UpsertEvent(ev models.Event) {
	if r == nil {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	doc := r.loadLatest(ctx, ev.DeviceID)
	ts := ev.TS
	if ts.IsZero() {
		ts = r.clock.Now()
	}
	doc.LastSeenAt = &ts
	switch ev.Type {
	case constants.TypeClientDetails:
		doc.ClientDetails = ev.Payload
	case constants.TypeNetworkSummary:
		doc.NetworkSummary = ev.Payload
	case constants.TypeActionSummary:
		doc.ActionSummary = ev.Payload
	}

	data, err := json.Marshal(doc)
	if err != nil {
		r.log.Printf("redis event marshal %s: %v", ev.DeviceID, err)
		return
	}
	evData, err := json.Marshal(ev)
	if err != nil {
		r.log.Printf("redis event body %s: %v", ev.DeviceID, err)
		return
	}

	score := float64(ts.UnixMilli())
	ekey := eventsKey(ev.DeviceID)
	pipe := r.client.Pipeline()
	pipe.SAdd(ctx, constants.RedisDevicesKey, ev.DeviceID)
	pipe.Set(ctx, latestKey(ev.DeviceID), data, 0)
	pipe.ZAdd(ctx, ekey, redis.Z{Score: score, Member: string(evData)})
	if r.maxEvents > 0 {
		pipe.ZRemRangeByRank(ctx, ekey, 0, int64(-r.maxEvents-1))
	}
	if _, err := pipe.Exec(ctx); err != nil {
		r.log.Printf("redis event %s: %v", ev.DeviceID, err)
	}
}
