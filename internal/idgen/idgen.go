package idgen

import (
	"crypto/rand"
	"encoding/hex"
)

// NewDeviceID returns a new TrustTwin device identifier.
func NewDeviceID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return "dev_" + hex.EncodeToString(b)
}

// NewToken returns a new device auth token.
func NewToken() string {
	b := make([]byte, 24)
	_, _ = rand.Read(b)
	return "tok_" + hex.EncodeToString(b)
}
