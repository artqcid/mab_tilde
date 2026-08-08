#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

#include "ext.h"
#include "ext_obex.h"
#include "z_dsp.h"

static t_class* mab_tilde_class = nullptr;

typedef struct _mab_tilde {
    t_pxobject ob;
    long is_ready;
    long is_bypass;
} t_mab_tilde;

// Funktionsprototypen
void* mab_tilde_new(t_symbol* s, long argc, t_atom* argv);
void mab_tilde_free(t_mab_tilde* x);
void mab_tilde_assist(t_mab_tilde* x, void* b, long m, long a, char* s);
void mab_tilde_dsp64(t_mab_tilde* x, t_object* dsp64, short* count, double samplerate, long maxvectorsize, long flags);
void mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, double** outs, long numouts, long sampleframes, long flags, void* userparam);

// Korrekter Einstiegspunkt mit C-Linkage für C++ Dateien
extern "C" {
    C74_EXPORT void ext_main(void* r) {
        t_class* c = class_new("mab~",
                               (method)mab_tilde_new,
                               (method)mab_tilde_free,
                               (long)sizeof(t_mab_tilde),
                               0L,
                               A_GIMME,
                               0);

        class_addmethod(c, (method)mab_tilde_dsp64, "dsp64", A_CANT, 0);
        class_addmethod(c, (method)mab_tilde_assist, "assist", A_CANT, 0);

        class_dspinit(c);
        class_register(CLASS_BOX, c);
        mab_tilde_class = c;

        post("mab~: Native Max SDK external loaded successfully.");
    }
}

void* mab_tilde_new(t_symbol* s, long argc, t_atom* argv) {
    t_mab_tilde* x = (t_mab_tilde*)object_alloc(mab_tilde_class);
    if (x) {
        dsp_setup((t_pxobject*)x, 1);
        outlet_new(x, "signal");
        x->is_ready = 0;
        x->is_bypass = 1; // Start im sicheren Pass-Through Modus
    }
    return x;
}

void mab_tilde_free(t_mab_tilde* x) {
    dsp_free((t_pxobject*)x);
}

void mab_tilde_assist(t_mab_tilde* x, void* b, long m, long a, char* s) {
    if (m == ASSIST_INLET) {
        sprintf(s, "(signal) Audio Input");
    } else {
        sprintf(s, "(signal) Audio Output");
    }
}

void mab_tilde_dsp64(t_mab_tilde* x, t_object* dsp64, short* count, double samplerate, long maxvectorsize, long flags) {
    object_method(dsp64, gensym("dsp_add64"), x, mab_tilde_perform64, 0, NULL);
}

void mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, double** outs, long numouts, long sampleframes, long flags, void* userparam) {
    double* in = ins[0];
    double* out = outs[0];
    long n = sampleframes;

    // Pass-Through / Bypass Logik
    for (long i = 0; i < n; i++) {
        out[i] = in[i];
    }
}