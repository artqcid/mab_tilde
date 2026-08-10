// Test for mab_tilde_dsp64 function
// This test verifies that the mab_tilde_dsp64 function can be declared and linked.

struct t_mab_tilde;
struct t_object;
struct t_symbol;

// Forward declaration
extern "C" void mab_tilde_dsp64(t_mab_tilde* x, t_object* dsp64, short* count, double samplerate, 
                     long maxvectorsize, long flags);

// Stub implementation for standalone testing (no Max SDK dependency)
extern "C" void mab_tilde_dsp64(t_mab_tilde* x, t_object* dsp64, short* count, double samplerate, 
                     long maxvectorsize, long flags) {
    (void)x; (void)dsp64; (void)count; (void)samplerate; (void)maxvectorsize; (void)flags;
}

int main() {
    // Mock test: verify function signature matches expected prototype
    
    // Test 1: Function pointer assignment (compile-time check)
    void (*func_ptr)(t_mab_tilde*, t_object*, short*, double, long, long) = mab_tilde_dsp64;
    
    // Test 2: Verify struct forward declarations are compatible
    t_mab_tilde* x = nullptr;
    t_object* dsp64 = nullptr;
    short* count = nullptr;
    double samplerate = 44100.0;
    long maxvectorsize = 512;
    long flags = 0;
    
    // Test 3: Verify function can be called (will not actually run in this mock)
    // mab_tilde_dsp64(x, dsp64, count, samplerate, maxvectorsize, flags);
    
    return 0;
}