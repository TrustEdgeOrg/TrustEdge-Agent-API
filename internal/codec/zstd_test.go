package codec

import (
	"bytes"
	"testing"
)

func TestMaybeCompressRoundTrip(t *testing.T) {
	src := bytes.Repeat([]byte(`{"type":"process_start","payload":{"pid":123}}`), 50)
	body, compressed, err := MaybeCompress(src)
	if err != nil {
		t.Fatal(err)
	}
	if !compressed {
		t.Fatal("expected compression for repetitive JSON")
	}
	if len(body) >= len(src) {
		t.Fatalf("compressed=%d src=%d", len(body), len(src))
	}
	out, err := Decompress(body)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(out, src) {
		t.Fatal("decompress mismatch")
	}
}

func TestMaybeCompressSkipsSmallPayload(t *testing.T) {
	src := []byte(`{"type":"x"}`)
	body, compressed, err := MaybeCompress(src)
	if err != nil {
		t.Fatal(err)
	}
	if compressed {
		t.Fatal("small payload should stay uncompressed")
	}
	if !bytes.Equal(body, src) {
		t.Fatal("body changed")
	}
}

func TestIsZstd(t *testing.T) {
	if !IsZstd("zstd") || !IsZstd("ZSTD") || !IsZstd("gzip, zstd") {
		t.Fatal("expected zstd match")
	}
	if IsZstd("gzip") {
		t.Fatal("unexpected match")
	}
}
