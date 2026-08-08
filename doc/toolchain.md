# Toolchain & Build System Documentation

**File:** `doc/toolchain.md`  
**Purpose:** Dokumentation des aktuellen Build-Systems, der verwendeten Tools und der Build-Konfiguration für das `mab_tilde` Projekt.

---

## 1. Überblick

Das `mab_tilde` Projekt verwendet ein **reines natives Max SDK Build-System** ohne das min-devkit Framework. Der Build erfolgt über CMake mit dem Visual Studio 2026 Generator (MSVC 19.51).

---

## 2. Build Tools

| Tool | Version | Zweck |
|------|---------|-------|
| **Visual Studio** | 18 (2026) Community | C++ Compiler (MSVC 19.51.36252.0) |
| **CMake** | 3.19+ | Build-System-Generator |
| **Windows SDK** | 10.0.26100.0 | Windows API Headers |
| **Python** | 3.9+ | PyTorch Inference Backend |

### Installierte VS 2026 Komponenten
- MSVC v144 (VS 2026 C++ x64/x86 Build Tools)
- Windows 10/11 SDK (10.0.26100.0)
- CMake 3.28+ (über VS integriert)

---

## 3. Build-Architektur

### 3.1 Root CMakeLists.txt
Die Haupt-CMakeLists.txt im Projekt-Root verwendet `add_library(mab_tilde MODULE ...)`:

```cmake
cmake_minimum_required(VERSION 3.19)
project(mab_tilde LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(MAX_SDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/source/min-api/max-sdk-base/c74support")

add_library(mab_tilde MODULE source/projects/mab_tilde/mab_tilde.cpp)

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
    set_target_properties(mab_tilde PROPERTIES
        PREFIX ""
        SUFFIX ".mxe64"
    )
endif()
```

### 3.2 SDK-Struktur
```
source/min-api/max-sdk-base/c74support/
├── max-includes/          # Max Runtime Headers (ext.h, ext_obex.h, etc.)
│   └── x64/
│       └── MaxAPI.lib     # Import Library für Max Runtime Symbole
├── msp-includes/          # Max DSP Headers (z_dsp.h, etc.)
│   └── x64/
│       └── MaxAudio.lib   # Import Library für DSP Symbole
└── jit-includes/          # Jitter Headers (optional)
    └── x64/
        └── jitlib.lib     # Import Library für Jitter Symbole
```

### 3.3 Output
- **Datei**: `mab_tilde.mxe64`
- **Ort**: `build/Debug/mab_tilde.mxe64` (Debug) oder `build/Release/mab_tilde.mxe64` (Release)
- **Format**: Windows DLL mit `.mxe64` Extension (Max External)

---

## 4. Build-Befehle

### Clean Build (empfohlen)
```powershell
# Im Projekt-Root-Verzeichnis ausführen:
Remove-Item -Recurse -Force build
cmake -B build -G "Visual Studio 18 2026" -A x64
cmake --build build --config Debug
```

### Schnell-Build (nach Konfigurierung)
```powershell
cmake --build build --config Debug
```

### Release Build
```powershell
cmake -B build -G "Visual Studio 18 2026" -A x64
cmake --build build --config Release
```

---

## 5. Wichtige Max SDK API-Namen (Native)

| Falscher Name | Korrekter Name | Verwendung |
|---------------|----------------|------------|
| `getsym(...)` | `gensym("...")` | Symbol-Erstellung |
| `atom_getint(...)` | `atom_getlong(...)` | Atom als 64-bit Integer lesen |
| `atom_type(...)` | `atom_gettype(...)` | Atom-Typ abfragen |
| `class_dspinit64(...)` | `class_dspinit(c)` | DSP-Initialisierung |
| `CLASS_NOFLOAT` | `0L` | class_new Flags |
| `bind64` | `gensym("dsp_add64")` | Perform-Methoden-Registrierung |
| `int main()` | `void ext_main()` | Max External Einstiegspunkt |

---

## 6. Bekannte Probleme & Lösungen

### 6.1 LNK1104: c74support.lib nicht gefunden
**Problem**: Das min-devkit Framework versucht, `c74support.lib` zu verlinken, die nicht existiert.  
**Lösung**: Verwende das reine native Build-System (siehe Abschnitt 3.1). Verlinke stattdessen `MaxAPI.lib` und `MaxAudio.lib` direkt.

### 6.2 Unknown CMake command "min_project"
**Problem**: Das `min_project()` Makro existiert nicht in der aktuellen min-api Version.  
**Lösung**: Verwende kein min-devkit Framework. Nutze `add_library()` direkt in der Root CMakeLists.txt.

### 6.3 Compiler-Fehler: CLASS_NOFLOAT nicht definiert
**Problem**: `CLASS_NOFLOAT` ist kein gültiger Max SDK Konstant.  
**Lösung**: Verwende `0L` als Flags-Parameter in `class_new()`.

### 6.4 std::wstring Konvertierungsfehler
**Problem**: `std::wstring(atom_getsym(argv)->s_name)` versucht, ein `char*` in `std::wstring` zu konvertieren.  
**Lösung**: Verwende `t_symbol*` direkt oder konvertiere explizit mit `std::string(atom_getsym(argv)->s_name)`.

### 6.5 MSVC 2026 Generator nicht gefunden
**Problem**: `cmake -G "Visual Studio 17 2022"` schlägt fehl, weil VS 2026 (Version 18) installiert ist.  
**Lösung**: Verwende `-G "Visual Studio 18 2026"`.

### 6.6 Crash beim Objekt-Instanziieren (std::atomic in C-Struct)
**Problem**: `std::atomic<bool>` in einem C-Struct, dessen Speicher über `object_alloc()` (malloc) reserviert wird. C++ Konstruktoren werden nie aufgerufen → Undefined Behavior → Crash.  
**Lösung**: Verwende `long` Variablen statt `std::atomic<bool>`. Auf x86/x64 sind einfache `long`-Lese/Schreib-Operationen atomar genug für Flags.

### 6.7 Falscher Einstiegspunkt (main statt ext_main)
**Problem**: Max erwartet `ext_main` als Einstiegspunkt für `.mxe64` Externals, nicht `int main()`.  
**Lösung**: Verwende `extern "C" { C74_EXPORT void ext_main(void* r) { ... } }` als Einstiegspunkt. Der `extern "C"` Block verhindert C++ Name Mangling, `void* r` ist der Parameter, den das moderne Max SDK erwartet.

### 6.8 Makro-Neudefinition Warnungen (WIN32_LEAN_AND_MEAN, NOMINMAX)
**Problem**: Diese Defines werden sowohl in der CMakeLists.txt als auch in mab_tilde.cpp definiert.  
**Lösung**: Entferne die Defines aus mab_tilde.cpp (sie werden über CMake-Compile-Definitions bereitgestellt). Alternativ: Verwende `#ifndef` Guards.

---

## 7. Build-Verifikation

Nach erfolgreichem Build sollte folgende Datei existieren:
```
build/Debug/mab_tilde.mxe64  (ca. 55 KB)
```

Die Datei kann direkt in den Max Packages-Ordner kopiert werden:
```
C:\Users\[Benutzer]\Documents\Max 8/Packages\mab_tilde\
```

---

*End of Toolchain Documentation*
