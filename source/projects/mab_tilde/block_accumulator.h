#pragma once
// Pure block-stream accumulation helpers for the mab~ audio thread.
//
// Max calls perform64 with a small vector size (e.g. 512) while the shared
// memory block spans `block_size` samples (e.g. 2048). These helpers fill and
// drain a [channels][block_size] float buffer across multiple DSP ticks.
//
// No Max SDK dependency: mab_tilde.cpp uses them on the real audio thread and
// unit tests exercise them standalone.

#include <emmintrin.h>
#include <cstring>

// A6: SIMD vectorised float <-> double conversion. SSE2 is guaranteed on x64.
// These helpers use unaligned loads/stores so no padding/alignment is required.
static inline void convert_d2f(const double* __restrict src,
                               float* __restrict dst, size_t n) {
    size_t i = 0;
    // Process two doubles -> two floats per iteration.
    for (; i + 2 <= n; i += 2) {
        __m128d vd = _mm_loadu_pd(src + i);
        __m128 vf = _mm_cvtpd_ps(vd);
        dst[i] = _mm_cvtss_f32(vf);
        dst[i + 1] = _mm_cvtss_f32(_mm_shuffle_ps(vf, vf, _MM_SHUFFLE(0, 0, 0, 1)));
    }
    for (; i < n; ++i) {
        dst[i] = static_cast<float>(src[i]);
    }
}

static inline void convert_f2d(const float* __restrict src,
                               double* __restrict dst, size_t n) {
    size_t i = 0;
    // Process four floats -> four doubles per iteration.
    for (; i + 4 <= n; i += 4) {
        __m128 vf = _mm_loadu_ps(src + i);
        __m128d vd0 = _mm_cvtps_pd(vf);
        __m128 vf_hi = _mm_movehl_ps(vf, vf);
        __m128d vd1 = _mm_cvtps_pd(vf_hi);
        _mm_storeu_pd(dst + i, vd0);
        _mm_storeu_pd(dst + i + 2, vd1);
    }
    for (; i < n; ++i) {
        dst[i] = static_cast<double>(src[i]);
    }
}

// Append `n` samples per channel to a [channels][block_size] float buffer.
// Never writes past the current block boundary, so a pending (not yet
// consumed by Python) block is never overwritten. A tick that exceeds the
// remaining space is truncated (the leftover samples are dropped - this only
// happens when the vector size does not divide the block size, which is
// unusual since both are powers of two).
// `pos` (in/out) is the current fill position within [0, block_size).
// Returns true when the block completed (pos wrapped to 0).
inline bool block_accumulate_write(float* buffer, long channels, long block_size,
                                   long n, const double* const* ins, long numins,
                                   long& pos) {
    if (pos >= block_size) pos = 0;
    long rem = block_size - pos;
    long w = (n < rem) ? n : rem;
    for (long ch = 0; ch < channels; ch++) {
        const double* in = (ch < numins && ins[ch]) ? ins[ch] : nullptr;
        float* dst = buffer + (long long)ch * block_size + pos;
        if (in) {
            convert_d2f(in, dst, static_cast<size_t>(w));
        } else {
            std::memset(dst, 0, static_cast<size_t>(w) * sizeof(float));
        }
    }
    pos += w;
    if (pos >= block_size) {
        pos = 0;
        return true;
    }
    return false;
}

// Drain `n` samples per channel from a [channels][block_size] float buffer.
// Stops at the block boundary; samples of this tick that extend beyond the
// drained block would be stale next-block data and are silenced.
// `pos` (in/out) is the current drain position within [0, block_size).
// Returns true when the block completed (pos wrapped to 0).
inline bool block_accumulate_read(float* buffer, long channels, long block_size,
                                  long n, double** outs, long numouts,
                                  long& pos) {
    if (pos >= block_size) pos = 0;
    long rem = block_size - pos;
    long r = (n < rem) ? n : rem;
    for (long ch = 0; ch < channels; ch++) {
        double* out = (ch < numouts) ? outs[ch] : nullptr;
        if (!out) continue;
        const float* src = buffer + (long long)ch * block_size + pos;
        convert_f2d(src, out, static_cast<size_t>(r));
    }
    pos += r;
    bool completed = (pos >= block_size);
    if (completed) pos = 0;
    // Tail of this tick beyond the drained block: stale data, silence it.
    if (r < n) {
        for (long ch = 0; ch < channels; ch++) {
            double* out = (ch < numouts) ? outs[ch] : nullptr;
            if (!out) continue;
            for (long i = r; i < n; i++) {
                out[i] = 0.0;
            }
        }
    }
    return completed;
}
