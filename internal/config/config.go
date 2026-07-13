package config

import (
	"errors"
	"os"
	"strings"
)

type APIConfig struct {
	Listen      string
	EnrollToken string
	DataDir     string
	MaxEvents   int
	Production  bool
	// Mirrors device state to TrustEdge when TRUSTEDGE_AGENT_REDIS_URL or REDIS_URL is set.
	RedisURL string
	// Optional Kafka publish after ingest (KAFKA_BROKERS unset = disabled).
	KafkaBrokers string
	KafkaTopic   string
}

func (c APIConfig) Validate() error {
	if !c.Production {
		return nil
	}
	if strings.TrimSpace(c.EnrollToken) == "" {
		return errors.New("production requires TRUSTEDGE_AGENT_ENROLL_TOKEN on the API")
	}
	if strings.TrimSpace(c.RedisURL) == "" {
		return errors.New("production requires REDIS_URL or TRUSTEDGE_AGENT_REDIS_URL (disk persistence is disabled)")
	}
	return nil
}

func (c APIConfig) PersistFiles() bool {
	if raw, ok := lookupEnv("TRUSTEDGE_AGENT_PERSIST_FILES", "TRUSTTWIN_PERSIST_FILES"); ok {
		v := strings.TrimSpace(strings.ToLower(raw))
		switch v {
		case "1", "true", "yes", "on":
			return true
		case "0", "false", "no", "off":
			return false
		}
	}
	return !c.Production
}

func env(primary, legacy, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(primary)); v != "" {
		return v
	}
	if legacy != "" {
		if v := strings.TrimSpace(os.Getenv(legacy)); v != "" {
			return v
		}
	}
	return fallback
}

func lookupEnv(primary, legacy string) (string, bool) {
	if v, ok := os.LookupEnv(primary); ok {
		return v, true
	}
	if legacy != "" {
		if v, ok := os.LookupEnv(legacy); ok {
			return v, true
		}
	}
	return "", false
}

func envBool(primary, legacy string) bool {
	v := strings.TrimSpace(strings.ToLower(env(primary, legacy, "")))
	switch v {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func Load() APIConfig {
	redisURL := env("TRUSTEDGE_AGENT_REDIS_URL", "TRUSTTWIN_REDIS_URL", "")
	if redisURL == "" {
		redisURL = env("REDIS_URL", "", "")
	}
	kafkaTopic := env("KAFKA_TOPIC", "", "trustedge.agent.events")
	return APIConfig{
		Listen:       env("TRUSTEDGE_AGENT_LISTEN", "TRUSTTWIN_LISTEN", ":8080"),
		EnrollToken:  env("TRUSTEDGE_AGENT_ENROLL_TOKEN", "TRUSTTWIN_ENROLL_TOKEN", ""),
		DataDir:      env("TRUSTEDGE_AGENT_DATA_DIR", "TRUSTTWIN_DATA_DIR", "data"),
		MaxEvents:    500,
		Production:   envBool("TRUSTEDGE_AGENT_PRODUCTION", "TRUSTTWIN_PRODUCTION"),
		RedisURL:     redisURL,
		KafkaBrokers: env("KAFKA_BROKERS", "", ""),
		KafkaTopic:   kafkaTopic,
	}
}
