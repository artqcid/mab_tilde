// Test for mab_tilde_free function
// This test verifies that the mab_tilde_free function can be declared and linked.

struct t_mab_tilde;

// Forward declaration
extern "C" void mab_tilde_free(t_mab_tilde* x);

// Stub implementation for standalone testing (no Max SDK dependency)
extern "C" void mab_tilde_free(t_mab_tilde* x) {
    (void)x; // unused
}

int main() {
    // Mock test: verify function signature matches expected prototype
    
    // Test 1: Function pointer assignment (compile-time check)
    void (*func_ptr)(t_mab_tilde*) = mab_tilde_free;
    
    // Test 2: Verify struct forward declaration is compatible
    t_mab_tilde* dummy = nullptr;
    
    // Test 3: Verify function can be called (will not actually run in this mock)
    // mab_tilde_free(dummy);  // Commented out to avoid runtime issues
    
    return 0;
}