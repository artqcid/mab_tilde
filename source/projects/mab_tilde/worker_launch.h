// worker_launch.h -- Portable launcher for inference_worker.py
//
// Shared by mab~, mab.info, mc.mab~ and mcs.mab~. All path resolution is
// Max-independent: the project dir is derived from the location of this
// module (the external DLL), so it works for Dev-Builds (build/Debug/) and
// Max-Package installations alike.
//
// This header is intentionally Max-agnostic (only <windows.h>) so it can be
// unit-tested without the Max SDK.

#pragma once

#include <windows.h>
#include <cstddef>

// Result of a worker launch. stdout_read is only valid when
// worker_launch(..., capture_stdout = true) was used; the caller owns it.
struct WorkerProcess {
    HANDLE process;         // child process handle (NULL on failure)
    HANDLE stdout_read;     // read end of the stdout pipe (NULL unless captured)
};

// Parsed result of a worker --query run (the MAB_INFO_BEGIN/END block).
struct WorkerModelInfo {
    long  has_info;
    char  last_error[512];
    char  model_type[64];
    char  methods[512];
    char  attributes[1024];
    long  block_size;
    long  channels_in;
    long  channels_out;
    long  latent_size;
    long  param_count;                      // number of methods with params
    char  param_methods[8][64];
    long  param_values[8][4];               // ci, in_ratio, co, out_ratio
};

// Resolve the directory that contains inference_worker.py.
// Checks MAB_PROJECT_DIR first (if it points at a valid project), then walks
// up from this module's directory; per level both the folder itself (Dev) and
// `support\` (Max-Package) are probed.
bool worker_resolve_project_dir(wchar_t* out, size_t out_size);

// Find the venv Python executable (prefers .venv\Scripts\python.exe, else
// venv\Scripts\python.exe). project_dir is the folder holding inference_worker.py.
bool worker_find_venv_python(const wchar_t* project_dir, wchar_t* out, size_t out_size);

// Parse the MAB_INFO_BEGIN ... MAB_INFO_END block from a worker's stdout.
// Returns true if the block was found and parsed (info->has_info = 1).
// On a worker "error:" line, sets info->has_info = 0 and returns true.
bool worker_parse_info_block(const char* text, WorkerModelInfo* info);

// Launch `inference_worker.py` in the resolved project dir with the given
// argument string (everything after "inference_worker.py" on the command line).
// The child runs with the project dir as its working directory.
//
// capture_stdout == false: stdout+stderr go to <project_dir>\mab_worker.log.
// capture_stdout == true : stdout is captured via an anonymous pipe (stderr
//                          still goes to the log). Read it until EOF.
void worker_launch(const char* arg_string, bool capture_stdout, WorkerProcess* out);
