package constants

// Redis keys shared with TrustEdge (see trustedge-agent_store.py).
const (
	RedisDevicesKey       = "twin:devices"
	RedisDeviceTokensKey  = "twin:device_tokens"
	RedisLatestKeyFmt     = "twin:device:%s:latest"
	RedisEventsKeyFmt     = "twin:device:%s:events"
)
