// worker_launch.cpp -- Portable launcher for inference_worker.py
//
// The Python/venv path and the working directory are never hardcoded: they are
// derived from the location of this module (the external DLL). Works for
// Dev-Builds (build/Debug/) and Max-Package installations (externals/ +
// support/).

#include "worker_launch.h"

#include <cstdio>
#include <cstring>
#include <string>

namespace {

// Steigt vom Modul-Verzeichnis auf, bis ein Ordner mit inference_worker.py
// gefunden ist (das ist das Projekt-/Package-Root). Geprüft werden pro Ebene
// sowohl der Ordner selbst (Dev: Repo-Root) als auch `support\` (Max-Package:
// externals liegen in externals/, Support-Dateien in support/).
bool find_worker_dir(wchar_t* out, size_t out_size) {
    HMODULE hMod = nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                       GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCWSTR)(LPVOID)&find_worker_dir, &hMod);
    if (!hMod) return false;

    wchar_t dllPath[MAX_PATH];
    if (GetModuleFileNameW(hMod, dllPath, MAX_PATH) == 0) return false;
    wchar_t* slash = wcsrchr(dllPath, L'\\');
    if (slash) *slash = L'\0';

    static const wchar_t* subdirs[] = { L"", L"support" };
    wchar_t probe[MAX_PATH];
    while (true) {
        for (size_t i = 0; i < sizeof(subdirs) / sizeof(subdirs[0]); i++) {
            if (subdirs[i][0]) {
                swprintf_s(probe, MAX_PATH, L"%ls\\%ls\\inference_worker.py",
                           dllPath, subdirs[i]);
            } else {
                swprintf_s(probe, MAX_PATH, L"%ls\\inference_worker.py", dllPath);
            }
            if (GetFileAttributesW(probe) != INVALID_FILE_ATTRIBUTES) {
                if (subdirs[i][0]) {
                    swprintf_s(out, out_size, L"%ls\\%ls", dllPath, subdirs[i]);
                } else {
                    wcsncpy_s(out, out_size, dllPath, _TRUNCATE);
                }
                return true;
            }
        }
        wchar_t* last = wcsrchr(dllPath, L'\\');
        if (!last) break;          // Root erreicht (z.B. "C:")
        *last = L'\0';
    }
    return false;
}

} // namespace

bool worker_parse_info_block(const char* text, WorkerModelInfo* info) {
    ZeroMemory(info, sizeof(*info));

    const char* begin = strstr(text, "MAB_INFO_BEGIN");
    const char* end = strstr(text, "MAB_INFO_END");
    if (!begin || !end || end <= begin) return false;

    const char* line = begin + strlen("MAB_INFO_BEGIN");
    while (line < end) {
        const char* nl = strchr(line, '\n');
        size_t len = nl ? (size_t)(nl - line) : (size_t)(end - line);
        if (len > 0) {
            std::string ln(line, len);
            if (!ln.empty() && ln.back() == '\r') ln.pop_back();
            size_t colon = ln.find(": ");
            if (colon != std::string::npos) {
                std::string key = ln.substr(0, colon);
                std::string val = ln.substr(colon + 2);
                if (key == "error") {
                    snprintf(info->last_error, sizeof(info->last_error), "%s",
                             val.c_str());
                    info->has_info = 0;
                    return true;
                } else if (key == "model_type") {
                    snprintf(info->model_type, sizeof(info->model_type), "%s",
                             val.c_str());
                } else if (key == "methods") {
                    snprintf(info->methods, sizeof(info->methods), "%s",
                             val.c_str());
                } else if (key == "attributes") {
                    snprintf(info->attributes, sizeof(info->attributes), "%s",
                             val.c_str());
                } else if (key == "block_size") {
                    info->block_size = atol(val.c_str());
                } else if (key == "channels_in") {
                    info->channels_in = atol(val.c_str());
                } else if (key == "channels_out") {
                    info->channels_out = atol(val.c_str());
                } else if (key == "latent_size") {
                    info->latent_size = atol(val.c_str());
                } else if (key.size() > 6 &&
                           key.compare(0, 6, "param ") == 0 &&
                           info->param_count < 8) {
                    // line: "param <method>: ci in_ratio co out_ratio"
                    std::string method = key.substr(6);
                    if (method.size() < 64) {
                        long v[4] = { 0, 0, 0, 0 };
                        if (sscanf(val.c_str(), "%ld %ld %ld %ld",
                                   &v[0], &v[1], &v[2], &v[3]) == 4) {
                            snprintf(info->param_methods[info->param_count],
                                     sizeof(info->param_methods[0]), "%s",
                                     method.c_str());
                            for (int i = 0; i < 4; i++)
                                info->param_values[info->param_count][i] = v[i];
                            info->param_count++;
                        }
                    }
                }
            }
        }
        if (!nl) break;
        line = nl + 1;
    }
    info->has_info = 1;
    return true;
}

bool worker_resolve_project_dir(wchar_t* out, size_t out_size) {
    wchar_t buf[MAX_PATH];
    DWORD len = GetEnvironmentVariableW(L"MAB_PROJECT_DIR", buf, MAX_PATH);
    if (len > 0 && len < MAX_PATH) {
        wchar_t probe[MAX_PATH];
        swprintf_s(probe, MAX_PATH, L"%ls\\inference_worker.py", buf);
        if (GetFileAttributesW(probe) != INVALID_FILE_ATTRIBUTES) {
            wcsncpy_s(out, out_size, buf, _TRUNCATE);
            return true;
        }
    }
    return find_worker_dir(out, out_size);
}

bool worker_find_venv_python(const wchar_t* project_dir, wchar_t* out, size_t out_size) {
    static const wchar_t* candidates[] = {
        L".venv\\Scripts\\python.exe",
        L"venv\\Scripts\\python.exe",
    };
    wchar_t probe[MAX_PATH];
    wchar_t dir[MAX_PATH];
    wcsncpy_s(dir, MAX_PATH, project_dir, _TRUNCATE);
    while (true) {
        for (size_t i = 0; i < sizeof(candidates) / sizeof(candidates[0]); i++) {
            swprintf_s(probe, MAX_PATH, L"%ls\\%ls", dir, candidates[i]);
            if (GetFileAttributesW(probe) != INVALID_FILE_ATTRIBUTES) {
                wcsncpy_s(out, out_size, probe, _TRUNCATE);
                return true;
            }
        }
        wchar_t* last = wcsrchr(dir, L'\\');
        if (!last) break;
        *last = L'\0';
    }
    return false;
}

void worker_launch(const char* arg_string, bool capture_stdout, WorkerProcess* out) {
    ZeroMemory(out, sizeof(*out));
    out->process = nullptr;
    out->stdout_read = nullptr;

    wchar_t project_dir[MAX_PATH];
    const bool have_dir = worker_resolve_project_dir(project_dir, MAX_PATH);

    wchar_t python_exe[MAX_PATH];
    const wchar_t* python = L"python";   // Fallback: System-Python aus PATH
    if (have_dir && worker_find_venv_python(project_dir, python_exe, MAX_PATH)) {
        python = python_exe;             // .venv\Scripts\python.exe bevorzugt
    }

    // -u: unbuffered stdout/stderr, damit Ausgabe/Fehler sofort verfügbar sind.
    wchar_t cmdLine[4096];
    swprintf_s(cmdLine, L"\"%ls\" -u inference_worker.py %S", python, arg_string);

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    HANDLE hLog = INVALID_HANDLE_VALUE;
    HANDLE hNullIn = INVALID_HANDLE_VALUE;
    HANDLE hPipeWrite = INVALID_HANDLE_VALUE;
    HANDLE hPipeRead = INVALID_HANDLE_VALUE;

    SECURITY_ATTRIBUTES sa;
    ZeroMemory(&sa, sizeof(sa));
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    if (capture_stdout) {
        // Anonymous pipe: child writes to hPipeWrite, parent reads hPipeRead.
        if (CreatePipe(&hPipeRead, &hPipeWrite, &sa, 0)) {
            SetHandleInformation(hPipeRead, HANDLE_FLAG_INHERIT, 0);
        } else {
            hPipeRead = INVALID_HANDLE_VALUE;
            hPipeWrite = INVALID_HANDLE_VALUE;
        }
    }

    if (have_dir) {
        wchar_t log_path[MAX_PATH];
        swprintf_s(log_path, MAX_PATH, L"%ls\\mab_worker.log", project_dir);
        hLog = CreateFileW(log_path, FILE_APPEND_DATA,
                           FILE_SHARE_READ | FILE_SHARE_WRITE,
                           NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (hLog != INVALID_HANDLE_VALUE) {
            SetHandleInformation(hLog, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT);
            hNullIn = CreateFileW(L"NUL", GENERIC_READ,
                                  FILE_SHARE_READ | FILE_SHARE_WRITE,
                                  NULL, OPEN_EXISTING, 0, NULL);
            if (hNullIn != INVALID_HANDLE_VALUE) {
                SetHandleInformation(hNullIn, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT);
            }
            si.dwFlags |= STARTF_USESTDHANDLES;
            si.hStdInput = hNullIn;
            si.hStdOutput = capture_stdout && hPipeWrite != INVALID_HANDLE_VALUE
                                ? hPipeWrite : hLog;
            si.hStdError = hLog;
        }
    }

    // lpCurrentDirectory explizit auf das Projektverzeichnis setzen, damit der
    // Worker inference_worker.py und relative Modellpfade korrekt auflöst.
    if (!CreateProcessW(NULL, cmdLine, NULL, NULL, TRUE, CREATE_NO_WINDOW,
                        NULL, have_dir ? project_dir : NULL, &si, &pi)) {
        if (hLog != INVALID_HANDLE_VALUE) CloseHandle(hLog);
        if (hNullIn != INVALID_HANDLE_VALUE) CloseHandle(hNullIn);
        if (hPipeRead != INVALID_HANDLE_VALUE) CloseHandle(hPipeRead);
        if (hPipeWrite != INVALID_HANDLE_VALUE) CloseHandle(hPipeWrite);
        return;
    }

    // ------------------------------------------------------------------
    // Echtzeit-Schutz (Grund für dieses Projekt): Der Worker darf den
    // Audio-/ASIO-Thread von Max nie verhungern lassen.
    //
    // 1) BELOW_NORMAL-Priorität: Der Audio-Thread (Max/ASIO läuft in einem
    //    RT-/HIGH-Prioritäts-Kontext) präemptet den Worker immer, egal wie
    //    viel CPU die PyTorch-Inferenz braucht.
    // 2) Affinität: Der Worker nutzt alle System-Kerne AUSSER Core 0. Damit
    //    bleibt ein Kern garantiert für den Audio-Thread frei und die
    //    PyTorch-Threads verteilen sich nicht mehr über den Kern, auf dem
    //    der ASIO-Callback läuft (die Ursache der nn_tilde-XRuns).
    //    Bei Ein-Kern-Systemen (mask == 0) wird keine Maske gesetzt.
    // ------------------------------------------------------------------
    SetPriorityClass(pi.hProcess, BELOW_NORMAL_PRIORITY_CLASS);

    DWORD_PTR sysMask = 0, procMask = 0;
    if (GetProcessAffinityMask(GetCurrentProcess(), &sysMask, &procMask) &&
        sysMask != 0) {
        DWORD_PTR workerMask = sysMask & ~(DWORD_PTR)1;  // alle außer Core 0
        if (workerMask != 0)
            SetProcessAffinityMask(pi.hProcess, workerMask);
    }

    // Parent schließt seine Kopien; der Child-Prozess besitzt eigene Handles.
    if (hLog != INVALID_HANDLE_VALUE) CloseHandle(hLog);
    if (hNullIn != INVALID_HANDLE_VALUE) CloseHandle(hNullIn);
    if (hPipeWrite != INVALID_HANDLE_VALUE) CloseHandle(hPipeWrite);

    out->process = pi.hProcess;
    out->stdout_read = capture_stdout && hPipeRead != INVALID_HANDLE_VALUE
                           ? hPipeRead : nullptr;
    CloseHandle(pi.hThread);
}
