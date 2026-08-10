// Test for shared memory management functionality
// This test verifies that the SharedMemoryHeader struct can be
// created, validated, and mapped correctly using Windows API.
//
// Build this test separately and run it to verify shared memory
// creation and mapping logic.

#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>

// Shared memory header structure (must match the definition in mab_tilde.cpp)
struct SharedMemoryHeader {
    uint32_t magic;           // 0x4D414254 ('MABT')
    uint32_t version;         // 1
    uint32_t block_size;      // samples per block
    uint32_t num_channels;    // 1 for mab~, up to 16 for mc.mab~
    uint32_t input_offset;    // bytes to input buffer
    uint32_t output_offset;   // bytes to output buffer
    long is_input_ready;      // atomic flag (volatile)
    long is_output_ready;     // atomic flag (volatile)
    long is_python_ready;     // atomic flag (volatile)
    long shutdown_flag;       // atomic flag (C++ tells Python to die)
};

int main() {
    // Test shared memory creation and validation
    const wchar_t* SHM_NAME = L"MabSharedMem_Test";
    const wchar_t* EVENT_NAME = L"MabReadyEvent_Test";

    // Step 1: Create file mapping
    HANDLE hMapFile = CreateFileMappingW(
        NULL, 
        NULL, 
        PAGE_READWRITE, 
        0, 
        4096, 
        SHM_NAME
    );

    if (!hMapFile) {
        printf("CreateFileMappingW failed (%lu)\n", GetLastError());
        return 1;
    }

    // Step 2: Map view of the file
    void* pBuf = MapViewOfFile(hMapFile, FILE_MAP_ALL_ACCESS, 0, 0, 0);
    if (!pBuf) {
        printf("MapViewOfFile failed (%lu)\n", GetLastError());
        CloseHandle(hMapFile);
        return 1;
    }

    // Step 3: Fill header
    SharedMemoryHeader* header = (SharedMemoryHeader*)pBuf;
    header->magic = 0x4D414254; // 'MABT'
    header->version = 1;
    header->block_size = 512;
    header->num_channels = 1;
    header->input_offset = sizeof(SharedMemoryHeader);
    header->output_offset = sizeof(SharedMemoryHeader) + 512 * 1 * sizeof(float);
    header->is_input_ready = 0;
    header->is_output_ready = 0;
    header->is_python_ready = 0;
    header->shutdown_flag = 0;

    // Step 4: Validate magic number
    if (header->magic != 0x4D414254) {
        printf("Invalid magic number: 0x%08X\n", header->magic);
        UnmapViewOfFile(pBuf);
        CloseHandle(hMapFile);
        return 1;
    }
    printf("Magic number validated: 0x%08X\n", header->magic);

    // Step 5: Compute pointers
    float* p_input = (float*)((char*)pBuf + header->input_offset);
    float* p_output = (float*)((char*)pBuf + header->output_offset);
    printf("input offset: %u, output offset: %u\n", header->input_offset, header->output_offset);
    printf("p_input: %p, p_output: %p\n", p_input, p_output);

    // Step 6: Test writing input buffer
    for (int i = 0; i < header->block_size; i++) {
        p_input[i] = (float)i;
    }
    printf("Wrote %d samples to input buffer.\n", header->block_size);

    // Step 7: Clean up
    UnmapViewOfFile(pBuf);
    CloseHandle(hMapFile);
    printf("Shared memory test completed successfully.\n");
    return 0;
}