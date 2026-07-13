package config

import "testing"

func TestAPIConfigValidateProduction(t *testing.T) {
	if err := (APIConfig{Production: true}).Validate(); err == nil {
		t.Fatal("expected error without enroll token")
	}
	if err := (APIConfig{Production: true, EnrollToken: "secret"}).Validate(); err == nil {
		t.Fatal("expected error without redis")
	}
	if err := (APIConfig{
		Production:  true,
		EnrollToken: "secret",
		RedisURL:    "redis://127.0.0.1:6379/0",
	}).Validate(); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestAPIConfigPersistFiles(t *testing.T) {
	dev := APIConfig{Production: false}
	if !dev.PersistFiles() {
		t.Fatal("dev should persist files by default")
	}
	prod := APIConfig{Production: true}
	if prod.PersistFiles() {
		t.Fatal("production should not persist files by default")
	}
}
