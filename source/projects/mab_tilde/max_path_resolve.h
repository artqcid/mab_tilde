// max_path_resolve.h -- Resolve model names through Max's search paths.
//
// Uses Max's path_absolutepath() so that bare model names are also looked up
// in the paths the user configured in Max (Options > File Preferences) and in
// the current patch's folder -- independent of the mab_tilde package.
//
// This module is Max-dependent and therefore NOT compiled into the unit tests
// (test_worker_launch builds worker_launch.cpp without the Max SDK).

#pragma once

#include <cstddef>

// Resolve a model name/path to an absolute file path on disk.
// Tries the name as given and, if it has no file extension, additionally
// "<name>.ts". Only accepts results that actually exist on disk.
// Returns true and fills `out` on success; on failure `out` is left empty.
bool mab_resolve_model_path(const char* name, char* out, size_t out_size);
