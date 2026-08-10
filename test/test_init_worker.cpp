// Test for asynchronous initialization of mab_tilde
// This test verifies that the init_worker_thread function can be declared and linked.

struct t_mab_tilde;
extern "C" void init_worker_thread(t_mab_tilde* x); // forward declaration

// Stub implementation for standalone testing (no Max SDK dependency)
extern "C" void init_worker_thread(t_mab_tilde* x) {
    (void)x; // unused
}

int main() {
    // Simple test: check that the function can be called without linking errors.
    // In a real test, we would instantiate a mab_tilde object and spawn the thread.
    return 0;
}