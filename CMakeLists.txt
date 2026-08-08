cmake_minimum_required(VERSION 3.19)
project(mab_tilde LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Pfad zum Max SDK (liegt in deinem Repo unter source/min-api/max-sdk-base/c74support)
set(MAX_SDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/source/min-api/max-sdk-base/c74support")

# Wir bauen ein klassisches Shared Library / DLL Modul
add_library(mab_tilde MODULE source/projects/mab_tilde/mab_tilde.cpp)

# Native Max Include-Pfade zuweisen
target_include_directories(mab_tilde PRIVATE
    ${MAX_SDK_DIR}/max-includes
    ${MAX_SDK_DIR}/msp-includes
)

# Native Max SDK Import Libraries verlinken
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
    set_target_properties(mab_tilde PROPERTIES
        PREFIX ""
        SUFFIX ".mxe64"
    )
endif()