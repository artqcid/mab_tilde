# RAG/MCP/Wiki – Analyse & Verbesserungsvorschläge

_Stand: 2026-08-11 (nach Commit `e6d6233`, RAG Schema v3)_

## 1. Ist-Zustand

### 1.1 Architektur
- **MCP-Server:** `mab_mcp_server.py` (1848 Zeilen), basiert auf `fastmcp`.
- **Datenbank:** SQLite FTS5 (`mab_rag.db`), Trigramm-Tokenizer (Fallback unicode61).
- **Chunking:** strukturell (Python-AST, C++-Brace-Scanner, Markdown-Sections) statt
  fester Zeilenblöcke. Jeder Chunk hat `symbol_type`, `symbol_name`, `signature`, `docstring`.
- **Suche:** Hybride FTS5/bm25 + Re-Ranking über exakte Identifier-Treffer.
- **Wiki:** `doc/code_wiki.md` – automatisch generierter Symbolindex (584 Symbole, 41 Dateien).
- **Ausgabeformate:** `text` (vollständig), `compact` (eine Zeile/Treffer + Chunk-ID),
  `json` (maschinenlesbar). Transientes Nachladen via `get_rag_chunk(chunk_id)`.
- **Inkrementelles Indexing:** SHA-256-basiert, alte Chunks werden bei Änderungen
  komplett gelöscht und neu eingefügt.
- **16 Tests** (`test/test_rag_wiki.py`): Chunking, Suche, Wiki, Chunk-IDs, Formate – alle grün.

### 1.2 MCP-Tools (13 registriert)
| Tool | Kategorie | Qualität |
|------|-----------|----------|
| `index_project_code` | RAG | ✅ Gut |
| `query_code_rag` | RAG | ✅ Gut |
| `query_code_wiki` | RAG/Wiki | ✅ Gut |
| `get_rag_chunk` | RAG | ✅ Gut |
| `inspect_rave_model` | Modell-Analyse | ✅ Gut (refactored) |
| `validate_ipc_sync` | IPC-Validierung | ⚠️ Hardcoded Checks |
| `search_max_sdk_docs` | SDK-Doku | ⚠️ Statische Antworten |
| `check_max_sdk_headers` | SDK-Doku | ⚠️ Rein statisch |
| `validate_rave_config` | Modell-Analyse | ⚠️ Dupliziert inspect_rave_model |
| `run_cpp_tests` | Build | ⚠️ Veraltet (nutzt nicht Presets) |
| `check_shared_memory_config` | IPC | ⚠️ Rein statisch |
| `analyze_inference_worker` | Analyse | ⚠️ Rein statisch |
| `get_project_info` | Info | ⚠️ Rein statisch |
| `inspect_model_metadata` | Modell | ⚠️ Dupliziert inspect_rave_model |

## 2. Stärken

1. **Strukturelles Chunking** statt Zeilen-Blöcke: erhält Kontext von Klassen/Methoden.
2. **Python-AST** für exakte Signaturen/Docstrings/qualified names – sehr robust.
3. **Token-Effizienz:** compact/json-Formate + transientes `get_rag_chunk` vermeiden Context-Dumping.
4. **Inkrementelles Indexing** mit SHA-256 – kein Rebuild bei unveränderten Dateien.
5. **Code-Wiki** als stabiler, eingecheckter Symbolindex – prompt-cache-freundlich.
6. **Trigramm-Tokenizer** matcht Substrings wie `block_size`, `mab_tilde` – ideal für Code.
7. **Keine zusätzlichen Pakete** (nur stdlib `ast`/`sqlite3`/`re`).

## 3. Schwächen & Verbesserungsvorschläge

### R1. Statische / Hardcoded Tools bereinigen (Priorität: HOCH)

**Problem:** 7 von 13 Tools liefern statische Strings, die seit Phase 1 unverändert
sind und nicht mehr dem Code entsprechen. `search_max_sdk_docs` hat 4 hardcodierte
Antworten; `check_shared_memory_config`, `get_project_info`, `analyze_inference_worker`
und `check_max_sdk_headers` sind reine String-Konstanten. `validate_rave_config` und
`inspect_model_metadata` duplizieren `inspect_rave_model`.

**Vorschlag:**
- **Entfernen:** `validate_rave_config`, `inspect_model_metadata` (Duplikate von
  `inspect_rave_model`), `check_max_sdk_headers` (rein statisch, kein Mehrwert).
- **Ersetzen:** `get_project_info`, `check_shared_memory_config`,
  `analyze_inference_worker` durch **eine** dynamische Funktion
  `get_project_summary()`, die den RAG-Index abfragt (Dateianzahl, Symbolanzahl,
  Top-Level-Klassen) und die Live-IPC-Konstanten aus dem echten Code extrahiert.
- **`search_max_sdk_docs`** → in `query_code_rag` aufgehen lassen (SDK-Headers
  sind bereits im RAG wenn nn_tilde indiziert ist).
- **`validate_ipc_sync`** → dynamisch machen: Regex-Suche auf den echten Quelldateien
  statt Hardcoded-String-Checks. Besser: via RAG-Abfragen implementieren.
- **`run_cpp_tests`** → CMake-Presets nutzen (`cmake --build --preset debug`).

**Impact:** MCP-Tool-Liste schrumpft von 13 auf ~7, weniger Verwirrung für Agents.

### R2. C++-Chunker: Kontextverlust bei verschachtelten Blöcken (Priorität: MITTEL)

**Problem:** Der C++-Brace-Scanner (`_chunk_cpp`, Zeile 278–380) findet nur Blöcke
auf Tiefe base+1. Das heißt:
- Methoden innerhalb von `extern "C" { ... }` werden als separate Funktionen
  erkannt ✅ (Tiefe 1 → korrekt).
- Aber Methoden innerhalb einer Klasse, die selbst in einem `namespace` steckt
  (Tiefe 2), werden **nicht** individuell extrahiert – der gesamte Namespace-Block
  wird ein Chunk. Bei kleinen Projekten kein Problem, bei größeren (z.B. nn_tilde
  mit ~2000-Zeilen-Dateien) → Riesenchunks.

**Vorschlag:** Rekursives Chunking (aktuell max. 2 Ebenen) auf 3 Ebenen erweitern:
Namespace → Klasse → Methode. Aufwand: ~30 Zeilen Codeänderung in `_chunk_cpp` +
2–3 neue Tests.

### R3. Wiki-Generierung: fehlende Dependency-Graphen (Priorität: NIEDRIG)

**Problem:** Das Code-Wiki listet Symbole pro Datei mit `#include`-Abhängigkeiten,
aber keine Aufruf-/Nutzungs-Beziehungen zwischen Symbolen (Caller → Callee).

**Vorschlag:** Einfache statische Analyse: für jedes Symbol `s` prüfen, ob
`s.symbol_name` in `content` anderer Chunks vorkommt. Das ergibt eine
Referenzliste (`used_by: [datei:zeile, ...]`) im Wiki. Aufwand: ~50 Zeilen +
DB-Query. Wichtig: nur für benannte Symbole, nicht für Modul-Chunks.

### R4. FTS5-Suchqualität: Ranking-Schwächen bei kurzen Queries (Priorität: MITTEL)

**Problem:** `_build_match_expr` verwirft Tokens < 3 Zeichen (Trigram-Minimum).
Suchanfragen wie `"io"`, `"mc"`, `"sr"` liefern keine Treffer. Auch Queries mit
nur einem 2-Zeichen-Token (z.B. `"mc rebuild"`) verlieren den `"mc"`-Teil.

**Vorschlag:** Fallback-Strategie:
1. Wenn alle Tokens < 3 Zeichen → LIKE-basierte Suche auf `symbol_name`
   (PREFIX-Match, performant über bestehenden Index).
2. Tokens ≥ 2 Zeichen als `LIKE '%xx%'`-Filter auf `symbol_name`/`signature`
   zusätzlich zum FTS5-MATCH verwenden.

### R5. Inkrementelles Indexing: Chunk-IDs instabil (Priorität: NIEDRIG)

**Problem:** Bei Dateiänderung werden alle Chunks der Datei gelöscht und neu
eingefügt → neue AUTOINCREMENT-IDs. Das bricht `get_rag_chunk("mab_123")` wenn
Chunk 123 zwischenzeitlich neu indiziert wurde (andere ID). In der Praxis selten
problematisch (innerhalb einer Session stabil), aber über Sessions hinweg nicht.

**Vorschlag:** Stabiles Chunk-Hashing: `chunk_id = hash(file_path + line_start +
symbol_name)` statt AUTOINCREMENT. Erfordert Schema-Migration (v4).

### R6. `query_code_wiki` nutzt LIKE statt FTS5 (Priorität: NIEDRIG)

**Problem:** `query_wiki` (Zeile 633–653) verwendet `LOWER(symbol_name) LIKE ?`
statt die FTS5-Tabelle. Bei der aktuellen Projektgröße (~600 Symbole) irrelevant,
aber bei Skalierung (z.B. wenn nn_tilde-Quellen voll indiziert werden)
ineffizienter als FTS5.

**Vorschlag:** Zweiten FTS5-Index über `symbol_name + signature + docstring`
anlegen. Aktuell kein Handlungsbedarf.

### R7. Kein Embedding-/Semantic-Search (Priorität: NIEDRIG, optional)

**Problem:** Die Suche ist rein lexikalisch (FTS5/bm25 + Identifier-Boost).
Semantisch ähnliche Konzepte (z.B. "audio callback" → `perform64`) werden nur
gefunden, wenn die Keywords im Code vorkommen.

**Vorschlag:** Für ein Projekt dieser Größe ist lexikalische Suche ausreichend.
Bei Skalierung (>100 Dateien): lokale Embeddings (z.B. `sentence-transformers`)
+ FAISS-Index als optionaler zweiter Suchpfad. Aktuell kein Handlungsbedarf.

## 4. Priorisierte Maßnahmen

| # | Maßnahme | Prio | Aufwand | Impact |
|---|----------|------|---------|--------|
| R1 | Statische Tools bereinigen | HOCH | 2–3h | Weniger Verwirrung, sauberer MCP |
| R4 | Kurze Queries: Fallback-Suche | MITTEL | 1h | Bessere Trefferquote |
| R2 | C++-Chunker: 3 Ebenen | MITTEL | 1–2h | Bessere Granularität bei großen Dateien |
| R5 | Stabile Chunk-IDs | NIEDRIG | 2h | Session-übergreifende Referenzen |
| R3 | Dependency-Graph im Wiki | NIEDRIG | 2h | Navigationsverbesserung |
| R6 | Wiki-Suche → FTS5 | NIEDRIG | 1h | Performance bei Skalierung |
| R7 | Semantic Search | NIEDRIG | 4h+ | Nur bei >100 Dateien relevant |

## 5. Nächster Schritt

**R1 (Cleanup)** kann vom Build-Agent in einer Session umgesetzt werden:
`mab_mcp_server.py` bearbeiten, 6 Tools entfernen/ersetzen, `MCP_README.md`
aktualisieren, Tests anpassen. Kein Schema-Migration nötig.
