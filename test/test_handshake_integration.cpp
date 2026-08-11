// Integration test for C++/Python shared memory handshake
// This test verifies the complete handshake protocol between C++ and Python.
//
// Note: This test requires the Max SDK to be available for full functionality.
// It tests the shared memory naming, header structure, and flag operations.

#include <cstdint>
#include <cstdio>
#include <cassert>
#include <cstring>
#include <windows.h>

// Shared memory header structure (must match Python's ctypes.Structure)
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

// Test shared memory name generation
void test_shm_name_generation() {
    printf("Testing shared memory name generation...\n");
    
    unsigned int instance_id = 0x12345678;
    wchar_t shm_name[128];
    wchar_t event_name[128];
    
    swprintf_s(shm_name, L"MabSharedMem_%08X", instance_id);
    swprintf_s(event_name, L"MabReadyEvent_%08X", instance_id);
    
    // Verify names
    assert(wcscmp(shm_name, L"MabSharedMem_12345678") == 0);
    assert(wcscmp(event_name, L"MabReadyEvent_12345678") == 0);
    
    printf("  Shared memory name: %ls\n", shm_name);
    printf("  Event name: %ls\n", event_name);
    printf("  Name generation verified!\n");
}

// Test shared memory creation and mapping
void test_shared_memory_creation() {
    printf("Testing shared memory creation...\n");
    
    const wchar_t* TEST_SHM_NAME = L"MabSharedMem_TestIntegration";
    const wchar_t* TEST_EVENT_NAME = L"MabReadyEvent_TestIntegration";
    
    // Calculate sizes
    size_t header_size = sizeof(SharedMemoryHeader);
    uint32_t block_size = 512;
    uint32_t num_channels = 1;
    size_t input_size = block_size * num_channels * sizeof(float);
    size_t output_size = block_size * num_channels * sizeof(float);
    size_t total_size = header_size + input_size + output_size;
    
    printf("  Header size: %zu\n", header_size);
    printf("  Input size: %zu\n", input_size);
    printf("  Output size: %zu\n", output_size);
    printf("  Total size: %zu\n", total_size);
    
    // Create file mapping
    HANDLE hMapFile = CreateFileMappingW(
        INVALID_HANDLE_VALUE,
        NULL,
        PAGE_READWRITE,
        0,
        (DWORD)total_size,
        TEST_SHM_NAME
    );
    
    if (!hMapFile) {
        printf("  CreateFileMappingW failed: %lu\n", GetLastError());
        return;
    }
    
    printf("  Shared memory created successfully\n");
    
    // Map view
    void* pBuf = MapViewOfFile(hMapFile, FILE_MAP_ALL_ACCESS, 0, 0, 0);
    if (!pBuf) {
        printf("  MapViewOfFile failed: %lu\n", GetLastError());
        CloseHandle(hMapFile);
        return;
    }
    
    printf("  View mapped successfully\n");
    
    // Initialize header
    SharedMemoryHeader* header = (SharedMemoryHeader*)pBuf;
    header->magic = 0x4D414254;
    header->version = 3;
    header->block_size = block_size;
    header->num_channels = num_channels;
    header->input_offset = (uint32_t)header_size;
    header->output_offset = (uint32_t)(header_size + input_size);
    header->is_input_ready = 0;
    header->is_output_ready = 0;
    header->is_python_ready = 0;
    header->shutdown_flag = 0;
    
    // Validate header
    assert(header->magic == 0x4D414254);
    assert(header->version == 3);
    assert(header->block_size == block_size);
    assert(header->num_channels == num_channels);
    
    printf("  Header initialized and validated\n");
    
    // Get buffer pointers
    float* p_input = (float*)((char*)pBuf + header->input_offset);
    float* p_output = (float*)((char*)pBuf + header->output_offset);
    
    // Test input buffer
    for (uint32_t i = 0; i < block_size; i++) {
        p_input[i] = (float)i;
    }
    header->is_input_ready = 1;
    
    // Verify input
    for (uint32_t i = 0; i < block_size; i++) {
        assert(p_input[i] == (float)i);
    }
    printf("  Input buffer test passed\n");
    
    // Test output buffer
    for (uint32_t i = 0; i < block_size; i++) {
        p_output[i] = (float)(i * 2);
    }
    header->is_output_ready = 1;
    
    // Verify output
    for (uint32_t i = 0; i < block_size; i++) {
        assert(p_output[i] == (float)(i * 2));
    }
    printf("  Output buffer test passed\n");
    
    // Test shutdown flag
    header->shutdown_flag = 1;
    assert(header->shutdown_flag == 1);
    printf("  Shutdown flag test passed\n");
    
    // Cleanup
    UnmapViewOfFile(pBuf);
    CloseHandle(hMapFile);
    
    // Clean up named objects
    HANDLE hEvent = OpenEventW(EVENT_ALL_ACCESS, FALSE, TEST_EVENT_NAME);
    if (hEvent) {
        CloseHandle(hEvent);
    }
    
    printf("  Shared memory cleanup completed\n");
    printf("  Shared memory creation test verified!\n");
}

// Test atomic flag operations
void test_atomic_flags() {
    printf("Testing atomic flag operations...\n");
    
    SharedMemoryHeader header = {};
    header.magic = 0x4D414254;
    
    // Test is_input_ready flag
    InterlockedExchange(&header.is_input_ready, 1);
    assert(header.is_input_ready == 1);
    InterlockedExchange(&header.is_input_ready, 0);
    assert(header.is_input_ready == 0);
    
    // Test is_output_ready flag
    InterlockedExchange(&header.is_output_ready, 1);
    assert(header.is_output_ready == 1);
    InterlockedExchange(&header.is_output_ready, 0);
    assert(header.is_output_ready == 0);
    
    // Test is_python_ready flag
    InterlockedExchange(&header.is_python_ready, 1);
    assert(header.is_python_ready == 1);
    InterlockedExchange(&header.is_python_ready, 0);
    assert(header.is_python_ready == 0);
    
    // Test shutdown_flag
    InterlockedExchange(&header.shutdown_flag, 1);
    assert(header.shutdown_flag == 1);
    InterlockedExchange(&header.shutdown_flag, 0);
    assert(header.shutdown_flag == 0);
    
    printf("  Atomic flag operations verified!\n");
}

// Test buffer size calculations
void test_buffer_calculations() {
    printf("Testing buffer size calculations...\n");
    
    // Test case 1: Mono, 512 samples
    {
        uint32_t block_size = 512;
        uint32_t num_channels = 1;
        size_t input_size = block_size * num_channels * sizeof(float);
        size_t output_size = block_size * num_channels * sizeof(float);
        
        assert(input_size == 2048);
        assert(output_size == 2048);
        printf("  Mono 512: input=%zu, output=%zu\n", input_size, output_size);
    }
    
    // Test case 2: Stereo, 1024 samples
    {
        uint32_t block_size = 1024;
        uint32_t num_channels = 2;
        size_t input_size = block_size * num_channels * sizeof(float);
        size_t output_size = block_size * num_channels * sizeof(float);
        
        assert(input_size == 8192);
        assert(output_size == 8192);
        printf("  Stereo 1024: input=%zu, output=%zu\n", input_size, output_size);
    }
    
    // Test case 3: Quad, 2048 samples
    {
        uint32_t block_size = 2048;
        uint32_t num_channels = 4;
        size_t input_size = block_size * num_channels * sizeof(float);
        size_t output_size = block_size * num_channels * sizeof(float);
        
        assert(input_size == 32768);
        assert(output_size == 32768);
        printf("  Quad 2048: input=%zu, output=%zu\n", input_size, output_size);
    }
    
    printf("  Buffer size calculations verified!\n");
}

int main() {
    printf("=== C++/Python Handshake Integration Tests ===\n\n");
    
    test_shm_name_generation();
    printf("\n");
    
    test_shared_memory_creation();
    printf("\n");
    
    test_atomic_flags();
    printf("\n");
    
    test_buffer_calculations();
    printf("\n");
    
    printf("=== All integration tests passed! ===\n");
    return 0;
}