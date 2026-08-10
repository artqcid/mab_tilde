// Test for the block-stream accumulation helpers used by perform64.
//
// These helpers fill and drain a [channels][block_size] float buffer across
// multiple DSP ticks (vector size < block size). The tests verify boundary
// handling, multi-channel access, truncation and tail-silencing.

#include <cstdio>
#include <cassert>
#include <cstring>
#include <cstdint>
#include <vector>

#include "../source/projects/mab_tilde/block_accumulator.h"

static const long BLOCK = 2048;
static const long VEC = 512;  // 4 ticks per block

// 4 ticks of 512 samples must complete exactly one 2048 block
static void test_accumulate_across_ticks() {
    printf("test_accumulate_across_ticks...\n");
    std::vector<float> buf(1 * BLOCK, 0.0f);
    long pos = 0;
    bool done = false;
    for (int t = 0; t < 4; t++) {
        std::vector<double> vec(VEC, (double)(t + 1));
        const double* ins[1] = { vec.data() };
        done = block_accumulate_write(buf.data(), 1, BLOCK, VEC, ins, 1, pos);
    }
    assert(done);                       // block completed after 4 ticks
    assert(pos == 0);                   // pos wrapped
    for (int t = 0; t < 4; t++) {
        for (long i = 0; i < VEC; i++) {
            assert(buf[(long)t * VEC + i] == (float)(t + 1));
        }
    }
    printf("  OK\n");
}

// input truncation: a single oversized tick must not write past the block end
static void test_write_truncates_at_boundary() {
    printf("test_write_truncates_at_boundary...\n");
    std::vector<float> buf(1 * BLOCK, 0.0f);
    long pos = BLOCK - 100;  // 100 samples of space left
    std::vector<double> vec(512, 7.0);
    const double* ins[1] = { vec.data() };
    bool done = block_accumulate_write(buf.data(), 1, BLOCK, 512, ins, 1, pos);
    assert(done);
    assert(pos == 0);
    // Only the last 100 slots are filled; the remaining 412 samples of the
    // tick are dropped and nothing may have been written before pos.
    for (long i = 0; i < BLOCK - 100; i++) {
        assert(buf[i] == 0.0f);
    }
    for (long i = BLOCK - 100; i < BLOCK; i++) {
        assert(buf[i] == 7.0f);
    }
    printf("  OK\n");
}

// multi-channel: each channel gets its own contiguous block row
static void test_multichannel_write_read() {
    printf("test_multichannel_write_read...\n");
    const long CH = 4;
    std::vector<float> buf(CH * BLOCK, 0.0f);
    long pos = 0;
    for (int t = 0; t < 4; t++) {
        std::vector<std::vector<double>> vals(CH, std::vector<double>(VEC, 0.0));
        const double* ins[CH];
        for (long c = 0; c < CH; c++) {
            for (long i = 0; i < VEC; i++) vals[c][i] = (double)(c + 1);
            ins[c] = vals[c].data();
        }
        block_accumulate_write(buf.data(), CH, BLOCK, VEC, ins, CH, pos);
    }
    for (long c = 0; c < CH; c++) {
        for (long i = 0; i < BLOCK; i++) {
            assert(buf[(long)c * BLOCK + i] == (float)(c + 1));
        }
    }

    // Drain over 4 ticks
    pos = 0;
    for (int t = 0; t < 4; t++) {
        std::vector<double> outs(CH * VEC, -1.0);
        double* outp[CH];
        for (long c = 0; c < CH; c++) outp[c] = &outs[(long)c * VEC];
        block_accumulate_read(buf.data(), CH, BLOCK, VEC, outp, CH, pos);
        for (long c = 0; c < CH; c++) {
            for (long i = 0; i < VEC; i++) {
                assert(outs[(long)c * VEC + i] == (double)(c + 1));
            }
        }
    }
    assert(pos == 0);
    printf("  OK\n");
}

// read tail-silencing: when a tick crosses the block boundary, the remainder
// must be zero (next block not ready yet)
static void test_read_silences_stale_tail() {
    printf("test_read_silences_stale_tail...\n");
    const long CH = 1;
    std::vector<float> buf(CH * BLOCK, 0.0f);
    for (long i = 0; i < BLOCK; i++) buf[i] = 5.0f;  // one full block of 5.0

    long pos = BLOCK - 128;  // near the end
    std::vector<double> outs(VEC, -1.0);
    double* outp[CH] = { outs.data() };
    bool done = block_accumulate_read(buf.data(), CH, BLOCK, VEC, outp, CH, pos);
    assert(done);
    assert(pos == 0);
    for (long i = 0; i < 128; i++) {
        assert(outs[i] == 5.0);   // drained block data
    }
    for (long i = 128; i < VEC; i++) {
        assert(outs[i] == 0.0);   // stale tail silenced
    }
    printf("  OK\n");
}

// missing outlets must not be written (skip instead of crash)
static void test_missing_outlets_skipped() {
    printf("test_missing_outlets_skipped...\n");
    const long CH = 2;
    std::vector<float> buf(CH * BLOCK, 3.0f);
    long pos = 0;
    std::vector<double> outs(VEC, -1.0);
    double* outp[CH] = { outs.data(), nullptr };  // only outlet 0 connected
    block_accumulate_read(buf.data(), CH, BLOCK, VEC, outp, 1, pos);
    for (long i = 0; i < VEC; i++) {
        assert(outs[i] == 3.0);
    }
    printf("  OK\n");
}

// missing inlets must be zero-filled
static void test_missing_inlets_zero_filled() {
    printf("test_missing_inlets_zero_filled...\n");
    const long CH = 2;
    std::vector<float> buf(CH * BLOCK, -1.0f);
    long pos = 0;
    const double* ins[CH] = { nullptr, nullptr };  // no inlets connected
    block_accumulate_write(buf.data(), CH, BLOCK, VEC, ins, 0, pos);
    for (long c = 0; c < CH; c++) {
        for (long i = 0; i < VEC; i++) {
            assert(buf[(long)c * BLOCK + i] == 0.0f);
        }
    }
    printf("  OK\n");
}

int main() {
    setvbuf(stdout, NULL, _IONBF, 0);  // keep output even on assert-crash
    printf("=== Block Accumulator Tests ===\n\n");
    test_accumulate_across_ticks();
    test_write_truncates_at_boundary();
    test_multichannel_write_read();
    test_read_silences_stale_tail();
    test_missing_outlets_skipped();
    test_missing_inlets_zero_filled();
    printf("\n=== All tests passed! ===\n");
    return 0;
}
