// Test for worker_launch.{h,cpp}: project-dir resolution, venv discovery,
// MAB_INFO parsing and an end-to-end --query launch against a real model.

#include "worker_launch.h"

#include <cstdio>
#include <cstring>
#include <string>

static int g_failures = 0;

#define CHECK(cond)                                                        \
    do {                                                                   \
        if (!(cond)) {                                                     \
            printf("  FAIL at line %d: %s\n", __LINE__, #cond);            \
            g_failures++;                                                  \
        }                                                                  \
    } while (0)

static bool read_all(HANDLE pipe, std::string* out) {
    char buf[4096];
    DWORD nread = 0;
    while (ReadFile(pipe, buf, sizeof(buf), &nread, NULL) && nread > 0) {
        out->append(buf, nread);
    }
    return !out->empty();
}

int main() {
    printf("=== Worker Launch Tests ===\n");

    // Test 1: project dir resolves to a folder containing inference_worker.py
    printf("test_resolve_project_dir...\n");
    {
        wchar_t dir[MAX_PATH];
        bool ok = worker_resolve_project_dir(dir, MAX_PATH);
        CHECK(ok);
        if (ok) {
            wchar_t probe[MAX_PATH];
            swprintf_s(probe, MAX_PATH, L"%ls\\inference_worker.py", dir);
            CHECK(GetFileAttributesW(probe) != INVALID_FILE_ATTRIBUTES);
            printf("  project dir: %ls\n", dir);
        }
    }

    // Test 2: venv python is found
    printf("test_find_venv_python...\n");
    {
        wchar_t dir[MAX_PATH];
        if (worker_resolve_project_dir(dir, MAX_PATH)) {
            wchar_t py[MAX_PATH];
            bool ok = worker_find_venv_python(dir, py, MAX_PATH);
            CHECK(ok);
            if (ok) {
                CHECK(GetFileAttributesW(py) != INVALID_FILE_ATTRIBUTES);
                printf("  venv python: %ls\n", py);
            }
        }
    }

    // Test 3: MAB_INFO block parsing (canned, mirrors real worker output)
    printf("test_parse_info_block...\n");
    {
        const char* text =
            "MABJSON {...}\n"
            "MAB_INFO_BEGIN\n"
            "model_path: D:\\AI-Models\\ts models\\musicnet.ts\n"
            "model_type: RAVE\n"
            "block_size: 2048\n"
            "channels_in: 16\n"
            "channels_out: 16\n"
            "latent_size: 16\n"
            "methods: decode; encode; forward; prior\n"
            "attributes: -\n"
            "param decode: 16 2048 1 1\n"
            "param encode: 1 1 16 2048\n"
            "MAB_INFO_END\n";
        WorkerModelInfo info;
        CHECK(worker_parse_info_block(text, &info));
        CHECK(info.has_info == 1);
        CHECK(strcmp(info.model_type, "RAVE") == 0);
        CHECK(info.block_size == 2048);
        CHECK(info.channels_in == 16);
        CHECK(info.channels_out == 16);
        CHECK(info.latent_size == 16);
        CHECK(strstr(info.methods, "decode") != nullptr);
        CHECK(info.param_count == 2);
        CHECK(strcmp(info.param_methods[0], "decode") == 0);
        CHECK(info.param_values[0][0] == 16 && info.param_values[0][1] == 2048);
        CHECK(info.param_values[0][2] == 1 && info.param_values[0][3] == 1);
        CHECK(strcmp(info.param_methods[1], "encode") == 0);
    }

    // Test 4: error block is detected
    printf("test_parse_error_block...\n");
    {
        const char* text =
            "MAB_INFO_BEGIN\n"
            "error: could not load model\n"
            "MAB_INFO_END\n";
        WorkerModelInfo info;
        CHECK(worker_parse_info_block(text, &info));
        CHECK(info.has_info == 0);
        CHECK(strstr(info.last_error, "could not load model") != nullptr);
    }

    // Test 5: end-to-end --query against the real model (skipped if absent)
    printf("test_launch_query_e2e...\n");
    {
        const char* model = "D:\\AI-Models\\ts models\\musicnet.ts";
        if (GetFileAttributesA(model) == INVALID_FILE_ATTRIBUTES) {
            printf("  SKIP (model not present)\n");
        } else {
            char argbuf[2048];
            snprintf(argbuf, sizeof(argbuf), "--query \"%s\"", model);
            WorkerProcess wp;
            worker_launch(argbuf, true, &wp);
            CHECK(wp.process != nullptr);
            if (wp.process) {
                // Real-Time-Schutz: Worker muss BELOW_NORMAL laufen und darf
                // Core 0 nicht benutzen (dort läuft der Audio-Thread).
                CHECK(GetPriorityClass(wp.process) == BELOW_NORMAL_PRIORITY_CLASS);
                DWORD_PTR sysMask = 0, procMask = 0;
                // Parameterreihenfolge: (hProcess, &processMask, &systemMask)
                if (GetProcessAffinityMask(wp.process, &procMask, &sysMask)) {
                    if (sysMask > 1) {   // >1 Kern -> Maske muss ohne Core 0 sein
                        CHECK((procMask & 1) == 0);
                    }
                }
                std::string text;
                if (wp.stdout_read) {
                    read_all(wp.stdout_read, &text);
                    CloseHandle(wp.stdout_read);
                }
                DWORD rc = 1;
                WaitForSingleObject(wp.process, 90000);
                GetExitCodeProcess(wp.process, &rc);
                CloseHandle(wp.process);
                CHECK(rc == 0);
                WorkerModelInfo info;
                CHECK(worker_parse_info_block(text.c_str(), &info));
                CHECK(info.has_info == 1);
                CHECK(info.latent_size == 16);
                CHECK(strstr(info.methods, "decode") != nullptr);
                CHECK(strstr(info.methods, "encode") != nullptr);
                CHECK(strstr(info.methods, "forward") != nullptr);
                CHECK(strstr(info.methods, "prior") != nullptr);
            }
        }
    }

    printf("\n%s\n", g_failures ? "TESTS FAILED" : "All tests passed!");
    return g_failures ? 1 : 0;
}
