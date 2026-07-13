package codec

import (
	"strings"
	"sync"

	"github.com/klauspost/compress/zstd"
)

const ContentEncoding = "zstd"

var (
	encOnce sync.Once
	decOnce sync.Once
	enc     *zstd.Encoder
	dec     *zstd.Decoder
	encErr  error
	decErr  error
)

func encoder() (*zstd.Encoder, error) {
	encOnce.Do(func() {
		enc, encErr = zstd.NewWriter(nil, zstd.WithEncoderLevel(zstd.SpeedDefault))
	})
	return enc, encErr
}

func decoder() (*zstd.Decoder, error) {
	decOnce.Do(func() {
		dec, decErr = zstd.NewReader(nil)
	})
	return dec, decErr
}

// Compress returns zstd-compressed data. The result may be larger than src for
// very small inputs; callers can compare lengths before sending.
func Compress(src []byte) ([]byte, error) {
	e, err := encoder()
	if err != nil {
		return nil, err
	}
	return e.EncodeAll(src, make([]byte, 0, len(src))), nil
}

func Decompress(src []byte) ([]byte, error) {
	d, err := decoder()
	if err != nil {
		return nil, err
	}
	return d.DecodeAll(src, nil)
}

func IsZstd(contentEncoding string) bool {
	for _, part := range strings.Split(contentEncoding, ",") {
		if strings.EqualFold(strings.TrimSpace(part), ContentEncoding) {
			return true
		}
	}
	return false
}

// MaybeCompress compresses when it reduces payload size.
func MaybeCompress(src []byte) (body []byte, compressed bool, err error) {
	if len(src) == 0 {
		return src, false, nil
	}
	out, err := Compress(src)
	if err != nil {
		return nil, false, err
	}
	if len(out) >= len(src) {
		return src, false, nil
	}
	return out, true, nil
}
