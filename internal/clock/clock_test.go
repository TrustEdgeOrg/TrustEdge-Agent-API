package clock

import (
	"testing"
	"time"
)

func TestNewEventIDUsesUTC(t *testing.T) {
	clk := Real{}
	ts := time.Date(2026, 7, 10, 14, 30, 0, 0, time.FixedZone("IDT", 3*3600))
	got := clk.NewEventID(ts)
	want := "evt_20260710T113000.000000000"
	if got != want {
		t.Fatalf("NewEventID()=%q want %q", got, want)
	}
}
