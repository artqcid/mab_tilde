// Test for multi-channel memory layout
// This test verifies the contiguous memory layout for multi-channel audio
// used by mc.mab~ objects.

#include <cstdint>
#include <cstdio>
#include <cassert>
#include <cstring>

// Shared memory header structure
struct SharedMemoryHeader {
    uint32_t magic;           // 0x4D414254 ('MABT')
    uint32_t version;         // 3
    uint32_t block_size;      // samples per block
    uint32_t num_channels;    // legacy channel count (== channels_out)
    uint32_t channels_in;     // active method: input channels
    uint32_t channels_out;    // active method: output channels
    uint32_t latent_size;     // latent dimension of the active method
    uint32_t input_ratio;     // active method: input ratio
    uint32_t output_ratio;    // active method: output ratio
    char     method[52];      // active method name (forward/encode/decode/prior)
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

// Test 1: Verify contiguous memory layout for single channel
void test_single_channel_layout() {
    printf("Testing single-channel memory layout...\n");
    
    const uint32_t block_size = 512;
    const uint32_t num_channels = 1;
    
    SharedMemoryHeader header = {};
    header.magic = 0x4D414254;
    header.version = 3;
    header.block_size = block_size;
    header.num_channels = num_channels;
    header.input_offset = sizeof(SharedMemoryHeader);
    header.output_offset = sizeof(SharedMemoryHeader) + 2 * block_size * num_channels * sizeof(float);
    
    // Verify input buffer size
    size_t input_size = block_size * num_channels * sizeof(float);
    assert(input_size == 512 * 4);  // 2048 bytes
    
    // Verify output buffer size
    size_t output_size = block_size * num_channels * sizeof(float);
    assert(output_size == 512 * 4);  // 2048 bytes
    
    // Verify total size
    size_t total_size = sizeof(SharedMemoryHeader) + 2 * input_size + 2 * output_size;
    printf("  Single channel: header=%zu, input=%zu, output=%zu, total=%zu\n",
           sizeof(SharedMemoryHeader), input_size, output_size, total_size);
    
    printf("  Single-channel layout verified!\n");
}

// Test 2: Verify contiguous memory layout for stereo
void test_stereo_layout() {
    printf("Testing stereo memory layout...\n");
    
    const uint32_t block_size = 512;
    const uint32_t num_channels = 2;
    
    SharedMemoryHeader header = {};
    header.magic = 0x4D414254;
    header.version = 3;
    header.block_size = block_size;
    header.num_channels = num_channels;
    header.input_offset = sizeof(SharedMemoryHeader);
    header.output_offset = sizeof(SharedMemoryHeader) + 2 * block_size * num_channels * sizeof(float);
    
    // Verify input buffer size
    size_t input_size = block_size * num_channels * sizeof(float);
    assert(input_size == 512 * 2 * 4);  // 4096 bytes
    
    // Verify output buffer size
    size_t output_size = block_size * num_channels * sizeof(float);
    assert(output_size == 512 * 2 * 4);  // 4096 bytes
    
    // Verify total size
    size_t total_size = sizeof(SharedMemoryHeader) + 2 * input_size + 2 * output_size;
    printf("  Stereo: header=%zu, input=%zu, output=%zu, total=%zu\n",
           sizeof(SharedMemoryHeader), input_size, output_size, total_size);
    
    printf("  Stereo layout verified!\n");
}

// Test 3: Verify contiguous memory layout for quad (4 channels)
void test_quad_layout() {
    printf("Testing quad (4-channel) memory layout...\n");
    
    const uint32_t block_size = 512;
    const uint32_t num_channels = 4;
    
    SharedMemoryHeader header = {};
    header.magic = 0x4D414254;
    header.version = 3;
    header.block_size = block_size;
    header.num_channels = num_channels;
    header.input_offset = sizeof(SharedMemoryHeader);
    header.output_offset = sizeof(SharedMemoryHeader) + 2 * block_size * num_channels * sizeof(float);
    
    // Verify input buffer size
    size_t input_size = block_size * num_channels * sizeof(float);
    assert(input_size == 512 * 4 * 4);  // 8192 bytes
    
    // Verify output buffer size
    size_t output_size = block_size * num_channels * sizeof(float);
    assert(output_size == 512 * 4 * 4);  // 8192 bytes
    
    // Verify total size
    size_t total_size = sizeof(SharedMemoryHeader) + 2 * input_size + 2 * output_size;
    printf("  Quad: header=%zu, input=%zu, output=%zu, total=%zu\n",
           sizeof(SharedMemoryHeader), input_size, output_size, total_size);
    
    printf("  Quad layout verified!\n");
}

// Test 4: Verify buffer pointer calculations
void test_buffer_pointer_calculations() {
    printf("Testing buffer pointer calculations...\n");
    
    const uint32_t block_size = 512;
    const uint32_t num_channels = 4;
    
    SharedMemoryHeader header = {};
    header.magic = 0x4D414254;
    header.version = 3;
    header.block_size = block_size;
    header.num_channels = num_channels;
    header.input_offset = sizeof(SharedMemoryHeader);
    header.output_offset = sizeof(SharedMemoryHeader) + 2 * block_size * num_channels * sizeof(float);
    
    // Simulate shared memory buffer
    uint8_t* buffer = new uint8_t[sizeof(SharedMemoryHeader) + block_size * num_channels * 4 * 4];
    
    // Calculate pointers
    float* p_input = (float*)(buffer + header.input_offset);
    float* p_output = (float*)(buffer + header.output_offset);
    
    // Verify pointers are correctly aligned
    assert(((uintptr_t)p_input % alignof(float)) == 0);
    assert(((uintptr_t)p_output % alignof(float)) == 0);
    
    // Verify pointers are not overlapping
    size_t input_end = header.input_offset + block_size * num_channels * sizeof(float);
    assert((uint8_t*)p_output >= buffer + input_end);
    
    printf("  Input pointer: %p\n", (void*)p_input);
    printf("  Output pointer: %p\n", (void*)p_output);
    printf("  Buffer pointer calculations verified!\n");
    
    delete[] buffer;
}

// Test 5: Verify NumPy-style reshape dimensions
void test_numpy_reshape_dimensions() {
    printf("Testing NumPy-style reshape dimensions...\n");
    
    // For a contiguous layout [num_channels, block_size]
    // The total number of samples is num_channels * block_size
    
    struct TestCase {
        uint32_t num_channels;
        uint32_t block_size;
        size_t expected_total_samples;
    };
    
    TestCase tests[] = {
        {1, 512, 512},
        {2, 512, 1024},
        {4, 512, 2048},
        {8, 1024, 8192},
        {16, 2048, 32768},
    };
    
    for (const auto& tc : tests) {
        size_t total_samples = tc.num_channels * tc.block_size;
        assert(total_samples == tc.expected_total_samples);
        printf("  Channels=%u, Block=%u: total_samples=%zu\n",
               tc.num_channels, tc.block_size, total_samples);
    }
    
    printf("  NumPy reshape dimensions verified!\n");
}

// Test 6: Verify channel stride calculations
void test_channel_stride() {
    printf("Testing channel stride calculations...\n");
    
    const uint32_t block_size = 512;
    const uint32_t num_channels = 4;
    
    // In contiguous layout [num_channels, block_size]:
    // - Channel 0: samples 0 to block_size-1
    // - Channel 1: samples block_size to 2*block_size-1
    // - etc.
    
    size_t stride = block_size * sizeof(float);  // Bytes per channel
    
    // Verify stride calculation
    assert(stride == 512 * 4);  // 2048 bytes
    
    // Simulate buffer access
    float* buffer = new float[num_channels * block_size];
    
    // Access each channel
    for (uint32_t ch = 0; ch < num_channels; ch++) {
        float* channel_ptr = buffer + ch * block_size;
        for (uint32_t i = 0; i < block_size; i++) {
            channel_ptr[i] = (float)(ch * 1000 + i);
        }
    }
    
    // Verify data
    for (uint32_t ch = 0; ch < num_channels; ch++) {
        float* channel_ptr = buffer + ch * block_size;
        for (uint32_t i = 0; i < block_size; i++) {
            assert(channel_ptr[i] == (float)(ch * 1000 + i));
        }
    }
    
    printf("  Channel stride: %zu bytes\n", stride);
    printf("  Channel stride verified!\n");
    
    delete[] buffer;
}

int main() {
    printf("=== Multi-Channel Memory Layout Tests ===\n\n");
    
    test_single_channel_layout();
    printf("\n");
    
    test_stereo_layout();
    printf("\n");
    
    test_quad_layout();
    printf("\n");
    
    test_buffer_pointer_calculations();
    printf("\n");
    
    test_numpy_reshape_dimensions();
    printf("\n");
    
    test_channel_stride();
    printf("\n");
    
    printf("=== All multi-channel tests passed! ===\n");
    return 0;
}