// Tests for the Phase 5 mc.mab~ (multichannel) logic.
//
// These verify the pure C++ decisions that live in mab_tilde.cpp without
// linking against the Max SDK:
//   1. MC IO layout: always exactly 1 inlet + 1 outlet (mab_tilde.cpp
//      mab_tilde_apply_io), with the model's channel counts kept separately.
//   2. mc_multichanneloutputs: `chans` (n_batches) wins, else channels_out.
//   3. mc_inputchanged: channel_map update + header publish; the model layout
//      (channels_in) is NOT modified.
//   4. perform64 output drain: read_ch = min(channels_out, numouts), clamped
//      to >= 1, extra outlets zero-filled.
//   5. block_accumulator zero-padding: a decode inlet with fewer connected
//      channels than the model declares yields silence on the missing rows.

#include <cstdio>
#include <cassert>
#include <cstring>
#include <cstdint>
#include <vector>

#include "../source/projects/mab_tilde/block_accumulator.h"

static const long MAX_CHANNELS = 32;
static const long BLOCK = 2048;

// ---- SharedMemoryHeader (v3) - must mirror mab_tilde.cpp:36-67 ----
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
    uint32_t channel_map[32];
    long is_input_ready;
    long is_output_ready;
    long is_python_ready;
    long shutdown_flag;
};
static_assert(sizeof(SharedMemoryHeader) == 256,
              "header v3 must be 256 bytes (sync with mab_tilde.cpp)");

// ---- Minimal t_mab_tilde subset used by the MC helpers ----
struct McState {
    long is_mc;
    long channels_in;      // model layout (header-driven)
    long channels_out;     // model layout (header-driven)
    long n_batches;        // `chans` attribute (0 = auto)
    long channel_map[32];
    SharedMemoryHeader* header;
};

// Mirror of mab_tilde.cpp mc_multichanneloutputs (line ~1317)
static long mc_multichanneloutputs(McState* x, long index, long count) {
    (void)index; (void)count;
    if (x->n_batches > 0) {
        return x->n_batches;
    }
    return x->channels_out;
}

// Mirror of mab_tilde.cpp mc_inputchanged (line ~1327)
static long mc_inputchanged(McState* x, long index, long count) {
    if (index < 0 || index >= 16) return 0;
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

// Mirror of mab_tilde.cpp mab_tilde_apply_io MC decision (line ~650)
static void apply_io_decision(McState* x, long model_in, long model_out,
                              long* io_in, long* io_out) {
    if (model_in < 1) model_in = 1;
    if (model_out < 1) model_out = 1;
    if (model_in > MAX_CHANNELS) model_in = MAX_CHANNELS;
    if (model_out > MAX_CHANNELS) model_out = MAX_CHANNELS;
    x->channels_in = model_in;
    x->channels_out = model_out;
    *io_in = x->is_mc ? 1 : model_in;
    *io_out = x->is_mc ? 1 : model_out;
    if (x->is_mc) {
        for (long i = 0; i < MAX_CHANNELS; i++) {
            x->channel_map[i] = 0;
            if (x->header) x->header->channel_map[i] = 0;
        }
    }
}

// Mirror of the perform64 output drain decision (line ~1292)
static long output_read_channels(long channels_out, long numouts) {
    long read_ch = channels_out;
    if (read_ch > numouts) read_ch = numouts;
    if (read_ch < 1) read_ch = 1;
    return read_ch;
}

// ---------------------------------------------------------------------------

static void test_mc_io_is_always_1_in_1_out() {
    printf("test_mc_io_is_always_1_in_1_out...\n");
    // decode: model 16 in / 1 out -> MC box still 1 inlet / 1 outlet
    McState x = {};
    x.is_mc = 1;
    long io_in, io_out;
    apply_io_decision(&x, 16, 1, &io_in, &io_out);
    assert(io_in == 1);
    assert(io_out == 1);
    // the model layout must be preserved for perform64 / detection
    assert(x.channels_in == 16);
    assert(x.channels_out == 1);
    // stale channel_map from a previous method must be cleared
    for (long i = 0; i < MAX_CHANNELS; i++) assert(x.channel_map[i] == 0);

    // encode: model 1 in / 16 out -> MC box still 1 / 1
    apply_io_decision(&x, 1, 16, &io_in, &io_out);
    assert(io_in == 1);
    assert(io_out == 1);
    assert(x.channels_in == 1);
    assert(x.channels_out == 16);
    printf("  OK\n");
}

static void test_mono_io_keeps_model_counts() {
    printf("test_mono_io_keeps_model_counts...\n");
    McState x = {};
    x.is_mc = 0;
    long io_in, io_out;
    apply_io_decision(&x, 16, 1, &io_in, &io_out);
    assert(io_in == 16);   // mono decode: 16 individual inlets
    assert(io_out == 1);
    apply_io_decision(&x, 1, 16, &io_in, &io_out);
    assert(io_in == 1);
    assert(io_out == 16);
    printf("  OK\n");
}

static void test_multichanneloutputs_chans_wins() {
    printf("test_multichanneloutputs_chans_wins...\n");
    McState x = {};
    x.channels_out = 1;   // decode: mono output
    assert(mc_multichanneloutputs(&x, 0, 0) == 1);   // auto -> channels_out
    x.n_batches = 2;                                  // chans 2
    assert(mc_multichanneloutputs(&x, 0, 0) == 2);    // fixed wins
    x.channels_out = 16;  // encode
    x.n_batches = 0;
    assert(mc_multichanneloutputs(&x, 0, 0) == 16);
    printf("  OK\n");
}

static void test_inputchanged_updates_map_and_header() {
    printf("test_inputchanged_updates_map_and_header...\n");
    SharedMemoryHeader h = {};
    McState x = {};
    x.header = &h;
    x.channels_in = 16;   // model layout must stay untouched

    mc_inputchanged(&x, 0, 16);   // noise~16 on the single MC inlet
    assert(x.channel_map[0] == 16);
    assert(h.channel_map[0] == 16);
    assert(x.channels_in == 16);  // model layout untouched (no rebuild loop)

    mc_inputchanged(&x, 0, 8);    // reconnect with 8 channels
    assert(x.channel_map[0] == 8);
    assert(h.channel_map[0] == 8);
    assert(x.channels_in == 16);

    // out-of-range index is ignored
    assert(mc_inputchanged(&x, 16, 4) == 0);
    assert(mc_inputchanged(&x, -1, 4) == 0);
    printf("  OK\n");
}

static void test_output_drain_channel_math() {
    printf("test_output_drain_channel_math...\n");
    // decode mono: 1 model channel, 1 outlet
    assert(output_read_channels(1, 1) == 1);
    // decode + chans 2: only 1 model channel, extra outlet silenced
    assert(output_read_channels(1, 2) == 1);
    // encode + chans 2: model 16 channels, only 2 outlets -> truncate
    assert(output_read_channels(16, 2) == 2);
    // degenerate: no outlets must still yield >= 1 (read into nothing)
    assert(output_read_channels(16, 0) == 1);
    printf("  OK\n");
}

// 5.5: decode with 16 latent channels in one MC inlet, mono audio out.
// A full decode block must be produced by draining read_ch rows and leaving
// the extra `chans` outlet silent.
static void test_latent_decode_mc_roundtrip() {
    printf("test_latent_decode_mc_roundtrip...\n");
    const long CI = 16;   // latent channels (model decode input)
    const long CO = 1;    // audio channels (model decode output)
    const long VEC = 512; // 4 ticks per block

    // --- input side: 16 latent rows written from 16 connected channels ---
    std::vector<float> in_buf(CI * BLOCK, 0.0f);
    long in_pos = 0;
    for (int t = 0; t < 4; t++) {
        std::vector<std::vector<double>> vals(CI, std::vector<double>(VEC, 0.0));
        const double* ins[CI];
        for (long c = 0; c < CI; c++) {
            for (long i = 0; i < VEC; i++) vals[c][i] = (double)(c + 1);
            ins[c] = vals[c].data();
        }
        block_accumulate_write(in_buf.data(), CI, BLOCK, VEC, ins, CI, in_pos);
    }
    assert(in_pos == 0);
    for (long c = 0; c < CI; c++) {
        for (long i = 0; i < BLOCK; i++) {
            assert(in_buf[(long)c * BLOCK + i] == (float)(c + 1));
        }
    }

    // --- output side: drain 1 row into the audio outlet over 4 ticks ---
    std::vector<float> out_buf(CO * BLOCK, 0.0f);
    for (long i = 0; i < BLOCK; i++) out_buf[i] = 9.0f;  // model output
    std::vector<double> ch0(BLOCK, -1.0);                 // drained audio
    std::vector<std::vector<double>> extra(3, std::vector<double>(VEC, -1.0));
    long out_pos = 0;
    for (int t = 0; t < 4; t++) {
        double* outp[4] = { ch0.data() + (long)t * VEC, extra[0].data(),
                            extra[1].data(), extra[2].data() };
        long read_ch = output_read_channels(CO, 4);   // chans 4 on mono decode
        assert(read_ch == 1);
        block_accumulate_read(out_buf.data(), read_ch, BLOCK, VEC, outp, 4,
                              out_pos);
        // extra outlets (read_ch..numouts) must be silenced exactly like
        // mc_mab_tilde_perform64 does
        for (long ch = read_ch; ch < 4; ch++) {
            for (long i = 0; i < VEC; i++) extra[ch - read_ch][i] = 0.0;
        }
    }
    assert(out_pos == 0);
    for (long i = 0; i < BLOCK; i++) assert(ch0[i] == 9.0);   // audio out
    for (long e = 0; e < 3; e++) {
        for (long i = 0; i < VEC; i++) assert(extra[e][i] == 0.0); // silent
    }
    printf("  OK\n");
}

// 5.3: fewer connected channels than the model declares -> zero-padding
static void test_fewer_connected_channels_zero_padded() {
    printf("test_fewer_connected_channels_zero_padded...\n");
    const long CI = 16;
    const long CONNECTED = 8;  // only 8 channels reach the decode inlet
    std::vector<float> buf(CI * BLOCK, -1.0f);
    long pos = 0;
    for (int t = 0; t < 4; t++) {
        std::vector<std::vector<double>> vals(CONNECTED,
                                              std::vector<double>(512, 3.0));
        const double* ins[CONNECTED];
        for (long c = 0; c < CONNECTED; c++) ins[c] = vals[c].data();
        // perform64 passes the DECLARED count; block_accumulate_write
        // zero-pads channels >= numins
        block_accumulate_write(buf.data(), CI, BLOCK, 512, ins, CONNECTED, pos);
    }
    assert(pos == 0);
    for (long c = 0; c < CONNECTED; c++) {
        for (long i = 0; i < BLOCK; i++) assert(buf[(long)c * BLOCK + i] == 3.0f);
    }
    for (long c = CONNECTED; c < CI; c++) {
        for (long i = 0; i < BLOCK; i++) assert(buf[(long)c * BLOCK + i] == 0.0f);
    }
    printf("  OK\n");
}

int main() {
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("=== mc.mab~ (Phase 5) Tests ===\n\n");
    test_mc_io_is_always_1_in_1_out();
    test_mono_io_keeps_model_counts();
    test_multichanneloutputs_chans_wins();
    test_inputchanged_updates_map_and_header();
    test_output_drain_channel_math();
    test_latent_decode_mc_roundtrip();
    test_fewer_connected_channels_zero_padded();
    printf("\n=== All tests passed! ===\n");
    return 0;
}
