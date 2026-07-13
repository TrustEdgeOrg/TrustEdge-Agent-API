package kafka

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/models"
	kafkago "github.com/segmentio/kafka-go"
)

const defaultTopic = "trustedge.agent.events"

// Producer publishes TrustTwin events to Kafka. Nil-safe when brokers are unset.
type Producer struct {
	writer *kafkago.Writer
	topic  string
	log    *log.Logger
}

func NewProducer(brokers, topic string, logger *log.Logger) (*Producer, error) {
	brokers = strings.TrimSpace(brokers)
	if brokers == "" {
		return nil, nil
	}
	if topic == "" {
		topic = defaultTopic
	}
	if logger == nil {
		logger = log.Default()
	}
	addrs := splitBrokers(brokers)
	w := &kafkago.Writer{
		Addr:     kafkago.TCP(addrs...),
		Topic:    topic,
		Balancer: &kafkago.Hash{},
	}
	return &Producer{writer: w, topic: topic, log: logger}, nil
}

func splitBrokers(raw string) []string {
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func (p *Producer) Enabled() bool {
	return p != nil && p.writer != nil
}

func (p *Producer) Topic() string {
	if p == nil {
		return ""
	}
	return p.topic
}

func (p *Producer) PublishEvent(ev models.Event) {
	if !p.Enabled() {
		return
	}
	data, err := json.Marshal(ev)
	if err != nil {
		p.log.Printf("kafka marshal %s: %v", ev.DeviceID, err)
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	err = p.writer.WriteMessages(ctx, kafkago.Message{
		Key:   []byte(ev.DeviceID),
		Value: data,
	})
	if err != nil {
		p.log.Printf("kafka publish %s %s: %v", ev.DeviceID, ev.Type, err)
	}
}

func (p *Producer) Close() error {
	if !p.Enabled() {
		return nil
	}
	if err := p.writer.Close(); err != nil {
		return fmt.Errorf("kafka writer close: %w", err)
	}
	return nil
}
