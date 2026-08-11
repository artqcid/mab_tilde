cmake_minimum_required(VERSION 3.19)
project(mab_tilde LANGUAGES C CXX)

if(WIN32)
    # Windows: Generator dauerhaft auf VS 18 2026 (x64) pinnen. Ohne -G wählt
    # CMake sonst u.U. einen leeren/kaputten "Visual Studio 17 2022"-Ordner als
    # Default und bricht mit "could not find any instance of Visual Studio" ab.
    set(CMAKE_GENERATOR "Visual Studio 18 2026" CACHE STRING "" FORCE)
    set(CMAKE_GENERATOR_PLATFORM "x64" CACHE STRING "" FORCE)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Pfad zum Max SDK (liegt in deinem Repo unter source/min-api/max-sdk-base/c74support)
set(MAX_SDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/source/min-api/max-sdk-base/c74support")

# Wir bauen eine STATIC Bibliothek für Tests und eine MODULE Bibliothek für Max
add_library(mab_tilde_lib STATIC
    source/projects/mab_tilde/mab_tilde.cpp
    source/projects/mab_tilde/worker_launch.cpp
    source/projects/mab_tilde/max_path_resolve.cpp
)

# Native Max Include-Pfade zuweisen
target_include_directories(mab_tilde_lib PRIVATE
    ${MAX_SDK_DIR}/max-includes
    ${MAX_SDK_DIR}/msp-includes
)

# Native Max SDK Import Libraries verlinken (mit vollständigen Pfaden)
target_link_libraries(mab_tilde_lib PRIVATE
    ${MAX_SDK_DIR}/max-includes/x64/MaxAPI.lib
    ${MAX_SDK_DIR}/msp-includes/x64/MaxAudio.lib
)

if(MSVC)
    target_compile_definitions(mab_tilde_lib PRIVATE
        WIN32_LEAN_AND_MEAN
        NOMINMAX
        _CRT_SECURE_NO_WARNINGS
    )
endif()

# Build the actual Max external (MODULE library)
add_library(mab_tilde MODULE
    source/projects/mab_tilde/mab_tilde.cpp
    source/projects/mab_tilde/worker_launch.cpp
    source/projects/mab_tilde/max_path_resolve.cpp
)
target_include_directories(mab_tilde PRIVATE
    ${MAX_SDK_DIR}/max-includes
    ${MAX_SDK_DIR}/msp-includes
)
target_link_libraries(mab_tilde PRIVATE
    ${MAX_SDK_DIR}/max-includes/x64/MaxAPI.lib
    ${MAX_SDK_DIR}/msp-includes/x64/MaxAudio.lib
)

if(MSVC)
    target_compile_definitions(mab_tilde PRIVATE
        WIN32_LEAN_AND_MEAN
        NOMINMAX
        _CRT_SECURE_NO_WARNINGS
    )
    # Max-Externals unter Windows müssen die Endung .mxe64 haben und kein 'lib'-Präfix
    # Der Output-Name muss exakt dem Objektnamen entsprechen (mab~)
    set_target_properties(mab_tilde PROPERTIES
        PREFIX ""
        OUTPUT_NAME "mab~"
        SUFFIX ".mxe64"
    )
endif()

# mc.mab~ -- Multichannel-Variante von mab~ (Phase 5).
# Wird aus derselben mab_tilde.cpp kompiliert wie mab~, aber mit
# MC_MAB_TILDE_MODULE, sodass ext_main nur die mc.mab~-Klasse registriert.
add_library(mc_mab_tilde MODULE
    source/projects/mab_tilde/mab_tilde.cpp
    source/projects/mab_tilde/worker_launch.cpp
    source/projects/mab_tilde/max_path_resolve.cpp
)
target_include_directories(mc_mab_tilde PRIVATE
    ${MAX_SDK_DIR}/max-includes
    ${MAX_SDK_DIR}/msp-includes
)
target_link_libraries(mc_mab_tilde PRIVATE
    ${MAX_SDK_DIR}/max-includes/x64/MaxAPI.lib
    ${MAX_SDK_DIR}/msp-includes/x64/MaxAudio.lib
)
if(MSVC)
    target_compile_definitions(mc_mab_tilde PRIVATE
        WIN32_LEAN_AND_MEAN
        NOMINMAX
        _CRT_SECURE_NO_WARNINGS
        MC_MAB_TILDE_MODULE
    )
    set_target_properties(mc_mab_tilde PROPERTIES
        PREFIX ""
        OUTPUT_NAME "mc.mab~"
        SUFFIX ".mxe64"
    )
endif()

# mcs.mab~ -- Batched-Multichannel-Variante von mab~ (Phase 6).
# Wird aus derselben mab_tilde.cpp kompiliert wie mab~/mc.mab~, aber mit
# MCS_MAB_TILDE_MODULE, sodass ext_main nur die mcs.mab~-Klasse registriert.
add_library(mcs_mab_tilde MODULE
    source/projects/mab_tilde/mab_tilde.cpp
    source/projects/mab_tilde/worker_launch.cpp
    source/projects/mab_tilde/max_path_resolve.cpp
)
target_include_directories(mcs_mab_tilde PRIVATE
    ${MAX_SDK_DIR}/max-includes
    ${MAX_SDK_DIR}/msp-includes
)
target_link_libraries(mcs_mab_tilde PRIVATE
    ${MAX_SDK_DIR}/max-includes/x64/MaxAPI.lib
    ${MAX_SDK_DIR}/msp-includes/x64/MaxAudio.lib
)
if(MSVC)
    target_compile_definitions(mcs_mab_tilde PRIVATE
        WIN32_LEAN_AND_MEAN
        NOMINMAX
        _CRT_SECURE_NO_WARNINGS
        MCS_MAB_TILDE_MODULE
    )
    set_target_properties(mcs_mab_tilde PROPERTIES
        PREFIX ""
        OUTPUT_NAME "mcs.mab~"
        SUFFIX ".mxe64"
    )
endif()

# mab.info -- prozessisolierter Modell-Inspektor (Phase 4)
add_library(mab_info MODULE
    source/projects/mab_tilde/mab_info.cpp
    source/projects/mab_tilde/worker_launch.cpp
    source/projects/mab_tilde/max_path_resolve.cpp
)
target_include_directories(mab_info PRIVATE
    ${MAX_SDK_DIR}/max-includes
    ${MAX_SDK_DIR}/msp-includes
)
target_link_libraries(mab_info PRIVATE
    ${MAX_SDK_DIR}/max-includes/x64/MaxAPI.lib
    ${MAX_SDK_DIR}/msp-includes/x64/MaxAudio.lib
)
if(MSVC)
    target_compile_definitions(mab_info PRIVATE
        WIN32_LEAN_AND_MEAN
        NOMINMAX
        _CRT_SECURE_NO_WARNINGS
    )
    set_target_properties(mab_info PROPERTIES
        PREFIX ""
        OUTPUT_NAME "mab.info"
        SUFFIX ".mxe64"
    )
endif()

# ============================================================================
# Unit Tests
# ============================================================================

# Test: Shared Memory Header Structure
add_executable(test_shared_memory_header test/test_shared_memory_header.cpp)
target_compile_definitions(test_shared_memory_header PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: init_worker_thread Comprehensive Tests
# These are compile-time signature checks only — no runtime calls to mab_tilde_lib.
# Linking against mab_tilde_lib would pull in MaxAPI.lib/MaxAudio.lib which require
# the Max runtime DLLs (not available outside Max).
add_executable(test_init_worker_thread_comprehensive test/test_init_worker_thread_comprehensive.cpp)
target_compile_definitions(test_init_worker_thread_comprehensive PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: init_worker_thread (basic)
add_executable(test_init_worker_thread test/test_init_worker_thread.cpp)
target_compile_definitions(test_init_worker_thread PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: mab_tilde_new
add_executable(test_mab_tilde_new test/test_mab_tilde_new.cpp)
target_compile_definitions(test_mab_tilde_new PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: mab_tilde_free
add_executable(test_mab_tilde_free test/test_mab_tilde_free.cpp)
target_compile_definitions(test_mab_tilde_free PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: mab_tilde_dsp64
add_executable(test_mab_tilde_dsp64 test/test_mab_tilde_dsp64.cpp)
target_compile_definitions(test_mab_tilde_dsp64 PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: mab_tilde_perform64
add_executable(test_mab_tilde_perform64 test/test_mab_tilde_perform64.cpp)
target_compile_definitions(test_mab_tilde_perform64 PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: mab_tilde_assist
add_executable(test_mab_tilde_assist test/test_mab_tilde_assist.cpp)
target_compile_definitions(test_mab_tilde_assist PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: init_worker
add_executable(test_init_worker test/test_init_worker.cpp)
target_compile_definitions(test_init_worker PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: Shared Memory Header Compatibility (C++ vs Python)
add_executable(test_shared_memory_header_compatibility test/test_shared_memory_header_compatibility.cpp)
target_compile_definitions(test_shared_memory_header_compatibility PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: Message Handlers
add_executable(test_message_handlers test/test_message_handlers.cpp)
target_compile_definitions(test_message_handlers PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: Handshake Integration (C++/Python shared memory)
add_executable(test_handshake_integration test/test_handshake_integration.cpp)
target_compile_definitions(test_handshake_integration PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: Multi-Channel Memory Layout
add_executable(test_multichannel_layout test/test_multichannel_layout.cpp)
target_compile_definitions(test_multichannel_layout PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: Anything Message Handler
add_executable(test_anything_handler test/test_anything_handler.cpp)
target_compile_definitions(test_anything_handler PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: Crash Monitoring
add_executable(test_crash_monitoring test/test_crash_monitoring.cpp)
target_compile_definitions(test_crash_monitoring PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: Block Accumulator (perform64 block fill/drain math)
add_executable(test_block_accumulator test/test_block_accumulator.cpp)
target_compile_definitions(test_block_accumulator PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: mc.mab~ (Phase 5) multichannel logic (IO layout, chans, channel_map)
add_executable(test_mc_mab_tilde test/test_mc_mab_tilde.cpp)
target_compile_definitions(test_mc_mab_tilde PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: mcs.mab~ (Phase 6) batched multichannel logic (n_batches IO, batch-major
# SHM rows, multichanneloutputs/inputchanged)
add_executable(test_mcs_mab_tilde test/test_mcs_mab_tilde.cpp)
target_compile_definitions(test_mcs_mab_tilde PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# Test: Worker Launch (project-dir resolution, MAB_INFO parsing, e2e --query)
add_executable(test_worker_launch
    test/test_worker_launch.cpp
    source/projects/mab_tilde/worker_launch.cpp
)
target_include_directories(test_worker_launch PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/source/projects/mab_tilde
)
target_compile_definitions(test_worker_launch PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)

# ============================================================================
# CTest-Integration (T6)
# ============================================================================

enable_testing()

set(MAB_TEST_EXES
    test_shared_memory_header
    test_init_worker_thread_comprehensive
    test_init_worker_thread
    test_mab_tilde_new
    test_mab_tilde_free
    test_mab_tilde_dsp64
    test_mab_tilde_perform64
    test_mab_tilde_assist
    test_init_worker
    test_shared_memory_header_compatibility
    test_message_handlers
    test_handshake_integration
    test_multichannel_layout
    test_anything_handler
    test_crash_monitoring
    test_block_accumulator
    test_mc_mab_tilde
    test_mcs_mab_tilde
    test_worker_launch
)

foreach(t ${MAB_TEST_EXES})
    add_test(NAME ${t} COMMAND ${t})
    set_tests_properties(${t} PROPERTIES TIMEOUT 180)
endforeach()

# Python-Tests via VENV-Python (Fallback: python im PATH)
if(DEFINED ENV{MAB_VENV_PYTHON})
    set(MAB_PYTHON "$ENV{MAB_VENV_PYTHON}")
elseif(WIN32 AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/.venv/Scripts/python.exe")
    set(MAB_PYTHON "${CMAKE_CURRENT_SOURCE_DIR}/.venv/Scripts/python.exe")
elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/.venv/bin/python")
    set(MAB_PYTHON "${CMAKE_CURRENT_SOURCE_DIR}/.venv/bin/python")
else()
    set(MAB_PYTHON "python")
endif()
message(STATUS "MAB_PYTHON = ${MAB_PYTHON}")

set(MAB_PYTHON_TESTS
    test_method_layout
    test_query_mode
    test_attribute_passthrough
    test_python_shared_memory
    test_block_size_extraction
    test_shared_memory_v2
    test_model_loading
    test_mab_info_models
    test_infer_all_models
    test_audio_quality
    test_model_edge_cases
)

foreach(t ${MAB_PYTHON_TESTS})
    add_test(NAME ${t}
        COMMAND "${CMAKE_COMMAND}" -E env PYTHONPATH="${CMAKE_CURRENT_SOURCE_DIR}"
        "${MAB_PYTHON}" -m pytest "${CMAKE_CURRENT_SOURCE_DIR}/test/${t}.py"
        -v -p no:warnings
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(${t} PROPERTIES TIMEOUT 900)
endforeach()