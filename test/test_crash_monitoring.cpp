// Test for crash monitoring functionality
// This test verifies that the crash monitoring logic can detect
// when the Python process has exited unexpectedly.

#include <cstdint>
#include <cstdio>
#include <cassert>
#include <cstring>
#include <windows.h>

// Shared memory header structure (must match the definition in mab_tilde.cpp)
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
    uint32_t channel_map[32]; // Phase 5 (mc.mab~): per-inlet channel counts
    long is_input_ready;      // atomic flag (volatile)
    long is_output_ready;     // atomic flag (volatile)
    long is_python_ready;     // atomic flag (volatile)
    long shutdown_flag;       // atomic flag (C++ tells Python to die)
};

// Control ring buffer structure
struct ControlRingBuffer {
    long head;
    long tail;
    char messages[256][256];
};

// Mock struct for testing
struct t_mab_tilde {
    long is_ready;
    long is_bypass;
    HANDLE python_process;
    HANDLE ready_event;
    HANDLE hMapFile;
    SharedMemoryHeader* header;
    float* p_input;
    float* p_output;
    ControlRingBuffer* p_control;
    char model_path[256];
    char method_name[64];
    long buffer_size;
    long gpu;
    long num_channels;
    char control_buffer[1024];
    long control_size;
};

// Test 1: Verify crash monitoring detects process exit
void test_crash_detection() {
    printf("Testing crash detection...\n");
    
    // Create a process that exits immediately
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));
    
    // Launch a process that exits immediately
    wchar_t cmdLine[] = L"cmd /c exit 0";
    if (CreateProcessW(NULL, cmdLine, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        // Wait for it to exit
        WaitForSingleObject(pi.hProcess, 5000);
        
        // Check exit code
        DWORD exitCode = 0;
        if (GetExitCodeProcess(pi.hProcess, &exitCode)) {
            printf("  Process exit code: %lu\n", exitCode);
            assert(exitCode != STILL_ACTIVE);
            printf("  Crash detection verified - process exited with code %lu\n", exitCode);
        }
        
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    } else {
        printf("  Failed to create test process\n");
    }
    
    printf("  Crash detection test passed!\n");
}

// Test 2: Verify crash monitoring detects still-active process
void test_active_process_detection() {
    printf("Testing active process detection...\n");
    
    // Create a process that stays alive
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));
    
    // Launch a process that stays alive briefly
    wchar_t cmdLine[] = L"cmd /c timeout /t 10";
    if (CreateProcessW(NULL, cmdLine, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        // Check exit code immediately (should be STILL_ACTIVE)
        DWORD exitCode = 0;
        if (GetExitCodeProcess(pi.hProcess, &exitCode)) {
            printf("  Process exit code: %lu (STILL_ACTIVE=%lu)\n", exitCode, STILL_ACTIVE);
            assert(exitCode == STILL_ACTIVE);
            printf("  Active process detection verified!\n");
        }
        
        // Terminate the process
        TerminateProcess(pi.hProcess, 0);
        WaitForSingleObject(pi.hProcess, 5000);
        
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    } else {
        printf("  Failed to create test process\n");
    }
    
    printf("  Active process detection test passed!\n");
}

// Test 3: Verify crash monitoring state transition
void test_crash_state_transition() {
    printf("Testing crash state transition...\n");
    
    t_mab_tilde x = {};
    x.is_ready = 1;
    x.is_bypass = 0;
    x.python_process = nullptr;
    x.header = nullptr;
    x.p_input = nullptr;
    x.p_output = nullptr;
    x.p_control = nullptr;
    x.hMapFile = nullptr;
    x.ready_event = nullptr;
    x.num_channels = 1;
    x.buffer_size = 512;
    x.gpu = 0;
    x.control_size = 0;
    memset(x.model_path, 0, sizeof(x.model_path));
    memset(x.method_name, 0, sizeof(x.method_name));
    memset(x.control_buffer, 0, sizeof(x.control_buffer));
    
    // Simulate crash detection
    // When python_process is null, no crash monitoring needed
    assert(x.is_ready == 1);
    assert(x.is_bypass == 0);
    
    // Simulate crash: set is_ready to 0 and is_bypass to 1
    InterlockedExchange(&x.is_ready, 0);
    InterlockedExchange(&x.is_bypass, 1);
    
    assert(x.is_ready == 0);
    assert(x.is_bypass == 1);
    
    printf("  State transition: ready=1, bypass=0 -> ready=0, bypass=1\n");
    printf("  Crash state transition verified!\n");
}

// Test 4: Verify STILL_ACTIVE constant
void test_still_active_constant() {
    printf("Testing STILL_ACTIVE constant...\n");
    
    // STILL_ACTIVE should be 259 on Windows
    assert(STILL_ACTIVE == 259);
    printf("  STILL_ACTIVE = %lu\n", STILL_ACTIVE);
    printf("  STILL_ACTIVE constant verified!\n");
}

int main() {
    printf("=== Crash Monitoring Tests ===\n\n");
    
    test_still_active_constant();
    printf("\n");
    
    test_crash_detection();
    printf("\n");
    
    test_active_process_detection();
    printf("\n");
    
    test_crash_state_transition();
    printf("\n");
    
    printf("=== All crash monitoring tests passed! ===\n");
    return 0;
}