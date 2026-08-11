// Test for SharedMemoryHeader struct compatibility between C++ and Python
// This test verifies that the C++ and Python SharedMemoryHeader structures
// have identical memory layout and field offsets (header version 3).
//
// Build this test separately and run it to verify struct compatibility.

#include <cstdint>
#include <cstdio>
#include <cassert>
#include <cstring>
#include <cstddef>

// Shared memory header structure (must match Python's ctypes.Structure exactly)
// Version 3 adds the method-aware metadata (v2) plus the per-inlet MC channel
// map used by mc.mab~ (Phase 5).
struct SharedMemoryHeader {
    uint32_t magic;           // 0x4D414254 ('MABT')
    uint32_t version;         // 3
    uint32_t block_size;      // samples per audio block
    uint32_t num_channels;    // legacy channel count (== channels_out)
    uint32_t channels_in;     // active method: input channels
    uint32_t channels_out;    // active method: output channels
    uint32_t latent_size;     // latent dimension of the active method
    uint32_t input_ratio;     // active method: input ratio
    uint32_t output_ratio;    // active method: output ratio
    char     method[52];      // active method name
    uint32_t method_id;       // stable hash of method for atomic comparison
    uint32_t input_offset;    // bytes to input buffer
    uint32_t output_offset;   // bytes to output buffer
    uint32_t control_offset;  // bytes to control ring buffer
    uint32_t input_buffer_index;   // A1: index of input buffer C++ is filling (0/1)
    uint32_t output_buffer_index;  // A1: index of output buffer C++ is draining (0/1)
    uint32_t channel_map[16]; // Phase 5 (mc.mab~): per-inlet channel counts
    long is_input_ready;      // atomic flag (volatile)
    long is_output_ready;     // atomic flag (volatile)
    long is_python_ready;     // atomic flag (volatile)
    long shutdown_flag;       // atomic flag (C++ tells Python to die)
};

// Test that the struct has the expected field offsets
// These offsets must match Python's ctypes.Structure
void test_field_offsets() {
    printf("Testing SharedMemoryHeader field offsets...\n");

    size_t offset_magic = offsetof(SharedMemoryHeader, magic);
    size_t offset_version = offsetof(SharedMemoryHeader, version);
    size_t offset_block_size = offsetof(SharedMemoryHeader, block_size);
    size_t offset_num_channels = offsetof(SharedMemoryHeader, num_channels);
    size_t offset_channels_in = offsetof(SharedMemoryHeader, channels_in);
    size_t offset_channels_out = offsetof(SharedMemoryHeader, channels_out);
    size_t offset_latent_size = offsetof(SharedMemoryHeader, latent_size);
    size_t offset_input_ratio = offsetof(SharedMemoryHeader, input_ratio);
    size_t offset_output_ratio = offsetof(SharedMemoryHeader, output_ratio);
    size_t offset_method = offsetof(SharedMemoryHeader, method);
    size_t offset_input_offset = offsetof(SharedMemoryHeader, input_offset);
    size_t offset_output_offset = offsetof(SharedMemoryHeader, output_offset);
    size_t offset_control_offset = offsetof(SharedMemoryHeader, control_offset);
    size_t offset_is_input_ready = offsetof(SharedMemoryHeader, is_input_ready);
    size_t offset_is_output_ready = offsetof(SharedMemoryHeader, is_output_ready);
    size_t offset_is_python_ready = offsetof(SharedMemoryHeader, is_python_ready);
    size_t offset_shutdown_flag = offsetof(SharedMemoryHeader, shutdown_flag);

    printf("  magic offset: %zu\n", offset_magic);
    printf("  version offset: %zu\n", offset_version);
    printf("  block_size offset: %zu\n", offset_block_size);
    printf("  num_channels offset: %zu\n", offset_num_channels);
    printf("  channels_in offset: %zu\n", offset_channels_in);
    printf("  channels_out offset: %zu\n", offset_channels_out);
    printf("  latent_size offset: %zu\n", offset_latent_size);
    printf("  input_ratio offset: %zu\n", offset_input_ratio);
    printf("  output_ratio offset: %zu\n", offset_output_ratio);
    printf("  method offset: %zu\n", offset_method);
    printf("  input_offset offset: %zu\n", offset_input_offset);
    printf("  output_offset offset: %zu\n", offset_output_offset);
    printf("  control_offset offset: %zu\n", offset_control_offset);
    printf("  is_input_ready offset: %zu\n", offset_is_input_ready);
    printf("  is_output_ready offset: %zu\n", offset_is_output_ready);
    printf("  is_python_ready offset: %zu\n", offset_is_python_ready);
    printf("  shutdown_flag offset: %zu\n", offset_shutdown_flag);

    // Verify sequential layout for the uint32_t fields
    assert(offset_magic == 0);
    assert(offset_version == 4);
    assert(offset_block_size == 8);
    assert(offset_num_channels == 12);
    assert(offset_channels_in == 16);
    assert(offset_channels_out == 20);
    assert(offset_latent_size == 24);
    assert(offset_input_ratio == 28);
    assert(offset_output_ratio == 32);
    assert(offset_method == 36);

    // After method[52] + method_id (4): input_offset, output_offset, control_offset
    assert(offset_input_offset == 92);
    assert(offset_output_offset == 96);
    assert(offset_control_offset == 100);
    size_t offset_input_buffer_index = offsetof(SharedMemoryHeader, input_buffer_index);
    size_t offset_output_buffer_index = offsetof(SharedMemoryHeader, output_buffer_index);
    printf("  input_buffer_index offset: %zu\n", offset_input_buffer_index);
    printf("  output_buffer_index offset: %zu\n", offset_output_buffer_index);
    assert(offset_input_buffer_index == 104);
    assert(offset_output_buffer_index == 108);

    // Phase 5: channel_map[16] (uint32) right after the buffer indices
    size_t offset_channel_map = offsetof(SharedMemoryHeader, channel_map);
    printf("  channel_map offset: %zu\n", offset_channel_map);
    assert(offset_channel_map == 112);
    assert(sizeof(SharedMemoryHeader().channel_map) == 16 * sizeof(uint32_t));

    // long fields (4 bytes each on Windows MSVC) follow channel_map
    assert(offset_is_input_ready == 176);
    assert(offset_is_output_ready == 180);
    assert(offset_is_python_ready == 184);
    assert(offset_shutdown_flag == 188);

    printf("  All field offsets verified!\n");
}

// Test that the struct size is correct
void test_struct_size() {
    printf("Testing SharedMemoryHeader struct size...\n");

    size_t expected_size = 9 * sizeof(uint32_t) + 52 + sizeof(uint32_t)
                           + 3 * sizeof(uint32_t) + 2 * sizeof(uint32_t)
                           + 16 * sizeof(uint32_t)   // channel_map (Phase 5)
                           + 4 * sizeof(long);

    printf("  Expected size: %zu\n", expected_size);
    printf("  Actual size: %zu\n", sizeof(SharedMemoryHeader));

    assert(sizeof(SharedMemoryHeader) == 192);
    assert(sizeof(SharedMemoryHeader) == expected_size);
    printf("  Struct size verified!\n");
}

// Test that the struct can be used as a C-compatible header
void test_header_usage() {
    printf("Testing SharedMemoryHeader usage...\n");

    SharedMemoryHeader header = {};

    // Initialize header
    header.magic = 0x4D414254;  // 'MABT'
    header.version = 3;
    header.block_size = 2048;
    header.num_channels = 1;
    header.channels_in = 16;    // e.g. RAVE decode latent input
    header.channels_out = 1;    // mono audio output
    header.latent_size = 16;
    header.input_ratio = 2048;
    header.output_ratio = 1;
    strncpy(header.method, "decode", sizeof(header.method) - 1);
    header.input_offset = sizeof(SharedMemoryHeader);
    header.output_offset = sizeof(SharedMemoryHeader) + 2 * 16 * 2048 * sizeof(float);
    header.is_input_ready = 0;
    header.is_output_ready = 0;
    header.is_python_ready = 0;
    header.shutdown_flag = 0;
    header.channel_map[0] = 16;  // 16 latent channels on the single MC inlet

    // Verify values
    assert(header.magic == 0x4D414254);
    assert(header.version == 3);
    assert(header.block_size == 2048);
    assert(header.channels_in == 16);
    assert(header.channels_out == 1);
    assert(header.latent_size == 16);
    assert(header.input_ratio == 2048);
    assert(header.output_ratio == 1);
    assert(strcmp(header.method, "decode") == 0);
    assert(header.input_offset == sizeof(SharedMemoryHeader));
    assert(header.output_offset == sizeof(SharedMemoryHeader) + 2 * 16 * 2048 * 4);
    assert(header.channel_map[0] == 16);
    assert(header.channel_map[1] == 0);

    // Test atomic flag operations
    header.is_input_ready = 1;
    assert(header.is_input_ready == 1);

    header.shutdown_flag = 1;
    assert(header.shutdown_flag == 1);

    printf("  Header usage verified!\n");
}

// Test buffer offset calculations (method-aware layout)
void test_buffer_offsets() {
    printf("Testing buffer offset calculations...\n");

    const uint32_t block_size = 2048;
    const uint32_t max_channels_in = 16;
    const uint32_t max_channels_out = 16;

    SharedMemoryHeader header = {};
    header.magic = 0x4D414254;
    header.version = 2;
    header.block_size = block_size;
    header.channels_in = max_channels_in;
    header.channels_out = max_channels_out;
    header.input_offset = sizeof(SharedMemoryHeader);
    header.output_offset = sizeof(SharedMemoryHeader)
                           + 2 * block_size * max_channels_in * sizeof(float);

    size_t input_size = block_size * max_channels_in * sizeof(float);
    size_t output_size = block_size * max_channels_out * sizeof(float);
    size_t total_size = sizeof(SharedMemoryHeader) + 2 * input_size + 2 * output_size;

    printf("  Header size: %zu\n", sizeof(SharedMemoryHeader));
    printf("  Input size: %zu bytes\n", input_size);
    printf("  Output size: %zu bytes\n", output_size);
    printf("  Total size: %zu bytes\n", total_size);

    assert(header.input_offset == sizeof(SharedMemoryHeader));
    assert(header.output_offset == sizeof(SharedMemoryHeader) + 2 * input_size);

    printf("  Buffer offsets verified!\n");
}

// Test multi-channel layout
void test_multichannel_layout() {
    printf("Testing multi-channel memory layout...\n");

    const uint32_t block_size = 2048;
    const uint32_t channels = 4;

    SharedMemoryHeader header = {};
    header.magic = 0x4D414254;
    header.version = 2;
    header.block_size = block_size;
    header.channels_in = channels;
    header.channels_out = channels;
    header.input_offset = sizeof(SharedMemoryHeader);
    header.output_offset = sizeof(SharedMemoryHeader) + 2 * block_size * channels * sizeof(float);

    size_t total_samples = block_size * channels;
    size_t total_bytes = total_samples * sizeof(float);

    printf("  Channels: %u\n", channels);
    printf("  Total samples: %zu\n", total_samples);
    printf("  Total bytes: %zu\n", total_bytes);

    assert(header.output_offset == sizeof(SharedMemoryHeader) + 2 * total_bytes);

    printf("  Multi-channel layout verified!\n");
}

int main() {
    printf("=== SharedMemoryHeader Compatibility Tests (v3) ===\n\n");

    test_field_offsets();
    printf("\n");

    test_struct_size();
    printf("\n");

    test_header_usage();
    printf("\n");

    test_buffer_offsets();
    printf("\n");

    test_multichannel_layout();
    printf("\n");

    printf("=== All tests passed! ===\n");
    return 0;
}
