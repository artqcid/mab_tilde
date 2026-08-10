// max_path_resolve.cpp -- Max-search-path model name resolution.
//
// Uses Max's path_absolutepath() (ext_path.h) which searches the patch's own
// folder, the Max search paths and the user's file preferences
// (Options > File Preferences) -- exactly the global, patch-independent paths
// the user asked about. Only results that exist on disk are accepted; anything
// else is left to the Python worker's own resolver (package models/ folders).

#include "max_path_resolve.h"

#include <cstdio>
#include <cstring>

#include "ext.h"
#include "ext_obex.h"
#include "ext_path.h"

#include <windows.h>

static bool path_is_file(const char* path) {
    DWORD attr = GetFileAttributesA(path);
    if (attr == INVALID_FILE_ATTRIBUTES)
        return false;
    return (attr & FILE_ATTRIBUTE_DIRECTORY) == 0;
}

static bool try_max_resolve(const char* name, char* out, size_t out_size) {
    t_symbol* resolved = NULL;
    if (path_absolutepath(&resolved, gensym(name), NULL, 0) != MAX_ERR_NONE)
        return false;
    if (!resolved || !resolved->s_name || !resolved->s_name[0])
        return false;
    // path_absolutepath() may "resolve" a bare name against the current
    // directory even when the file is missing -- verify on disk.
    if (!path_is_file(resolved->s_name))
        return false;
    strncpy(out, resolved->s_name, out_size - 1);
    out[out_size - 1] = '\0';
    return true;
}

bool mab_resolve_model_path(const char* name, char* out, size_t out_size) {
    if (!out_size)
        return false;
    out[0] = '\0';
    if (!name || !name[0])
        return false;

    // Already an absolute, existing file -- return it unchanged.
    if (path_is_file(name)) {
        strncpy(out, name, out_size - 1);
        out[out_size - 1] = '\0';
        return true;
    }

    if (try_max_resolve(name, out, out_size))
        return true;

    // No file extension -> also look for "<name>.ts" in the search paths.
    if (!strchr(name, '.')) {
        char with_ext[MAX_PATH];
        snprintf(with_ext, sizeof(with_ext), "%s.ts", name);
        if (try_max_resolve(with_ext, out, out_size))
            return true;
    }
    return false;
}
