package main

import (
	"log"
	"net/http"
	"os"

	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/clock"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/config"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/server"
	"github.com/TrustEdgeOrg/TrustEdge-Agent-API/internal/store"
)

func main() {
	clk := clock.Real{}
	cfg := config.Load()
	if err := cfg.Validate(); err != nil {
		log.Fatal(err)
	}
	logger := log.New(os.Stdout, "trustedge-agent-api: ", log.LstdFlags|log.Lmsgprefix)

	st, err := store.NewWithOptions(store.Options{
		Clock:                  clk,
		DataDir:                cfg.DataDir,
		MaxEvents:              cfg.MaxEvents,
		DisableDiskPersistence: !cfg.PersistFiles(),
		RedisURL:               cfg.RedisURL,
		KafkaBrokers:           cfg.KafkaBrokers,
		KafkaTopic:             cfg.KafkaTopic,
		Logger:                 logger,
	})
	if err != nil {
		logger.Fatalf("store: %v", err)
	}
	defer st.Close()

	srv := server.New(cfg, st, clk, logger)
	redisNote := "off"
	if st.RedisEnabled() {
		redisNote = "on"
	}
	kafkaNote := "off"
	if st.KafkaEnabled() {
		kafkaNote = "on"
	}
	logger.Printf("listening on %s (disk=%t redis=%s kafka=%s)", cfg.Listen, cfg.PersistFiles(), redisNote, kafkaNote)
	if err := http.ListenAndServe(cfg.Listen, srv.Handler()); err != nil {
		logger.Fatal(err)
	}
}
