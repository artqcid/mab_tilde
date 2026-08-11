# Wiki-Audit: code_wiki.md Vollständigkeitsprüfung

_Datum: 2026-08-11 | Status: Analyse abgeschlossen_

## Zusammenfassung

Das Code-Wiki (`doc/code_wiki.md`, 699 Zeilen, ~826 Roh-Zeilen) ist ein automatisch generierter Symbolindex
(41 Dateien, 783 Chunks, 502 Symbole). Die strukturelle Qualität ist gut, aber es gibt systematische Lücken
durch Chunker-Limitationen und fehlendes manuelles Projektwissen.

---

## 1. Gefundene Lücken (nach Schweregrad)

### 🔴 KRITISCH: Zentrale Datenstrukturen fehlen

| Symbol | Datei | Zeilen | Fehlerursache |
|--------|-------|--------|---------------|
| `_mab_tilde` / `t_mab_tilde` | mab_tilde.cpp | 64-112 | Chunker erkennt `typedef struct` nicht als Klasse (nur Test-Mocks) |
| `t_mab_info` | mab_info.cpp | 29-51 | Gleicher Fehler: `typedef struct _mab_info` |
| `init_worker` | mab_tilde.cpp | 578-660 | `extern "C"` im Funktionskopf schluckt die Funktionserkennung |

**Impact:** Ohne `_mab_tilde`-Struktur weiß ein Agent nicht:
- Welche Felder das Objekt hat (`is_ready`, `is_bypass`, `python_process`, `header`, `p_input`, etc.)
- Wie der Zustandsautomat funktioniert (bypass → init → ready)
- Wie die Thread-Synchronisation aufgebaut ist (`init_thread`, `io_qelem`, `crash_clock`)

### 🟡 MITTEL: Präprozessor-Konstanten fehlen

Der strukturelle Chunker ignoriert `#define`-Anweisungen vollständig:

| Konstante | Wert | Datei | Bedeutung |
|-----------|------|-------|-----------|
| `MAX_CHANNELS` | 16 | mab_tilde.cpp:18 | Maximale Kanalanzahl |
| `MAX_BLOCK_SIZE` | 4096 | mab_tilde.cpp:19 | Maximale Blockgröße |
| `CONTROL_RING_SIZE` | 256 | mab_tilde.cpp:20 | Ringpuffer-Größe |
| `CONTROL_MSG_SIZE` | 256 | mab_tilde.cpp:21 | Nachrichten-Größe |
| `MAB_INFO_DICT_JSON` | 16384 | mab_info.cpp:25 | Dict-JSON-Puffer |
| `MAGIC_NUMBER` | 0x4D414254 | inference_worker.py:50 | Header-Magic |
| `MODEL_API_ROOT` | URL | inference_worker.py:55 | IRCAM API |
| `FILE_MAP_ALL_ACCESS` | 0x00F001F | inference_worker.py:44 | WinAPI |
| `PAGE_READWRITE` | 0x04 | inference_worker.py:45 | WinAPI |
| `CONTROL_RING_SIZE` | 256 | inference_worker.py:92 | Python-seitig |

### 🟢 NIEDRIG: Build- und Config-Dateien nicht indiziert

| Datei | Typ | Enthalten in Wiki? |
|-------|-----|-------------------|
| `CMakeLists.txt` | Build-Definition | ❌ (kein `.txt` in Extensions) |
| `CMakePresets.json` | CMake-Konfiguration | ❌ (kein `.json` in Extensions) |
| `.mcp.json` | MCP-Konfiguration | ❌ |
| `opencode.json` | Agent-Konfiguration | ❌ |
| `.ragignore` | Index-Filter | ❌ |
| `requirements.txt` | Python-Deps | ❌ |
| `setup_env.bat` | Setup-Skript | ❌ (kein `.bat` in Extensions) |
| `.gitignore` | Git-Ignore | ❌ |
| `help/mab~.maxhelp` | Max-Hilfe | ❌ (kein `.maxhelp` in Extensions) |
| `help/mab.info.maxhelp` | Max-Hilfe | ❌ |
| `docs/mab~.maxref.xml` | Referenz | ❌ (kein `.xml` in Extensions) |
| `docs/mab.info.maxref.xml` | Referenz | ❌ |

**Impact:** Build-Agenten sehen nicht auf Anhieb, welche Ziele existieren (`mab_tilde`, `mab_tilde_lib`, `mab_info`, 17 Tests).

### 🔵 WIKI-NOISE: Test-Dateien dominieren

Von 502 Symbolen stammen ~300 (60%) aus Test-Dateien. Das ist für Entwicklungs-Workflows
wertvoll (Testabdeckung sichtbar), aber es verdünnt den Signal/Rausch-Anteil für
Feature-Entwicklung.

---

## 2. Wurzelursachen im Chunker (`mab_mcp_server.py`)

### 2.1 `_cpp_def_kind` – `extern "C"` schluckt Funktionen (Zeile 346-347)

```python
if re.match(r'extern\s*"C"', h):
    return ("extern", None)
```

`extern "C" void init_worker(...)` matched den `extern`-Pattern VOR dem Funktions-Pattern.
→ Funktion wird als `extern`-Block klassifiziert, ihr Inhalt als Modul-Chunk ohne Namen.

**Fix:** Prüfe zuerst auf Funktionsmuster, oder erkenne `extern "C"` + Funktionssignatur
kombiniert als `("function", name)`.

### 2.2 `_cpp_def_kind` – `typedef struct X { ... } Y;` (Zeile 348-355)

Der Regex `(?:class|struct|union)\s+([A-Za-z_]\w*)` matched `struct _mab_tilde` und
extrahiert `_mab_tilde`. Das ist technisch korrekt, ABER:

Das Problem liegt woanders: Der Chunker erkennt den Block, klassifiziert ihn als `class`,
und `_chunk_cpp_class` wird aufgerufen. Da die Struktur nur Datenmember hat (keine
Methoden), gibt es keine Sub-Blöcke → `_chunk_cpp_class` sollte einen einzigen Chunk
emittieren. **Warum erscheint er nicht im Wiki?**

Mögliche Ursachen (muss am echten Chunker debugged werden):
1. Der `typedef`-Präfix stört die Header-Rekonstruktion
2. Der Block wird fälschlich als Einzeiler klassifiziert
3. Ein anderer Filter verwirft den Chunk

### 2.3 Fehlende `#define`-Erfassung

`#define`-Zeilen beginnen mit `#` und werden von `_cpp_def_kind` explizit ignoriert:
```python
if not h or h.startswith("#") or h.endswith(";"):
    return ("block", None)
```

**Fix:** Konstanten-Chunks aus `#define`-Zeilen generieren, oder ein manuelles
Konstanten-Referenz im Wiki pflegen.

---

## 3. Empfohlenes Wissen für Agenten (Wiki-First)

Folgendes Wissen sollten Agents direkt aus dem Wiki beziehen können,
ohne RAG-Suche oder Source-Read:

| Wissenskategorie | Aktuell im Wiki? | Empfehlung |
|-----------------|------------------|------------|
| `_mab_tilde` Struct-Layout | ❌ | Manuell hinzufügen (Chunker-Fix benötigt) |
| Threading-Modell (welche Funktion auf welchem Thread) | ❌ | Manuelle Sektion |
| Message-Flow (Max→C++→Python) | Teilweise (WORKSPACE_AGENT_PROMPT.md) | Kompakt im Wiki |
| Konstanten-Referenz | ❌ | Manuelle Sektion oder Chunker-Fix |
| Build-Targets und ihre Beziehung | ❌ | Manuelle Sektion |
| Datei-Zweck-Übersicht (1-Zeiler pro Datei) | ❌ | Manuelle Sektion |
| Shared Memory Layout (Header v2) | ✅ (als Code) | Gut genug |
| Max-SDK-API-Referenz | ✅ (toolchain.md) | Gut genug |
| nn_tilde-Paritäts-Delta | ✅ (nn_tilde_parity.md) | Gut genug |

---

## 4. Aktionsplan

### Schritt 1: Chunker-Fixes (Build-Agent – Source-Code-Änderungen)

#### 1a. `extern "C"` Funktionserkennung in `_cpp_def_kind`
**Datei:** `mab_mcp_server.py:335-359`

Vor dem `extern "C"`-Match (Zeile 346) prüfen, ob die Zeile auch eine
Funktionssignatur enthält:
```python
# Prüfe: "extern \"C\" return_type func_name(args...)"
m = re.match(r'extern\s*"C"\s+.*?([A-Za-z_]\w*)\s*\(', h)
if m and m.group(1) not in _CPP_CTRL:
    return ("function", m.group(1))
if re.match(r'extern\s*"C"', h):
    return ("extern", None)
```

#### 1b. `typedef struct` Debugging
- `_chunk_cpp_class` aufrufen mit Logging, ob der Block tatsächlich erreicht wird
- Header-String prüfen: ist es `typedef struct _mab_tilde`?
- Prüfen ob `_cpp_def_kind` tatsächlich `("class", "_mab_tilde")` zurückgibt

#### 1c. `#define`-Konstanten erfassen
In `_chunk_cpp` oder `_chunk_cpp_region` eine Vorverarbeitung einbauen,
die `#define NAME VALUE`-Zeilen als `("constant", name)`-Chunks emittiert.

### Schritt 2: Manuelle Wiki-Erweiterung (Architect – .md-Edit)

Eine Sektion **"## Projektwissen (manuell gepflegt)"** am Anfang des Wikis
einfügen (vor dem Inhaltsverzeichnis), mit:

```
## Projektwissen (manuell)
### Zentrale Datenstrukturen
### Threading-Modell  
### Message-Flow
### Konstanten
### Build-Targets
### Datei-Zweck-Übersicht
```

Dieses Wissen wird **vor** dem autogenerierten Teil eingefügt und bei
`index_project_code` nicht überschrieben (der Generator schreibt hinter
die manuelle Sektion).

**Wichtig:** Der Generator (`generate_wiki`) überschreibt die GESAMTE Datei.
→ Entweder den Generator anpassen (Marker-Kommentar respektieren) oder das
manuelle Wissen in eine separate Datei `doc/projektwissen.md` auslagern und
per `[include]` referenzieren.

### Schritt 3: Re-Index und Verifikation

1. Chunker-Fixes einbauen
2. `index_project_code` ausführen
3. Prüfen: `_mab_tilde`, `t_mab_info`, `init_worker` erscheinen im Wiki
4. Prüfen: `#define`-Konstanten erscheinen

---

## 5. Geschätzte Token-Ersparnis

| Maßnahme | Geschätzte Token-Ersparnis pro Session |
|----------|--------------------------------------|
| `_mab_tilde` im Wiki (statt RAG-Suche + 2x Source-Read) | ~2000 Tokens |
| Threading-Modell im Wiki | ~1500 Tokens |
| Konstanten im Wiki | ~800 Tokens |
| Build-Targets im Wiki | ~500 Tokens |
| **Gesamt** | **~4800 Tokens/Session** |

---

## 6. Nächste Schritte

1. **Architect** (jetzt): Dieses Audit-Dokument finalisieren
2. **Build-Agent**: Chunker-Fixes 1a–1c implementieren  
3. **Build-Agent**: `index_project_code` ausführen
4. **Architect**: Manuelles Projektwissen ergänzen
5. **Build-Agent**: Finalen Build + Tests durchführen
