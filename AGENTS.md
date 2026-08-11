# AGENTS.md – mab_tilde

Auto-loaded by opencode/Continue. Read `WORKSPACE_AGENT_PROMPT.md` for full project rules.

## Status

- **Current:** Offline-Tests T1–T7 ✅ (23 TorchScript-Modelle, 19 C++-Tests, CPU+GPU, kein Crash). Phase 6 implementiert (mcs.mab~ Batched Multichannel). Bug 1+2 gefixt. Offen: Max-Runtime-Test 6.4, Max-Runtime-V1–V6, FR2+FR3.
  - Phase 3: Method-aware processing (Header v2, latent inlets/outlets, `block_accumulator`, `infer_method` dispatch).
  - Phase 4: `mab.info` model inspector.
  - Phase 4.5: ASIO XRun prevention (`BELOW_NORMAL_PRIORITY_CLASS` + core affinity).
  - Phase 4.6: nn_tilde parity P1–P6.
  - Phase 5: mc.mab~ Multichannel — Header v3 (`channel_map`), 1-in-1-out MC-IO, `Z_MC_INLETS`-Flag, `chans`-Attribut, Max-verifiziert (5.8 ✅).
  - Phase 6: mcs.mab~ Batched Multichannel — `mcs_batches`-Inlets/-Outlets, batch-major SHM `[B×ci×bs]` (C++ `b*ci+c`), batched `infer_method` `(B,ci,bs)`, Arg-Order `[model method n_batches bufsize gpu cores]` (6.4 Max-Test offen).
  - Bug 1: NaN/Inf-Guard + safety_clip in `infer_method()` (crashte Max bei RAVE-Modellen). ✅
  - Bug 2: Deploy-Skript + venv-Junction + MAB_PROJECT_DIR (Worker startete nicht, GPU nicht verfügbar). ✅
  - FR1: `timeBeginPeriod(1)` + `SetThreadPriority(LOWEST)` (ASIO XRun-Prävention). ✅
  - CUDA: torch 2.12.0.dev+cu128 installiert (Python 3.14 Nightly), RTX 3060 6 GB.
  - Test-Suite: T1–T7 fertig (Modell-Laden, mab.info, Inferenz-Dispatch, Audio-Qualität, Edge-Cases, ctest-Integration, Benchmark-Report).

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
- Build: `cmake --preset debug && cmake --build --preset debug` → `build/Debug/mab~.mxe64`.
- **Deploy:** NUR ueber `deploy.ps1` (oder VSCode-Task `Deploy to Max 9`) — kopiert `.mxe64` **UND** `inference_worker.py` nach `%USERPROFILE%\Documents\Max 9\Packages\mab_tilde\`. Nach Deploy Max neu starten. Bug 2: ohne `inference_worker.py` crasht der Worker wg. Arg-Mismatch.
- MCP: `mab_mcp_server.py`; registriert in `opencode.json` unter `mcp.mab-rave-assistant` (NICHT `.mcp.json` – das ist nur für VS Code); tools: `index_project_code`, `query_code_rag`, `query_code_wiki`, `get_rag_chunk`, `inspect_rave_model` (im Chat mit Server-Präfix `mab-rave-assistant_*`).
- Manuelles Wissen: `doc/projektwissen.md` (~200 Z., direkt lesen).
- Auto-generiertes Wissen: `code_wiki.md` (NUR via MCP abfragen, NIE direkt lesen).
- Reference: `C:\Users\marku\Documents\GitHub\thirdParty\nn_tilde`.

## Global rules

- `~/.config/opencode/rules/no-auto-commit.md`: no git commits/pushes/PRs without explicit user request.