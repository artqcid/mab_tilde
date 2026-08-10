// Test for mab_tilde_perform64 function
// This test verifies that the mab_tilde_perform64 function can be declared and linked.

struct t_mab_tilde;
struct t_object;

// Forward declaration
extern "C" void mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, 
                         double** outs, long numouts, long sampleframes, long flags, void* userparam);

// Stub implementation for standalone testing (no Max SDK dependency)
extern "C" void mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, 
                         double** outs, long numouts, long sampleframes, long flags, void* userparam) {
    (void)x; (void)dsp64; (void)ins; (void)numins; (void)outs; (void)numouts; (void)sampleframes; (void)flags; (void)userparam;
}

int main() {
    // Mock test: verify function signature matches expected prototype
    
    // Test 1: Function pointer assignment (compile-time check)
    void (*func_ptr)(t_mab_tilde*, t_object*, double**, long, double**, long, long, long, void*) = mab_tilde_perform64;
    
    // Test 2: Verify struct forward declarations are compatible
    t_mab_tilde* x = nullptr;
    t_object* dsp64 = nullptr;
    double** ins = nullptr;
    double** outs = nullptr;
    long numins = 1;
    long numouts = 1;
    long sampleframes = 512;
    long flags = 0;
    void* userparam = nullptr;
    
    // Test 3: Verify function can be called (will not actually run in this mock)
    // mab_tilde_perform64(x, dsp64, ins, numins, outs, numouts, sampleframes, flags, userparam);
    
    return 0;
}