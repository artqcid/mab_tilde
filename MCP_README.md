# MAB-RAVE MCP Server

Ein MCP (Model Context Protocol) Server für die Entwicklung und Validierung des `mab~` Max/MSP Externals.

## Installation

```bash
pip install -r requirements.txt
```

## Verwendung

### Manueller Start

```bash
python mab_mcp_server.py
```

### Über VS Code MCP Integration

1. Öffnen Sie die Einstellungen in VS Code
2. Fügen Sie die MCP-Konfiguration in `.mcp.json` hinzu
3. Starten Sie den MCP-Server über die Command Palette

## Verfügbare Tools

### `check_max_sdk_headers()`
Durchsucht das Projekt nach typischen Max/MSP API Headern und prüft die Einbindung.

### `validate_rave_config(model_path: str)`
Überprüft ein RAVE ONNX/Torch-Modell auf Kompatibilität mit dem C++ Worker.

**Parameter:**
- `model_path`: Pfad zur ONNX- oder TorchScript-Modelldatei

### `run_cpp_tests()`
Führt lokale Tests oder den Build-Prozess für das mab~ External aus.

### `check_shared_memory_config()`
Prüft die Shared Memory-Konfiguration zwischen C++ und Python.

### `analyze_inference_worker()`
Analysiert den inference_worker.py und gibt Strukturinformationen zurück.

### `get_project_info()`
Gibt allgemeine Informationen über das mab~ Projekt zurück.

### `inspect_model_metadata(model_path: str)` ⭐ NEU
Lädt ein ONNX- oder TorchScript-Modell (RAVE) und extrahiert automatisch
die Tensor-Shapes (Input/Output), die Hop-Size und die Sampling-Rate.

**Parameter:**
- `model_path`: Pfad zur ONNX- oder TorchScript-Modelldatei

**Returns:**
- Vollständige Modellmetadaten für die C++ Integration

### `search_max_sdk_docs(query: str)` ⭐ NEU
Durchsucht lokale Markdown-Notizen oder Header-Dateien des Max SDK
nach Begriffen wie `t_pxobject`, `dsp_setup`, `class_addmethod` oder `InterlockedExchange`.

**Parameter:**
- `query`: Suchbegriff für die Dokumentation

**Returns:**
- Fundene Informationen und Code-Beispiele

### `validate_ipc_sync()` ⭐ NEU
Analysiert statisch den C++ Code (`mab_tilde.cpp`) und das Python-Worker-Skript,
um sicherzustellen, dass die Shared-Memory-Magie (`0x4D414254` / `'MABT'`) und
die Ringbuffer-Indizes (`head`/`tail`) synchron implementiert sind.

**Returns:**
- IPC-Synchronisations-Report mit Problemen und Warnungen

## SQLite-RAG-Tools (v3.1) & Code-Wiki

Die RAG-Tools erlauben es lokalen/Cloud-Coding-Modellen, exakten Projektcode
(`mab~` C++ External & `inference_worker.py`) abzufragen – ohne das Modell zu
trainieren. Basis ist eine SQLite-FTS5-Volltextdatenbank (`mab_rag.db`) mit
**Trigramm-Tokenizer**: Der matcht auch Identifikatoren wie `mab_tilde`,
`block_size` oder `dsp_setup` als Substrings – ideal für Code-Retrieval.
Keine zusätzlichen Python-Pakete nötig (`ast`/`sqlite3`/`re` sind eingebaut).

### Strukturelles Chunking (statt Zeilenblöcken)
Der Index zerlegt Code **strukturell** in Chunks mit Symbol-Metadaten:

- **Python:** `ast` → Klassen, Funktionen, Methoden (qualified names) mit
  Signaturen und Docstrings; Importe bleiben im Modul-Chunk.
- **C++:** brace-basierter Scanner → Funktionen, Klassen (inkl. Methoden),
  Namespaces/`extern "C"`; `#include`s bleiben im Modul-Chunk.
- **Markdown:** Chunking nach Überschriften (Sections).

### `index_project_code(directory_path: str)`
Scannt das Projektverzeichnis rekursiv nach C++- (`.cpp/.h/.hpp/.cc/.cxx/.c`),
Python- (`.py`) und Markdown-Dateien (`.md`, inkl. `AGENTS.md` und
`WORKSPACE_AGENT_PROMPT.md`) und speichert die Chunks in `mab_rag.db`.
Unveränderte Dateien werden per SHA-256 übersprungen (inkrementelles
Re-Indexing); entfernte Dateien werden aufgeräumt.

**Zusätzlich** regeneriert das Tool automatisch das **Code-Wiki**
`doc/code_wiki.md` – ein stabiler, eingecheckter Symbolindex (Datei → Symbole
mit Signatur/Docstring/Zeilennummern, inkl. `#include`-Abhängigkeiten und
`## Inhaltsverzeichnis`). Das Wiki indiziert sich nicht selbst
(`code_wiki.md` ist ausgeschlossen).

Ausgeschlossene Verzeichnisse: `.git`, `build`, `.venv`, `__pycache__`,
`.pytest_cache`, `node_modules`, sowie das fremde Max-SDK/Devkit
(`max-sdk-base`, `min-api`, `min-lib`), damit der Index auf eigenem Code bleibt.

**Beispiel:** `index_project_code("C:/pfad/zu/mab_tilde")`

### `query_code_rag(query: str, top_k: int = 3)`
Hybride Suche: FTS5-MATCH mit bm25-Ranking **plus** Re-Ranking über exakte
Identifier-Treffer (Syntax-Boost). Gibt die relevantesten Chunks als
formatierten Markdown-Codeblock (Dateipfad + Zeilennummern) zurück – direkt
als Kontext für den Chat nutzbar.

**Beispiel:** `query_code_rag("shared memory handshake is_input_ready")`

### `query_code_wiki(query: str, max_results: int = 12)`
Struktursuche über den Code-Wiki-Symbolindex (Klassen, Funktionen, Methoden,
Sections) anhand von Symbolname/Signatur/Docstring. Liefert Typ + Dateipfad +
Zeilennummern – ideal für „welche Methode macht X?“. Für
Implementierungsdetails danach `query_code_rag` verwenden.

**Beispiel:** `query_code_wiki("apply_io")`

### `inspect_rave_model(model_path: str)`
Leichtgewichtige RAVE/ONNX/TorchScript-Analyse: Dateimetadaten, Ein-/Ausgangs-
Shapes, Hop-Size-Detektion, verfügbare Methoden (`encode`/`decode`/`forward`)
und eine Empfehlung für `block_size`/`num_channels` des mab~-Ringbuffers.
Nutzt optional `onnxruntime`/`torch`, funktioniert aber auch ohne.

### Verpflichtender Workflow für Coding-Agents
1. **Code-Wiki lesen:** `doc/code_wiki.md` einmalig pro Session als stabilen
   Kontext (prompt-cache-freundlich) einlesen – danach gezielt suchen.
2. **`query_code_wiki`** für Struktur-/Architekturfragen verwenden.
3. **`query_code_rag`** für Implementierungsdetails; Treffer **immer am echten
   Quellcode verifizieren** (Pfad + Zeilennummern).
4. **Nach Quellcode-Änderungen:** `index_project_code` erneut ausführen, damit
   Datenbank und Code-Wiki aktuell bleiben.

### RAG-Datenbank & Git
`mab_rag.db` (+ WAL/SHM) ist ein Laufzeit-Artefakt und in `.gitignore`
eingetragen. Löschen Sie die Datei, um den Index komplett neu aufzubauen:
`Remove-Item mab_rag.db*`. Das generierte `doc/code_wiki.md` wird **eingecheckt**
(kein `.gitignore`).

## Projektstruktur

```
mab_tilde/
├── source/projects/mab_tilde/mab_tilde.cpp  # Haupt-C++ Code
├── inference_worker.py                       # Python Backend
├── mab_mcp_server.py                         # MCP Server
├── requirements.txt                          # Python Abhängigkeiten
├── CMakeLists.txt                            # Build-Konfiguration
└── .mcp.json                                 # MCP Konfiguration
```

## Shared Memory Handshake-Protokoll

Siehe `check_shared_memory_config()` Tool für Details.

## Neue Tools (v2.0)

### `inspect_model_metadata(model_path)`
Vollständige Modellanalyse für RAVE-Modelle:
- ONNX Runtime Integration für detaillierte Shape-Analyse
- Automatische Hop-Size-Erkennung
- RAVE-Konformitäts-Check
- C++ Kompatibilitäts-Empfehlungen

### `search_max_sdk_docs(query)`
Intelligenter Max SDK Dokumentations-Zugriff:
- Volltextsuche in C++ Header-Dateien
- Code-Beispiele für typische Max SDK Patterns
- SPSC-Implementierungshinweise

### `validate_ipc_sync()`
Statische IPC-Validierung:
- Magic Number Konsistenz (0x4D414254)
- Ring Buffer Head/Tail Synchronisation
- Shared Memory Namenskonventionen
- Event-basierte Synchronisation

## Lizenz

Dieses Projekt ist Teil des artqcid/ai-projects Repository.