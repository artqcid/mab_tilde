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

### Über opencode (empfohlen)

Die MCP-Registrierung für opencode erfolgt im Projekt-`opencode.json` unter
dem Key `mcp` (natives opencode-Format, `type: "local"`, `command` als Array):

```json
"mcp": {
  "mab-rave-assistant": {
    "type": "local",
    "command": [
      "C:/Users/marku/Documents/GitHub/artqcid/ai-projects/mab_tilde/.venv/Scripts/python.exe",
      "-u",
      "mab_mcp_server.py"
    ],
    "cwd": "C:/Users/marku/Documents/GitHub/artqcid/ai-projects/mab_tilde",
    "environment": { "PYTHONUNBUFFERED": "1" },
    "enabled": true
  }
}
```

**Wichtig:** opencode lädt `.mcp.json` (VS-Code-/Claude-Code-Format) NICHT.
Nach einer Änderung an `opencode.json` muss opencode neu gestartet werden
(Config wird nur beim Start geladen). Status prüfen: `opencode mcp list`
→ `mab-rave-assistant ✓ connected`. Die MCP-Tools erscheinen bei allen
Agents mit Server-Präfix (`mab-rave-assistant_query_code_wiki`, ...).

### Über VS Code MCP Integration

1. Öffnen Sie die Einstellungen in VS Code
2. Fügen Sie die MCP-Konfiguration in `.mcp.json` hinzu
3. Starten Sie den MCP-Server über die Command Palette

## Verfügbare Tools (7)

### `run_cpp_tests()`
Führt den Build-Prozess für das mab~ External über `cmake --build --preset debug`
aus (siehe `CMakePresets.json`). Erfordert vorher `cmake --preset debug`.

### `get_project_summary()`
Dynamische Projektübersicht. Liest aktuelle Dateien (`mab_tilde.cpp`,
`inference_worker.py`, etc.) und den RAG-Index-Status aus. Ersetzt die früheren
statischen Tools `get_project_info`, `check_shared_memory_config` und
`analyze_inference_worker`.



### `inspect_rave_model(model_path: str)`
Leichtgewichtige RAVE/ONNX/TorchScript-Analyse: Dateimetadaten, Ein-/Ausgangs-
Shapes, Hop-Size-Detektion, verfügbare Methoden (`encode`/`decode`/`forward`)
und eine Empfehlung für `block_size`/`num_channels` des mab~-Ringbuffers.

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

### `query_code_rag(query: str, top_k: int = 3, format: str = "text")`
Hybride Suche: FTS5-MATCH mit bm25-Ranking **plus** Re-Ranking über exakte
Identifier-Treffer (Syntax-Boost). Gibt die relevantesten Chunks als
formatierten Markdown-Codeblock (Dateipfad + Zeilennummern) zurück – direkt
als Kontext für den Chat nutzbar. Jeder Treffer trägt eine stabile
Chunk-Referenz `[mab_<id>]`.

`format` steuert die Kontext-Fülle (Token-Optimierung):
- `"text"` (Standard): vollständige Code-Snippets.
- `"compact"`: eine Zeile pro Treffer (ID, Pfad, Zeilen, Symbol, Signatur) –
  Full-Content nur bei Bedarf via `get_rag_chunk(<id>)` abrufen (spart Token).
- `"json"`: maschinenlesbares JSON inkl. `chunk_id` je Treffer.

**Beispiel:** `query_code_rag("shared memory handshake", format="compact")`

### `get_rag_chunk(chunk_id: str)`
Holt den **vollständigen Inhalt eines einzelnen Chunks** transient – erst wenn
er im Reasoning im Detail gebraucht wird (Evidence-Aliasing statt
Context-Dumping). `chunk_id` im Format `mab_<id>` aus den Suchergebnissen.

**Beispiel:** `get_rag_chunk("mab_534")`

### `query_code_wiki(query: str, max_results: int = 12, format: str = "text")`
Struktursuche über den Code-Wiki-Symbolindex (Klassen, Funktionen, Methoden,
Sections) anhand von Symbolname/Signatur/Docstring. Liefert Typ + Dateipfad +
Zeilennummern – ideal für „welche Methode macht X?“. Für
Implementierungsdetails danach `query_code_rag` verwenden. `format` wie bei
`query_code_rag` (`"text"`/`"compact"`/`"json"`).

**Beispiel:** `query_code_wiki("apply_io", format="compact")`

### `inspect_rave_model(model_path: str)`
Leichtgewichtige RAVE/ONNX/TorchScript-Analyse: Dateimetadaten, Ein-/Ausgangs-
Shapes, Hop-Size-Detektion, verfügbare Methoden (`encode`/`decode`/`forward`)
und eine Empfehlung für `block_size`/`num_channels` des mab~-Ringbuffers.
Nutzt optional `onnxruntime`/`torch`, funktioniert aber auch ohne.

### Workflow für Coding-Agents (Wiki-First)
1. `doc/checklist.md` → nächsten offenen Task nehmen
2. `doc/code_wiki.md` einmalig pro Session als stabilen Kontext einlesen
3. `query_code_wiki("<symbol>")` für Strukturfragen (Signatur, Datei, Zeilennummer)
4. **Nur wenn Wiki-Wissen nicht ausreicht:** `query_code_rag(..., format="compact")`
5. **Nur benötigten Chunk laden:** `get_rag_chunk("mab_XXX")`
6. Im echten Code verifizieren (Pfad + Zeilennummern)
7. **Nach Quellcode-Änderungen:** `index_project_code` → Wiki wird aktualisiert

**Regel:** Was einmal im Wiki steht, wird nie wieder per RAG gesucht.
### Token-Effizienter RAG-Workflow
Für große Suchmengen die Kontext-Fülle reduzieren:
1. Erste Erkundung mit `format="compact"` (eine Zeile pro Treffer, inkl.
   Chunk-ID `[mab_<id>]`).
2. Nur die tatsächlich benötigten Chunks via `get_rag_chunk("mab_<id>")`
   im Detail laden (transient, statt alle Snippets einzublenden).
3. Maschinelle Weiterverarbeitung/Parsing: `format="json"` (stabile Felder
   inkl. `chunk_id`, `file_path`, `line_start`/`line_end`).

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
├── .mcp.json                                 # MCP-Konfiguration für VS Code (Claude-Code-Format)
└── opencode.json                             # opencode-Konfiguration: Agenten + MCP-Registrierung (`mab-rave-assistant`)
```

## Lizenz

Dieses Projekt ist Teil des artqcid/ai-projects Repository.
