# AGENTS.md – mab_tilde

Auto-loaded by opencode/Continue. Read `WORKSPACE_AGENT_PROMPT.md` for full project rules.

## Status

- **Kein Blocker.** Alle Bugs (1–14) gefixt. `mab~`-Klasse entfernt (R1).
- **Current:** Nur noch `mc.mab~` und `mcs.mab~`. 19 C++-Tests + 289 Python-Tests ✅.
  - Phase 5: mc.mab~ Multichannel — Header v4, 1-in-1-out MC-IO, `Z_MC_INLETS`, `chans`, Max-verifiziert (5.8 ✅).
  - Phase 6: mcs.mab~ Batched Multichannel — `mcs_batches`, batch-major SHM, Max-Test offen.
  - Bug 13: thread-sicherer IO-Rebuild (`perform_active`-Guard + `dsp_free` + `dirty`). ✅
  - Bug 14: `expected_new`-Fix fuer decode/prior. ✅
  - R1: `mab~`-Klasse entfernt, nur noch `mc.mab~` / `mcs.mab~`. ✅

## Workflow (verpflichtend)

1. `doc/checklist.md` → naechsten offenen Task nehmen
2. `doc/projektwissen.md` → Struct-Layouts, Konstanten, Threading (manuell gepflegt, ~200 Zeilen)
3. **NUR `query_code_wiki("<symbol>")`** → Signatur, Datei, Zeilennummer
4. **Nur wenn Wissen fehlt:** `query_code_rag(..., format="compact")`
5. **Nur benoetigten Chunk laden:** `get_rag_chunk("mab_XXX")`
6. Im echten Code verifizieren (path + line)
7. **Nach Aenderung:** `index_project_code` → Wiki wird aktualisiert → kein doppeltes Suchen

**MCP-PFLICHT (keine Ausnahmen):**
- `doc/code_wiki.md` DARF NIEMALS per `read()` geladen werden.
- JEDER Agent mit MCP-Zugriff MUSS `query_code_wiki` / `query_code_rag` / `get_rag_chunk` benutzen.
- Projekt- und SDK-Dateien nur mit `offset`/`limit` lesen — NIE ganze Dateien.
- Was einmal per MCP gefunden wurde, wird nie wieder gesucht.

**Post-Task Sync (nach jedem abgeschlossenen Task):**
- MCP nicht aktuell, Wiki aktuell: `index_project_code` → MCP nachziehen
- MCP nicht aktuell, Wiki nicht aktuell: `index_project_code` → beides aktualisieren
- Jeder Agent MUSS nach Code-Aenderungen `index_project_code` ausfuehren
- Falls nicht moeglich (kein MCP-Zugriff): explizit zurueckmelden dass Sync aussteht

## Quick facts

- Main code: `source/projects/mab_tilde/mab_tilde.cpp`, `inference_worker.py`.
- Checklist: `doc/checklist.md` (offene Tasks).
- Build: `cmake --preset debug && cmake --build --preset debug` → `build/Debug/mc.mab~.mxe64` + `mcs.mab~.mxe64`.
- **Deploy:** NUR ueber `deploy.ps1` (oder VSCode-Task `Deploy to Max 9`) — kopiert `.mxe64` **UND** `inference_worker.py` nach `%USERPROFILE%\Documents\Max 9\Packages\mab_tilde\`. Nach Deploy Max neu starten. Bug 2: ohne `inference_worker.py` crasht der Worker wg. Arg-Mismatch.
- MCP: `mab_mcp_server.py`; registriert in `opencode.json` unter `mcp.mab-rave-assistant` (NICHT `.mcp.json` – das ist nur für VS Code); tools: `index_project_code`, `query_code_rag`, `query_code_wiki`, `get_rag_chunk`, `inspect_rave_model` (im Chat mit Server-Präfix `mab-rave-assistant_*`).
- Manuelles Wissen: `doc/projektwissen.md` (~200 Z., direkt lesen).
- Auto-generiertes Wissen: `code_wiki.md` (NUR via MCP abfragen, NIE direkt lesen).
- Reference: `C:\Users\marku\Documents\GitHub\thirdParty\nn_tilde`.

## Global rules

- `~/.config/opencode/rules/no-auto-commit.md`: no git commits/pushes/PRs without explicit user request.