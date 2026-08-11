// Test for SharedMemoryHeader struct
// This test verifies that the SharedMemoryHeader struct has the correct layout.

#include <cstdint>
#include <cstring>
#include <cassert>

// Shared memory header structure (C-compatible, no C++ objects)
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

int main() {
    // Test 1: Verify struct size matches the contract (192 bytes, header v3)
    assert(sizeof(SharedMemoryHeader) == 192);
    
    // Test 2: Verify magic number constant
    uint32_t expected_magic = 0x4D414254; // 'MABT'
    assert(expected_magic == 0x4D414254);
    
    // Test 3: Verify struct can be initialized
    SharedMemoryHeader header = {};
    header.magic = 0x4D414254;
    header.version = 3;
    header.block_size = 512;
    header.num_channels = 1;
    header.channels_in = 1;
    header.channels_out = 1;
    header.input_ratio = 1;
    header.output_ratio = 1;
    strcpy(header.method, "forward");
    header.input_offset = sizeof(SharedMemoryHeader);
    header.output_offset = sizeof(SharedMemoryHeader) + 2 * 512 * sizeof(float);
    header.is_input_ready = 0;
    header.is_output_ready = 0;
    header.is_python_ready = 0;
    header.shutdown_flag = 0;
    
    // Test 4: Verify field values
    assert(header.magic == 0x4D414254);
    assert(header.version == 3);
    assert(header.block_size == 512);
    assert(header.num_channels == 1);
    assert(header.channels_in == 1);
    assert(header.channels_out == 1);
    assert(header.input_ratio == 1);
    assert(header.output_ratio == 1);
    assert(strcmp(header.method, "forward") == 0);
    assert(header.input_offset == sizeof(SharedMemoryHeader));
    assert(header.output_offset == sizeof(SharedMemoryHeader) + 2 * 512 * 4);
    assert(header.shutdown_flag == 0);
    
    // Test 5: Verify shutdown_flag can be set
    header.shutdown_flag = 1;
    assert(header.shutdown_flag == 1);

    // Test 6: Verify channel_map (Phase 5) can be read/written
    header.channel_map[0] = 16;
    header.channel_map[3] = 2;
    assert(header.channel_map[0] == 16);
    assert(header.channel_map[3] == 2);
    assert(header.channel_map[15] == 0);
    
    return 0;
}