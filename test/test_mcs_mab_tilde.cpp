// Tests for the Phase 6 mcs.mab~ (batched multichannel) logic.
//
// These verify the pure C++ decisions that live in mab_tilde.cpp without
// linking against the Max SDK:
//   1. IO layout: mcs.mab~ has exactly `mcs_batches` inlets AND outlets
//      (mab_tilde.cpp mab_tilde_apply_io), with the model's channel counts
//      kept separately (channels_in per batch).
//   2. Batch input wiring: the flat `ins[]` array from Max is mapped into
//      batch-major SHM rows b*ci+c; unconnected channels (channel_map[b] < ci)
//      stay null -> block_accumulate_write zero-pads them.
//   3. Batch output wiring: SHM rows b*co+c are drained into the per-batch
//      multichannel outlets at flat index b*per_outlet+c; extra outlet
//      channels (per_outlet > co, e.g. `chans`) are silenced.
//   4. mcs_multichanneloutputs: `chans` (n_batches) wins, else channels_out.
//   5. mcs_inputchanged: channel_map update + header publish; the model layout
//      (channels_in) is NOT modified.

#include <cstdio>
#include <cassert>
#include <cstring>
#include <cstdint>
#include <vector>

#include "../source/projects/mab_tilde/block_accumulator.h"

static const long MAX_CHANNELS = 16;
static const long BLOCK = 2048;

// ---- SharedMemoryHeader (v3) - must mirror mab_tilde.cpp:38-67 ----
struct SharedMemoryHeader {
    uint32_t magic;
    uint32_t version;
    uint32_t block_size;
    uint32_t num_channels;
    uint32_t channels_in;
    uint32_t channels_out;
    uint32_t latent_size;
    uint32_t input_ratio;
    uint32_t output_ratio;
    char     method[52];
    uint32_t method_id;
    uint32_t input_offset;
    uint32_t output_offset;
    uint32_t control_offset;
    uint32_t input_buffer_index;
    uint32_t output_buffer_index;
    uint32_t channel_map[16];
    long is_input_ready;
    long is_output_ready;
    long is_python_ready;
    long shutdown_flag;
};
static_assert(sizeof(SharedMemoryHeader) == 192,
              "header v3 must be 192 bytes (sync with mab_tilde.cpp)");

// ---- Minimal t_mab_tilde subset used by the mcs helpers ----
struct McsState {
    long is_mc;
    long is_mcs;
    long channels_in;      // model layout (header-driven, per batch)
    long channels_out;     // model layout (header-driven, per batch)
    long mcs_batches;      // number of batch inlets/outlets
    long n_batches;        // `chans` attribute (per-outlet channels, 0 = auto)
    long channel_map[16];
    SharedMemoryHeader* header;
};

// Mirror of mab_tilde.cpp mab_tilde_apply_io decision (line ~725)
static void apply_io_decision(McsState* x, long model_in, long model_out,
                              long* io_in, long* io_out) {
    if (model_in < 1) model_in = 1;
    if (model_out < 1) model_out = 1;
    if (model_in > MAX_CHANNELS) model_in = MAX_CHANNELS;
    if (model_out > MAX_CHANNELS) model_out = MAX_CHANNELS;
    x->channels_in = model_in;
    x->channels_out = model_out;
    *io_in = x->is_mcs ? x->mcs_batches : (x->is_mc ? 1 : model_in);
    *io_out = x->is_mcs ? x->mcs_batches : (x->is_mc ? 1 : model_out);
    if (x->is_mc) {
        for (long i = 0; i < MAX_CHANNELS; i++) {
            x->channel_map[i] = 0;
            if (x->header) x->header->channel_map[i] = 0;
        }
    }
}

// Mirror of mab_tilde.cpp mcs_multichanneloutputs (line ~1730)
static long mcs_multichanneloutputs(McsState* x, long index, long count) {
    (void)index; (void)count;
    if (x->n_batches > 0) {
        return x->n_batches;
    }
    return x->channels_out;
}

// Mirror of mab_tilde.cpp mcs_inputchanged (line ~1740)
static long mcs_inputchanged(McsState* x, long index, long count) {
    if (index < 0 || index >= MAX_CHANNELS) return 0;
    if (count < 1) count = 1;
    if (count > MAX_CHANNELS) count = MAX_CHANNELS;
    if (x->channel_map[index] != count) {
        x->channel_map[index] = count;
        if (x->header) {
            x->header->channel_map[index] = (uint32_t)count;
        }
    }
    return 1;
}

// Mirror of the perform64 input wiring (mab_tilde.cpp mcs_mab_tilde_perform64):
// maps the flat `ins[]` (inlet 0 channels first, then inlet 1, ...) into the
// batch-major SHM rows b*ci+c. Unconnected rows stay nullptr (zero-padded).
static void wire_batch_input(const double* const* ins, long numins,
                             long n_batches, long ci, const long* channel_map,
                             const double* wired[MAX_CHANNELS * MAX_CHANNELS]) {
    for (long r = 0; r < n_batches * ci; r++) wired[r] = nullptr;
    long flat = 0;
    for (long b = 0; b < n_batches; b++) {
        long ch_conn = channel_map[b];
        if (ch_conn < 0) ch_conn = 0;
        if (ch_conn > ci) ch_conn = ci;
        for (long c = 0; c < ch_conn && flat < numins; c++, flat++) {
            if (ins[flat]) wired[b * ci + c] = ins[flat];
        }
    }
}

// Mirror of the perform64 output wiring: SHM rows b*co+c -> flat outlets
// b*per_outlet+c. Rows without a real outlet stay nullptr (skipped).
static void wire_batch_output(double** outs, long numouts, long n_batches,
                              long co, long per_outlet,
                              double* wired[MAX_CHANNELS * MAX_CHANNELS]) {
    for (long r = 0; r < n_batches * co; r++) wired[r] = nullptr;
    for (long b = 0; b < n_batches; b++) {
        for (long c = 0; c < co; c++) {
            long flat_idx = b * per_outlet + c;
            if (flat_idx < numouts && outs[flat_idx]) {
                wired[b * co + c] = outs[flat_idx];
            }
        }
    }
}

// ---------------------------------------------------------------------------

static void test_mcs_io_is_n_batches_in_n_batches_out() {
    printf("test_mcs_io_is_n_batches_in_n_batches_out...\n");
    McsState x = {};
    x.is_mcs = 1;
    x.is_mc = 1;
    x.mcs_batches = 4;

    // encode: model 1 in / 16 out -> mcs box has 4 inlets / 4 outlets
    long io_in, io_out;
    apply_io_decision(&x, 1, 16, &io_in, &io_out);
    assert(io_in == 4);
    assert(io_out == 4);
    // the model layout must be preserved for perform64 / detection
    assert(x.channels_in == 1);
    assert(x.channels_out == 16);
    // stale channel_map from a previous method must be cleared
    for (long i = 0; i < MAX_CHANNELS; i++) assert(x.channel_map[i] == 0);

    // decode: model 16 in / 1 out -> still 4 inlets / 4 outlets
    apply_io_decision(&x, 16, 1, &io_in, &io_out);
    assert(io_in == 4);
    assert(io_out == 4);
    assert(x.channels_in == 16);
    assert(x.channels_out == 1);
    printf("  OK\n");
}

static void test_single_batch_falls_back_to_model_counts() {
    printf("test_single_batch_falls_back_to_model_counts...\n");
    // mcs_batches == 1 behaves like mc.mab~ (1-in-1-out MC)
    McsState x = {};
    x.is_mcs = 1;
    x.is_mc = 1;
    x.mcs_batches = 1;
    long io_in, io_out;
    apply_io_decision(&x, 16, 1, &io_in, &io_out);
    assert(io_in == 1);
    assert(io_out == 1);
    assert(x.channels_in == 16);
    printf("  OK\n");
}

static void test_batch_input_wiring_batch_major() {
    printf("test_batch_input_wiring_batch_major...\n");
    // encode: ci=1, 4 batches, each batch inlet 1 channel (channel_map all 1).
    // The flat ins[] -> SHM rows b*1+0 = [0,1,2,3].
    {
        const long CI = 1, NB = 4, VEC = 512;
        std::vector<std::vector<double>> vals(NB, std::vector<double>(VEC, 0.0));
        const double* ins[NB];
        for (long b = 0; b < NB; b++) {
            for (long i = 0; i < VEC; i++) vals[b][i] = (double)(b + 1);
            ins[b] = vals[b].data();
        }
        long map[16] = { 1, 1, 1, 1 };
        const double* wired[MAX_CHANNELS * MAX_CHANNELS] = { nullptr };
        wire_batch_input(ins, NB, NB, CI, map, wired);
        for (long b = 0; b < NB; b++) assert(wired[b * CI + 0] == ins[b]);

        // full block write: rows b*ci+c hold exactly batch b's channel
        std::vector<float> shm_buf(NB * CI * BLOCK, -1.0f);
        long pos = 0;
        for (int t = 0; t < 4; t++) {
            block_accumulate_write(shm_buf.data(), NB * CI, BLOCK, VEC,
                                   wired, NB * CI, pos);
        }
        assert(pos == 0);
        for (long b = 0; b < NB; b++) {
            for (long i = 0; i < BLOCK; i++) {
                assert(shm_buf[(long)(b * CI + 0) * BLOCK + i] == (float)(b + 1));
            }
        }
    }
    printf("  OK\n");
}

static void test_partial_batch_zero_padded() {
    printf("test_partial_batch_zero_padded...\n");
    // decode: ci=16, 4 batches. Only batches 0 and 1 are connected with 16
    // channels; batches 2-3 have channel_map 0 -> fully zero-padded rows.
    const long CI = 16, NB = 4, VEC = 512;
    long map[16] = { 16, 16, 0, 0 };
    // flat: 32 connected channels (16 per connected batch inlet)
    std::vector<std::vector<double>> vals(32, std::vector<double>(VEC, 3.0));
    const double* ins[32];
    for (long c = 0; c < 32; c++) ins[c] = vals[c].data();

    const double* wired[MAX_CHANNELS * MAX_CHANNELS] = { nullptr };
    wire_batch_input(ins, 32, NB, CI, map, wired);
    // batch 0 rows 0..15 and batch 1 rows 16..31 are wired
    for (long r = 0; r < 32; r++) assert(wired[r] == ins[r]);
    // batches 2-3 (rows 32..63) are null -> zero-padded by the accumulator
    for (long r = 32; r < NB * CI; r++) assert(wired[r] == nullptr);

    std::vector<float> shm_buf(NB * CI * BLOCK, -1.0f);
    long pos = 0;
    for (int t = 0; t < 4; t++) {
        block_accumulate_write(shm_buf.data(), NB * CI, BLOCK, VEC,
                               wired, NB * CI, pos);
    }
    assert(pos == 0);
    for (long r = 0; r < 32; r++) {
        for (long i = 0; i < BLOCK; i++) assert(shm_buf[r * BLOCK + i] == 3.0f);
    }
    for (long r = 32; r < NB * CI; r++) {
        for (long i = 0; i < BLOCK; i++) assert(shm_buf[r * BLOCK + i] == 0.0f);
    }
    printf("  OK\n");
}

static void test_output_wiring_and_extra_outlet_silenced() {
    printf("test_output_wiring_and_extra_outlet_silenced...\n");
    // encode: co=16 latent channels per batch, 4 batch outlets, no `chans`
    // override -> per_outlet = co = 16. numouts = 4*16 = 64.
    const long CO = 16, NB = 4;
    const long PER_OUTLET = 16;   // = channels_out (auto)
    const long NUMOUTS = NB * PER_OUTLET;

    std::vector<double> outlets[NUMOUTS];
    for (long o = 0; o < NUMOUTS; o++) outlets[o].assign(BLOCK, -1.0);
    double* outs[NUMOUTS];
    for (long o = 0; o < NUMOUTS; o++) outs[o] = outlets[o].data();

    double* wired[MAX_CHANNELS * MAX_CHANNELS] = { nullptr };
    wire_batch_output(outs, NUMOUTS, NB, CO, PER_OUTLET, wired);
    // SHM row b*co+c -> flat b*PER_OUTLET+c
    for (long b = 0; b < NB; b++) {
        for (long c = 0; c < CO; c++) {
            assert(wired[b * CO + c] == outs[b * PER_OUTLET + c]);
        }
    }

    // Drain a full block: rows hold b*co+c's value, outlets must match.
    // Note: block_accumulate_read writes into the pointers given to it, so the
    // caller must advance them per tick (like the real perform64 gets fresh
    // per-tick Max buffers).
    std::vector<float> shm_buf(NB * CO * BLOCK, 0.0f);
    for (long r = 0; r < NB * CO; r++) {
        for (long i = 0; i < BLOCK; i++) shm_buf[r * BLOCK + i] = (float)(r + 1);
    }
    long pos = 0;
    for (int t = 0; t < 4; t++) {
        double* outs_tick[NUMOUTS];
        for (long o = 0; o < NUMOUTS; o++) outs_tick[o] = outlets[o].data() + (long)t * 512;
        double* wired[MAX_CHANNELS * MAX_CHANNELS] = { nullptr };
        wire_batch_output(outs_tick, NUMOUTS, NB, CO, PER_OUTLET, wired);
        block_accumulate_read(shm_buf.data(), NB * CO, BLOCK, 512,
                              wired, NB * CO, pos);
    }
    assert(pos == 0);
    for (long b = 0; b < NB; b++) {
        for (long c = 0; c < CO; c++) {
            for (long i = 0; i < BLOCK; i++) {
                assert(outlets[b * PER_OUTLET + c][i] == (double)(b * CO + c + 1));
            }
        }
    }
    printf("  OK\n");
}

static void test_chans_override_wiring() {
    printf("test_chans_override_wiring...\n");
    // decode: co=1, 4 batches, `chans 2` -> per_outlet = 2. numouts = 8.
    // Only flat indices b*2+0 (first channel of each outlet) are wired;
    // the second channel of each outlet must be silenced by perform64.
    const long CO = 1, NB = 4;
    const long PER_OUTLET = 2;   // chans override
    const long NUMOUTS = NB * PER_OUTLET;

    std::vector<double> outlets[NUMOUTS];
    for (long o = 0; o < NUMOUTS; o++) outlets[o].assign(BLOCK, 7.0);
    double* outs[NUMOUTS];
    for (long o = 0; o < NUMOUTS; o++) outs[o] = outlets[o].data();

    double* wired[MAX_CHANNELS * MAX_CHANNELS] = { nullptr };
    wire_batch_output(outs, NUMOUTS, NB, CO, PER_OUTLET, wired);
    for (long b = 0; b < NB; b++) assert(wired[b * CO + 0] == outs[b * PER_OUTLET + 0]);

    std::vector<float> shm_buf(NB * CO * BLOCK, 0.0f);
    for (long i = 0; i < BLOCK; i++) shm_buf[i] = 9.0f;  // batch 0 audio
    long pos = 0;
    for (int t = 0; t < 4; t++) {
        double* outs_tick[NUMOUTS];
        for (long o = 0; o < NUMOUTS; o++) outs_tick[o] = outlets[o].data() + (long)t * 512;
        double* wired_tick[MAX_CHANNELS * MAX_CHANNELS] = { nullptr };
        wire_batch_output(outs_tick, NUMOUTS, NB, CO, PER_OUTLET, wired_tick);
        block_accumulate_read(shm_buf.data(), NB * CO, BLOCK, 512,
                              wired_tick, NB * CO, pos);
        // perform64 silences extra outlet channels explicitly
        for (long b = 0; b < NB; b++) {
            long extra = b * PER_OUTLET + CO;
            if (extra < NUMOUTS) {
                for (long i = 0; i < 512; i++) outlets[extra][(long)t * 512 + i] = 0.0;
            }
        }
    }
    assert(pos == 0);
    for (long b = 0; b < NB; b++) {
        for (long i = 0; i < BLOCK; i++) {
            assert(outlets[b * PER_OUTLET + 0][i] == (b == 0 ? 9.0 : 0.0));
        }
        for (long i = 0; i < BLOCK; i++) {
            assert(outlets[b * PER_OUTLET + 1][i] == 0.0);  // silenced
        }
    }
    printf("  OK\n");
}

static void test_multichanneloutputs_chans_wins() {
    printf("test_multichanneloutputs_chans_wins...\n");
    McsState x = {};
    x.channels_out = 16;   // encode
    assert(mcs_multichanneloutputs(&x, 0, 0) == 16);   // auto -> channels_out
    x.n_batches = 2;                                   // chans 2
    assert(mcs_multichanneloutputs(&x, 0, 0) == 2);    // fixed wins
    x.channels_out = 1;                                // decode
    x.n_batches = 0;
    assert(mcs_multichanneloutputs(&x, 3, 0) == 1);    // per-outlet index agnostic
    printf("  OK\n");
}

static void test_inputchanged_updates_map_and_header() {
    printf("test_inputchanged_updates_map_and_header...\n");
    SharedMemoryHeader h = {};
    McsState x = {};
    x.header = &h;
    x.channels_in = 16;   // model layout must stay untouched

    mcs_inputchanged(&x, 0, 16);   // batch inlet 0: 16 latent channels
    assert(x.channel_map[0] == 16);
    assert(h.channel_map[0] == 16);
    assert(x.channels_in == 16);   // model layout untouched (no rebuild loop)

    mcs_inputchanged(&x, 3, 8);    // batch inlet 3: 8 channels
    assert(x.channel_map[3] == 8);
    assert(h.channel_map[3] == 8);

    // out-of-range index is ignored
    assert(mcs_inputchanged(&x, 16, 4) == 0);
    assert(mcs_inputchanged(&x, -1, 4) == 0);
    printf("  OK\n");
}

int main() {
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("=== mcs.mab~ (Phase 6) Tests ===\n\n");
    test_mcs_io_is_n_batches_in_n_batches_out();
    test_single_batch_falls_back_to_model_counts();
    test_batch_input_wiring_batch_major();
    test_partial_batch_zero_padded();
    test_output_wiring_and_extra_outlet_silenced();
    test_chans_override_wiring();
    test_multichanneloutputs_chans_wins();
    test_inputchanged_updates_map_and_header();
    printf("\n=== All tests passed! ===\n");
    return 0;
}
