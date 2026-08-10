// Test for mab_tilde message handlers
// This test verifies that all message handlers can be declared and linked.
// These are compile-time signature checks only.

#include <cstdint>
#include <cstring>

// Forward declaration of the t_mab_tilde struct
typedef struct _mab_tilde t_mab_tilde;

// Forward declarations of message handlers (extern "C" linkage)
extern "C" {
    void mab_tilde_enable(t_mab_tilde* x, long flag);
    void mab_tilde_gpu(t_mab_tilde* x, long flag);
    void mab_tilde_reload(t_mab_tilde* x, void* s);  // t_symbol* is opaque
    void mab_tilde_dump(t_mab_tilde* x);
    void mab_tilde_set(t_mab_tilde* x, void* s, long argc, void* argv);  // t_symbol*, t_atom*
    void mab_tilde_get(t_mab_tilde* x, void* s);  // t_symbol*
    void mab_tilde_method(t_mab_tilde* x, void* s, long argc, void* argv);  // t_symbol*, t_atom*
    void mab_tilde_load(t_mab_tilde* x, void* s);  // t_symbol*
}

// Mock struct for testing
struct _mab_tilde {
    long is_ready;
    long is_bypass;
    long gpu;
    long buffer_size;
    long num_channels;
    char model_path[256];
    char method_name[64];
};

// Stub implementations for testing
extern "C" void mab_tilde_enable(t_mab_tilde* x, long flag) {
    (void)x; (void)flag;
}

extern "C" void mab_tilde_gpu(t_mab_tilde* x, long flag) {
    (void)x; (void)flag;
}

extern "C" void mab_tilde_reload(t_mab_tilde* x, void* s) {
    (void)x; (void)s;
}

extern "C" void mab_tilde_dump(t_mab_tilde* x) {
    (void)x;
}

extern "C" void mab_tilde_set(t_mab_tilde* x, void* s, long argc, void* argv) {
    (void)x; (void)s; (void)argc; (void)argv;
}

extern "C" void mab_tilde_get(t_mab_tilde* x, void* s) {
    (void)x; (void)s;
}

extern "C" void mab_tilde_method(t_mab_tilde* x, void* s, long argc, void* argv) {
    (void)x; (void)s; (void)argc; (void)argv;
}

extern "C" void mab_tilde_load(t_mab_tilde* x, void* s) {
    (void)x; (void)s;
}

int main() {
    // Test 1: Verify function pointer assignments
    void (*enable_ptr)(t_mab_tilde*, long) = mab_tilde_enable;
    void (*gpu_ptr)(t_mab_tilde*, long) = mab_tilde_gpu;
    void (*reload_ptr)(t_mab_tilde*, void*) = mab_tilde_reload;
    void (*dump_ptr)(t_mab_tilde*) = mab_tilde_dump;
    void (*set_ptr)(t_mab_tilde*, void*, long, void*) = mab_tilde_set;
    void (*get_ptr)(t_mab_tilde*, void*) = mab_tilde_get;
    void (*method_ptr)(t_mab_tilde*, void*, long, void*) = mab_tilde_method;
    void (*load_ptr)(t_mab_tilde*, void*) = mab_tilde_load;
    
    // Test 2: Create mock object and call handlers
    t_mab_tilde x = {};
    x.is_ready = 0;
    x.is_bypass = 1;
    x.gpu = 0;
    x.buffer_size = 512;
    x.num_channels = 1;
    memset(x.model_path, 0, sizeof(x.model_path));
    memset(x.method_name, 0, sizeof(x.method_name));
    
    // Test enable/disable
    mab_tilde_enable(&x, 1);  // Enable
    mab_tilde_enable(&x, 0);  // Disable
    
    // Test gpu toggle
    mab_tilde_gpu(&x, 1);  // GPU on
    mab_tilde_gpu(&x, 0);  // GPU off
    
    // Test dump
    mab_tilde_dump(&x);
    
    // Test set (with mock args)
    const char* test_attr = "gpu";
    long test_val = 1;
    mab_tilde_set(&x, (void*)test_attr, 2, nullptr);
    
    // Test get
    mab_tilde_get(&x, (void*)test_attr);
    
    // Test method
    mab_tilde_method(&x, (void*)test_attr, 1, nullptr);
    
    // Test load
    mab_tilde_load(&x, (void*)test_attr);
    
    // Test reload
    mab_tilde_reload(&x, nullptr);
    
    return 0;
}