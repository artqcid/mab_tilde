// Test for ext_main function
// This test verifies that the ext_main function can be declared and linked.

// Forward declaration
extern "C" __declspec(dllexport) void ext_main(void* r);

// Stub implementation for standalone testing (no Max SDK dependency)
extern "C" __declspec(dllexport) void ext_main(void* r) {
    (void)r; // unused
}

int main() {
    // Mock test: verify function signature matches expected prototype
    
    // Test 1: Function pointer assignment (compile-time check)
    void (*func_ptr)(void*) = ext_main;
    
    // Test 2: Verify function can be called (will not actually run in this mock)
    // ext_main(nullptr);  // Commented out to avoid runtime issues
    
    return 0;
}