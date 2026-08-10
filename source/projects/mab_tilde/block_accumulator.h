#pragma once
// Pure block-stream accumulation helpers for the mab~ audio thread.
//
// Max calls perform64 with a small vector size (e.g. 512) while the shared
// memory block spans `block_size` samples (e.g. 2048). These helpers fill and
// drain a [channels][block_size] float buffer across multiple DSP ticks.
//
// No Max SDK dependency: mab_tilde.cpp uses them on the real audio thread and
// unit tests exercise them standalone.

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
        for (long i = 0; i < w; i++) {
            dst[i] = in ? (float)in[i] : 0.0f;
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
        for (long i = 0; i < r; i++) {
            out[i] = (double)src[i];
        }
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
