package clock

import "time"

// Clock supplies time for telemetry timestamps and event IDs.
type Clock interface {
	Now() time.Time
	NewEventID(t time.Time) string
}

// Real uses the system clock in UTC.
type Real struct{}

func (Real) Now() time.Time {
	return time.Now().UTC()
}

func (Real) NewEventID(t time.Time) string {
	return "evt_" + t.UTC().Format("20060102T150405.000000000")
}
