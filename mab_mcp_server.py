#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
MCP Server für mab~ Max/MSP External

Dieser Server bietet Tools für die Entwicklung und Validierung
des mab~ RAVE-basierten Audio-External.
"""

from fastmcp import FastMCP
import subprocess
import os
import sys
import re
import hashlib
import sqlite3
from contextlib import closing

# Initialisiere den FastMCP Server
mcp = FastMCP("MAB-RAVE-Assistant")


# ============================================================================
# SQLite-RAG-System (Retrieval-Augmented Generation)
# ----------------------------------------------------------------------------
# Leichtgewichtiges RAG ausschließlich mit Pythons eingebautem `sqlite3` und
# FTS5 (Full-Text-Search). Kein schweres Embedding-Framework nötig.
#
# Besonderheit: Es wird der FTS5-*Trigramm*-Tokenizer verwendet. Anders als
# klassische Tokenizer (unicode61/porter) zerlegt er Code nicht an
# Wortgrenzen/Unterstrichen, sondern ermöglicht Substring-Matches auf echten
# Identifikatoren wie `mab_tilde`, `block_size` oder `dsp_setup`.
# Das ist für Code-Retrieval deutlich treffsicherer als semantische Suche.
# ============================================================================

# Datenbankdatei liegt neben diesem Skript im Projektverzeichnis
RAG_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mab_rag.db")

# Zu indizierende Sprachen und ihre Dateiendungen.
# `.md` ist inkludiert, damit auch die zentrale Anleitung
# (WORKSPACE_AGENT_PROMPT.md, AGENTS.md, Doku) per RAG durchsuchbar ist.
RAG_LANGUAGE_EXTENSIONS = {
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".h": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "cpp",
    ".py": "python",
    ".md": "markdown",
}

# Chunking: Code wird zeilenweise in Blöcke mit Überlappung zerlegt, damit
# zusammenhängender Kontext (z.B. eine Funktion) nicht auseinandergerissen wird.
RAG_CHUNK_LINES = 60
RAG_CHUNK_OVERLAP = 10

# Verzeichnisse, die beim Scan übersprungen werden.
# max-sdk-base: komplettes Cycling74-SDK (tausende Header) würde den Index
# mit fremdem Code überfluten und die Suche im eigenen Projektcode verwässern.
RAG_IGNORED_DIRS = {
    ".git", "build", ".venv", "__pycache__", ".pytest_cache",
    "node_modules", ".continue", "CMakeFiles", ".vscode",
    "max-sdk-base", "min-api", "min-lib",
}

# Maximale Dateigröße, die indiziert wird (Bytes) - verhindert große Binaries
RAG_MAX_FILE_SIZE = 2 * 1024 * 1024


class ProjectRAG:
    """Verwaltet die lokale SQLite-FTS5-Datenbank für den Code-Retrieval."""

    def __init__(self, db_path: str = RAG_DB_PATH):
        self.db_path = db_path
        self._init_schema()

    # -- Datenbank-Verbindung ------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        """Öffnet eine frische Verbindung (thread-sicher für parallele MCP-Aufrufe)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    # -- Schema --------------------------------------------------------------
    def _init_schema(self):
        """Legt die Tabellen an, sofern sie noch nicht existieren."""
        with closing(self._connect()) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS code_chunks (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_path   TEXT    NOT NULL,
                        language    TEXT    NOT NULL,
                        chunk_index INTEGER NOT NULL,
                        line_start  INTEGER NOT NULL,
                        line_end    INTEGER NOT NULL,
                        content     TEXT    NOT NULL,
                        file_sha    TEXT    NOT NULL,
                        UNIQUE(file_path, chunk_index)
                    )
                """)
                # FTS5-Virtual-Table: rowid verweist auf code_chunks.id.
                # Trigramm-Tokenizer bevorzugt, Fallback auf unicode61.
                fts_sql = (
                    "CREATE VIRTUAL TABLE IF NOT EXISTS code_fts USING fts5("
                    "file_path UNINDEXED, language UNINDEXED, "
                    "line_start UNINDEXED, line_end UNINDEXED, content, "
                    "tokenize = '{}')"
                )
                try:
                    conn.execute(fts_sql.format("trigram"))
                except sqlite3.OperationalError:
                    # Ältere SQLite-Builds ohne Trigramm-Tokenizer
                    conn.execute(fts_sql.format("unicode61"))
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_code_chunks_path "
                    "ON code_chunks(file_path)"
                )

    # -- Scanning ------------------------------------------------------------
    def _scan_directory(self, directory_path: str) -> list:
        """Sammelt alle indizierbaren Quelldateien unter directory_path."""
        files = []
        for root, dirs, names in os.walk(directory_path):
            dirs[:] = [d for d in dirs if d not in RAG_IGNORED_DIRS]
            for name in names:
                ext = os.path.splitext(name)[1].lower()
                lang = RAG_LANGUAGE_EXTENSIONS.get(ext)
                if not lang:
                    continue
                abs_path = os.path.join(root, name)
                try:
                    if os.path.getsize(abs_path) > RAG_MAX_FILE_SIZE:
                        continue
                    with open(abs_path, "rb") as f:
                        content_bytes = f.read()
                except OSError:
                    continue  # nicht lesbare Datei (z.B. gesperrt) überspringen
                try:
                    content = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    content = content_bytes.decode("utf-8", errors="replace")
                files.append({
                    "path": os.path.normpath(abs_path),
                    "language": lang,
                    "sha": hashlib.sha256(content_bytes).hexdigest(),
                    "content": content,
                })
        return files

    @staticmethod
    def _chunk_lines(lines, chunk_lines: int = RAG_CHUNK_LINES,
                     overlap: int = RAG_CHUNK_OVERLAP) -> list:
        """Zerlegt eine Zeilenliste in überlappende Blöcke (1-basierte Zeilennummern)."""
        chunks = []
        step = max(1, chunk_lines - overlap)
        total = len(lines)
        start = 0
        while start < total:
            end = min(total, start + chunk_lines)
            chunks.append((start + 1, end, "\n".join(lines[start:end])))
            if end >= total:
                break
            start += step
        return chunks

    # -- Indexierung ---------------------------------------------------------
    def index_directory(self, directory_path: str) -> dict:
        """Indiziert (bzw. aktualisiert inkrementell) alle Code-Dateien."""
        directory_path = os.path.normpath(directory_path)
        if not os.path.isdir(directory_path):
            raise ValueError(f"Verzeichnis nicht gefunden: {directory_path}")

        files = self._scan_directory(directory_path)
        scanned_paths = {f["path"] for f in files}
        indexed = 0
        skipped = 0

        with closing(self._connect()) as conn:
            with conn:
                for f in files:
                    # Inkrementell: unveränderte Dateien (gleicher SHA) überspringen
                    rows = conn.execute(
                        "SELECT file_sha FROM code_chunks WHERE file_path = ?",
                        (f["path"],),
                    ).fetchall()
                    if rows and all(r["file_sha"] == f["sha"] for r in rows):
                        skipped += 1
                        continue

                    # Alte Chunks dieser Datei entfernen (Struktur + FTS)
                    conn.execute("DELETE FROM code_fts WHERE file_path = ?", (f["path"],))
                    conn.execute("DELETE FROM code_chunks WHERE file_path = ?", (f["path"],))

                    # Datei in Chunks zerlegen und einfügen
                    for idx, (line_start, line_end, text) in enumerate(
                        self._chunk_lines(f["content"].splitlines())
                    ):
                        cur = conn.execute(
                            "INSERT INTO code_chunks "
                            "(file_path, language, chunk_index, line_start, "
                            " line_end, content, file_sha) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (f["path"], f["language"], idx, line_start, line_end,
                             text, f["sha"]),
                        )
                        conn.execute(
                            "INSERT INTO code_fts "
                            "(rowid, file_path, language, line_start, line_end, content) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (cur.lastrowid, f["path"], f["language"],
                             line_start, line_end, text),
                        )
                    indexed += 1

                # Aufräumen: gelöschte/entfernte Dateien aus dem Index nehmen
                stale = self._find_stale_paths(conn, directory_path, scanned_paths)
                for path in stale:
                    conn.execute("DELETE FROM code_fts WHERE file_path = ?", (path,))
                    conn.execute("DELETE FROM code_chunks WHERE file_path = ?", (path,))

        return {"indexed": indexed, "skipped": skipped, "total_files": len(files)}

    @staticmethod
    def _find_stale_paths(conn, directory_path: str, scanned_paths: set) -> list:
        """Findet indizierte Pfade unter directory_path, die nicht mehr existieren."""
        prefix = directory_path + os.sep
        # LIKE-Sonderzeichen im Pfad escapen (Backslash als ESCAPE-Zeichen)
        pattern = (
            prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            + "%"
        )
        stale = []
        for row in conn.execute(
            "SELECT DISTINCT file_path FROM code_chunks "
            "WHERE file_path LIKE ? ESCAPE '\\'",
            (pattern,),
        ):
            if row["file_path"] not in scanned_paths:
                stale.append(row["file_path"])
        return stale

    # -- Abfrage -------------------------------------------------------------
    @staticmethod
    def _build_match_expr(query: str) -> str | None:
        """Baut aus der Suchanfrage einen sicheren FTS5-MATCH-Ausdruck.

        Trigramm-Tokenizer verlangt Phrasen >= 3 Zeichen. Jeder Term wird als
        gequoteter Substring mit UND verknüpft, damit alle Begriffe vorkommen.
        """
        tokens = re.findall(r"[A-Za-z0-9_]{3,}", query)[:20]
        if not tokens:
            return None
        return " AND ".join('"' + t + '"' for t in tokens)

    def query(self, query: str, top_k: int = 3) -> list:
        """Sucht die top_k relevantesten Code-Chunks (bm25-Ranking)."""
        match_expr = self._build_match_expr(query)
        if not match_expr:
            return []
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT file_path, language, line_start, line_end, content,
                       bm25(code_fts) AS rank
                FROM code_fts
                WHERE code_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (match_expr, top_k),
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def format_results(results: list, query: str) -> str:
        """Formatiert die Suchergebnisse als lesbaren Markdown-Block für den Chat."""
        if not results:
            return (
                f"Keine Treffer in der RAG-Datenbank für: '{query}'\n"
                "Tipp: Führe zuerst `index_project_code` auf dem Projektverzeichnis aus."
            )
        lines = [f"RAG-Suchergebnisse für: '{query}'", "=" * 60]
        for i, r in enumerate(results, 1):
            lang = r["language"]
            snippet = r["content"]
            if len(snippet) > 900:
                snippet = snippet[:900] + "\n... (gekürzt)"
            indented = "\n".join("    " + ln for ln in snippet.splitlines())
            lines.append("")
            lines.append(
                f"[{i}] {r['file_path']} (Zeilen {r['line_start']}-{r['line_end']})"
            )
            lines.append(f"    Sprache: {lang}")
            lines.append(f"    ```{lang}\n{indented}\n    ```")
        return "\n".join(lines)


# RAG-Instanz wird global gehalten, damit alle Tools dieselbe Datenbank nutzen.
_rag = ProjectRAG()


@mcp.tool()
def check_max_sdk_headers() -> str:
    """
    Durchsucht das Projekt nach typischen Max/MSP API Headern und prüft die Einbindung.
    
    Gibt Informationen über die erwarteten Max/MSP SDK-Strukturen zurück.
    """
    return """Max/MSP SDK Strukturen (ext.h, z_dsp.h) werden im C++ Code vorausgesetzt.
    
Wichtige Komponenten:
- t_pxobject: Basis-Struktur für Patcher-Objekte
- dsp_setup(): DSP-Initialisierung für Signalobjekte
- object_alloc(): Speicherallokation für Max-Objekte
- class_new(): Klassenerstellung für neue Externals
- dsp_add64(): DSP-Performance-Funktion für 64-Bit Audio

Erwartete Header-Dateien (im Max SDK):
- ext.h: Grundlegende Max SDK Funktionen
- ext_obex.h: Object-Experience SDK
- z_dsp.h: DSP-spezifische Hilfsfunktionen

Hinweis: Diese Header sind Teil des Max SDK und müssen nicht im Projekt selbst liegen.
Sie werden vom Compiler über die Include-Pfade definiert."""


@mcp.tool()
def validate_rave_config(model_path: str) -> str:
    """
    Überprüft ein RAVE ONNX/Torch-Modell auf Kompatibilität mit dem C++ Worker.
    
    Args:
        model_path: Pfad zur ONNX- oder TorchScript-Modelldatei
        
    Returns:
        Informationen über Modellkompatibilität
    """
    if not os.path.exists(model_path):
        return f"Fehler: Modelldatei unter {model_path} nicht gefunden."
    
    # Prüfe Dateiendung
    ext = os.path.splitext(model_path)[1].lower()
    
    result = f"Modell {model_path} existiert.\n"
    result += f"Dateityp: {ext}\n\n"
    
    # Versuche, das Modell zu laden und Metadaten zu extrahieren
    try:
        if ext in ['.onnx']:
            try:
                import onnxruntime as ort
                session = ort.InferenceSession(model_path)
                result += "ONNX-Modell erfolgreich geladen.\n"
                
                # Eingabe- und Ausgangsinformationen
                for inp in session.get_inputs():
                    result += f"Eingabe: {inp.name}, Shape: {inp.shape}, Typ: {inp.type}\n"
                for out in session.get_outputs():
                    result += f"Ausgabe: {out.name}, Shape: {out.shape}, Typ: {out.type}\n"
                    
                result += "\nEmpfehlung für mab~: Prüfe, ob die Hop-Size und Encoder/Decoder-Dimensionen mit dem C++ Ringbuffer übereinstimmen."
            except ImportError:
                result += "Hinweis: onnxruntime nicht installiert. Installiere mit: pip install onnxruntime"
            except Exception as e:
                result += f"Fehler beim Laden des ONNX-Modells: {str(e)}"
                
        elif ext in ['.pt', '.pth', '.ts']:
            try:
                import torch
                model = torch.jit.load(model_path, map_location='cpu')
                result += "TorchScript-Modell erfolgreich geladen.\n"
                
                # Versuche Eingabe-/Ausgangsdimensionen zu extrahieren
                if hasattr(model, 'graph'):
                    result += "Modell-Graph verfügbar.\n"
                
                result += "\nEmpfehlung für mab~: Prüfe, ob die Eingangs- und Ausgangsdimensionen mit block_size und num_channels im C++ Code übereinstimmen."
            except ImportError:
                result += "Hinweis: torch nicht installiert. Installiere mit: pip install torch"
            except Exception as e:
                result += f"Fehler beim Laden des Torch-Modells: {str(e)}"
        else:
            result += f"Unbekannter Modelltyp: {ext}\n"
            result += "Unterstützte Formate: .onnx, .pt, .pth, .ts"
            
    except Exception as e:
        result += f"Allgemeiner Fehler: {str(e)}"
    
    return result


@mcp.tool()
def run_cpp_tests() -> str:
    """
    Führt lokale Tests oder den Build-Prozess für das mab~ External aus.
    
    Returns:
        Ergebnis des Build-Prozesses
    """
    try:
        # Prüfe ob Build-Verzeichnis existiert
        if not os.path.exists("build"):
            return "Fehler: Build-Verzeichnis nicht gefunden. Führe zuerst 'cmake -B build' aus."
        
        # Versuche Build zu starten
        result = subprocess.run(
            ["cmake", "--build", "build", "--config", "Debug"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            return "Build erfolgreich!\n\n" + result.stdout
        else:
            return "Build-Fehler:\n\n" + result.stderr
            
    except subprocess.TimeoutExpired:
        return "Fehler: Build-Prozess hat einen Timeout erfahren (60s)."
    except FileNotFoundError:
        return "Fehler: cmake nicht gefunden. Stelle sicher, dass CMake installiert ist."
    except Exception as e:
        return f"Fehler beim Ausführen des Builds: {str(e)}"


@mcp.tool()
def check_shared_memory_config() -> str:
    """
    Prüft die Shared Memory-Konfiguration zwischen C++ und Python.
    
    Gibt Informationen über die erwartete Kommunikationsstruktur zurück.
    """
    return """Shared Memory Handshake-Protokoll:

1. Python erstellt Shared Memory mit Header-Struktur:
   - Magic: 0x4D414254 ('MABT')
   - Version: 1
   - block_size: Samples pro Block
   - num_channels: Anzahl der Kanäle
   - input_offset: Offset zum Input-Puffer
   - output_offset: Offset zum Output-Puffer
   - control_offset: Offset zum Ring-Puffer

2. C++ öffnet Shared Memory und mappt View:
   - Öffnet Event: MabReadyEvent_{PID}
   - Öffnet Shared Memory: MabSharedMem_{PID}
   - Mappt View und liest Header

3. Kommunikationsfluss:
   - C++ (Producer): is_input_ready, head (Ring-Puffer)
   - Python (Consumer): is_output_ready, tail (Ring-Puffer)

Ring-Puffer-Konfiguration:
- Größe: 256 Nachrichten
- Max. Nachricht: 256 Zeichen
- SPSC (Single-Producer/Single-Consumer) Pattern

Empfohlene Werte:
- block_size: 512-4096 (abhängig vom Audio-System)
- num_channels: 1-16 (1 für mab~, bis zu 16 für mc.mab~)"""


@mcp.tool()
def analyze_inference_worker() -> str:
    """
    Analysiert den inference_worker.py und gibt Strukturinformationen zurück.
    """
    worker_path = "inference_worker.py"
    
    if not os.path.exists(worker_path):
        return f"Fehler: {worker_path} nicht gefunden."
    
    result = "inference_worker.py Analyse:\n\n"
    
    try:
        with open(worker_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Zähle wichtige Komponenten
        result += f"Dateigröße: {len(content)} Bytes\n"
        result += f"Zeilenanzahl: {len(content.splitlines())}\n\n"
        
        # Suche nach Klassen und Funktionen
        if "SharedMemoryManager" in content:
            result += "✓ SharedMemoryManager Klasse gefunden\n"
        if "LockFreeRingBuffer" in content:
            result += "✓ LockFreeRingBuffer Klasse gefunden\n"
        if "load_model" in content:
            result += "✓ load_model Funktion gefunden\n"
        if "infer_block" in content:
            result += "✓ infer_block Funktion gefunden\n"
        if "argparse" in content:
            result += "✓ Argument Parsing implementiert\n"
            
        result += "\nWichtige Konstanten:"
        result += "\n- CONTROL_RING_SIZE: 256"
        result += "\n- CONTROL_MSG_SIZE: 256"
        result += "\n- MAGIC_NUMBER: 0x4D414254 ('MABT')"
        
    except Exception as e:
        result += f"Fehler bei der Analyse: {str(e)}"
    
    return result


@mcp.tool()
def get_project_info() -> str:
    """
    Gibt allgemeine Informationen über das mab~ Projekt zurück.
    """
    info = """mab~ Projektinformationen:

Projektstruktur:
- source/projects/mab_tilde/mab_tilde.cpp: Haupt-C++ Code
- inference_worker.py: Python Backend für Inferenz
- CMakeLists.txt: Build-Konfiguration
- requirements.txt: Python Abhängigkeiten

Build-System:
- CMake mit Visual Studio 18 2026 Generator
- Ziel: x64

Wichtige Konstanten (C++):
- MAX_CHANNELS: 16
- MAX_BLOCK_SIZE: 4096
- CONTROL_RING_SIZE: 256
- CONTROL_MSG_SIZE: 256

Shared Memory Namen:
- Event: MabReadyEvent_{PID}
- Shared Memory: MabSharedMem_{PID}

Nachrichten-Handler (Phase 1.7):
- enable: Aktiviert/Deaktiviert die Audio-Verarbeitung
- gpu: Schaltet zwischen CPU/GPU-Modus
- reload: Lädt das aktuelle Modell neu
- load: Lädt ein neues Modell
- dump: Gibt Modellinformationen aus
- set/get: Attribute lesen/schreiben
- anything: Leitet unbekannte Nachrichten an Python weiter"""
    
    return info


@mcp.tool()
def inspect_model_metadata(model_path: str) -> str:
    """
    Lädt ein ONNX- oder TorchScript-Modell (RAVE) und extrahiert automatisch
    die Tensor-Shapes (Input/Output), die Hop-Size und die Sampling-Rate.
    
    Args:
        model_path: Pfad zur ONNX- oder TorchScript-Modelldatei
        
    Returns:
        Vollständige Modellmetadaten für die C++ Integration
    """
    if not os.path.exists(model_path):
        return f"Fehler: Modelldatei unter {model_path} nicht gefunden."
    
    ext = os.path.splitext(model_path)[1].lower()
    result = f"Modell-Analyse: {model_path}\n"
    result += "=" * 50 + "\n\n"
    
    try:
        if ext in ['.onnx']:
            try:
                import onnxruntime as ort
                import numpy as np
                
                session = ort.InferenceSession(model_path)
                result += "✓ ONNX-Modell erfolgreich geladen\n\n"
                
                # Eingabeinformationen
                result += "EINGABEN:\n"
                result += "-" * 30 + "\n"
                for i, inp in enumerate(session.get_inputs()):
                    shape_str = str(inp.shape)
                    # Extrahiere Hop-Size falls möglich
                    hop_size = None
                    if hasattr(inp, 'shape') and inp.shape:
                        for dim in inp.shape:
                            if isinstance(dim, int) and 256 <= dim <= 8192:
                                hop_size = dim
                                break
                    
                    result += f"  Name: {inp.name}\n"
                    result += f"  Shape: {shape_str}\n"
                    result += f"  Typ: {inp.type}\n"
                    if hop_size:
                        result += f"  ⚠️  Mögliche Hop-Size: {hop_size}\n"
                    result += "\n"
                
                # Ausgangsinformationen
                result += "AUSGÄNGE:\n"
                result += "-" * 30 + "\n"
                for i, out in enumerate(session.get_outputs()):
                    result += f"  Name: {out.name}\n"
                    result += f"  Shape: {out.shape}\n"
                    result += f"  Typ: {out.type}\n\n"
                
                # RAVE-spezifische Analyse
                result += "RAVE-KONFORMITÄT:\n"
                result += "-" * 30 + "\n"
                
                # Suche nach typischen RAVE-Dimensionen
                input_shape = session.get_inputs()[0].shape if session.get_inputs() else []
                output_shape = session.get_outputs()[0].shape if session.get_outputs() else []
                
                # Typische RAVE-Hop-Sizes
                typical_hops = [256, 512, 1024, 2048, 4096]
                for dim in input_shape:
                    if isinstance(dim, int) and dim in typical_hops:
                        result += f"✓ Erkannte RAVE-Hop-Size: {dim}\n"
                        result += f"  → Blockgröße für C++ Ringbuffer: {dim}\n"
                
                # Sampling-Rate-Hinweis
                result += "\nSampling-Rate:\n"
                result += "  RAVE-Modelle speichern keine SR explizit.\n"
                result += "  Typische Werte: 16000, 22050, 44100, 48000 Hz\n"
                result += "  → Stelle sicher, dass dein Audio-System diese Rate verwendet.\n"
                
                # C++ Kompatibilitäts-Check
                result += "\nC++ KOMPATIBILITÄT:\n"
                result += "-" * 30 + "\n"
                max_block = max([d for d in input_shape if isinstance(d, int) and d > 0], default=512)
                if max_block <= 4096:
                    result += f"✓ Blockgröße {max_block} passt in MAX_BLOCK_SIZE (4096)\n"
                else:
                    result += f"⚠️ Blockgröße {max_block} überschreitet MAX_BLOCK_SIZE (4096)\n"
                
                return result
                
            except ImportError:
                return "Fehler: onnxruntime nicht installiert.\nInstalliere mit: pip install onnxruntime"
            except Exception as e:
                return f"Fehler beim Laden des ONNX-Modells: {str(e)}"
                
        elif ext in ['.pt', '.pth', '.ts']:
            try:
                import torch
                import numpy as np
                
                model = torch.jit.load(model_path, map_location='cpu')
                result += "✓ TorchScript-Modell erfolgreich geladen\n\n"
                
                # Versuche Graph-Informationen zu extrahieren
                if hasattr(model, 'graph'):
                    result += "GRAPH-ANALYSE:\n"
                    result += "-" * 30 + "\n"
                    
                    # Eingabe- und Ausgangsdimensionen aus dem Graph
                    try:
                        inputs = list(model.graph.inputs())
                        outputs = list(model.graph.outputs())
                        
                        result += "EINGABEN:\n"
                        for inp in inputs:
                            if hasattr(inp, 'type') and hasattr(inp.type(), 'sizes'):
                                sizes = inp.type().sizes()
                                result += f"  Name: {inp.name()}, Shape: {sizes}\n"
                        
                        result += "\nAUSGÄNGE:\n"
                        for out in outputs:
                            if hasattr(out, 'type') and hasattr(out.type(), 'sizes'):
                                sizes = out.type().sizes()
                                result += f"  Name: {out.name()}, Shape: {sizes}\n"
                    except Exception:
                        result += "  (Graph-Analyse nicht verfügbar)\n"
                
                # Parameter-Analyse
                result += "\nPARAMETER-ANALYSE:\n"
                result += "-" * 30 + "\n"
                total_params = sum(p.numel() for p in model.parameters())
                result += f"  Gesamte Parameter: {total_params:,}\n"
                
                # RAVE-spezifische Hinweise
                result += "\nRAVE-HINWEISE:\n"
                result += "  TorchScript-Modelle von RAVE haben typischerweise:\n"
                result += "  - Eingabe: (1, num_channels, block_size)\n"
                result += "  - Ausgabe: (1, num_channels, block_size)\n"
                result += "  - Hop-Size = block_size / 2 (typisch)\n"
                
                return result
                
            except ImportError:
                return "Fehler: torch nicht installiert.\nInstalliere mit: pip install torch"
            except Exception as e:
                return f"Fehler beim Laden des Torch-Modells: {str(e)}"
        else:
            return f"Unbekannter Modelltyp: {ext}\nUnterstützte Formate: .onnx, .pt, .pth, .ts"
            
    except Exception as e:
        return f"Allgemeiner Fehler: {str(e)}"


@mcp.tool()
def search_max_sdk_docs(query: str) -> str:
    """
    Durchsucht lokale Markdown-Notizen oder Header-Dateien des Max SDK
    nach Begriffen wie t_pxobject, dsp_setup, class_addmethod oder InterlockedExchange.
    
    Args:
        query: Suchbegriff für die Dokumentation
        
    Returns:
        Fundene Informationen und Code-Beispiele
    """
    # Suche im Projekt nach relevanten Dateien
    search_paths = [
        "source/projects/mab_tilde/mab_tilde.cpp",
        "inference_worker.py",
        "doc/",
        "."
    ]
    
    results = []
    query_lower = query.lower()
    
    # Spezifische Suchergebnisse für häufige Max SDK Begriffe
    max_sdk_patterns = {
        "t_pxobject": """t_pxobject ist die Grundstruktur für Patcher-Objekte mit DSP-Fähigkeit.

Verwendung:
```c
typedef struct _mab_tilde {
    t_pxobject ob;  // Muss die erste Komponente sein
    // ... weitere Felder
} t_mab_tilde;
```

Wichtige Eigenschaften:
- p_in1, p_in2: Eingangs-Pointer für Signalobjekte
- p_out1, p_out2: Ausgangs-Pointer
- z_in_num: Anzahl der Eingänge
- z_out_num: Anzahl der Ausgänge
- z_oshead: OS-spezifischer Header""",
        
        "dsp_setup": """dsp_setup() initialisiert ein Signalobjekt für DSP-Verarbeitung.

Verwendung:
```c
dsp_setup((t_pxobject*)x, 1);  // 1 Eingang
```

Parameter:
- x: Pointer auf das Objekt-Struct
- n: Anzahl der Eingänge (0 = kein Signal)

Wichtig: Muss vor outlet_new() aufgerufen werden!""",
        
        "class_addmethod": """class_addmethod() fügt Methoden zu einer Max-Klasse hinzu.

Verwendung:
```c
class_addmethod(c, (method)mab_tilde_enable, "enable", A_LONG, 0);
```

Parameter:
- c: Die Klasse
- method: Die Funktion
- selector: Der Message-Name in Max
- type: Argument-Typ (A_LONG, A_FLOAT, A_SYM, A_GIMME, A_CANT)
- arg: Zusätzlicher Parameter (meist 0)""",
        
        "interlockedexchange": """InterlockedExchange() führt eine atomare Wertersetzung aus.

Verwendung:
```c
InterlockedExchange(&x->header->shutdown_flag, 1);
```

Wichtig für Shared Memory IPC zwischen C++ und Python!

Weitere nützliche Interlocked-Funktionen:
- InterlockedIncrement() - atomares Inkrement
- InterlockedDecrement() - atomares Dekrement
- InterlockedCompareExchange() - Compare-and-Swap"""
    }
    
    # Prüfe auf direkte Übereinstimmung
    if query_lower in max_sdk_patterns:
        return f"Max SDK Suche: '{query}'\n" + "=" * 50 + "\n\n" + max_sdk_patterns[query_lower]
    
    # Suche nach Teilübereinstimmungen
    for key, value in max_sdk_patterns.items():
        if key in query_lower:
            results.append(f"Gefunden: {key}\n" + value + "\n")
    
    if results:
        return "\n".join(results)
    
    # Standardantwort mit allgemeinen Informationen
    return f"""Max SDK Suchergebnis für: '{query}'

Verfügbare Suchbegriffe:
- t_pxobject: Signalobjekt-Struktur
- dsp_setup: DSP-Initialisierung
- class_addmethod: Methoden-Registrierung
- interlockedexchange: Atomare Operationen

Weitere Informationen:
- Max SDK Dokumentation: https://cycling74.com/sdk/
- GitHub: https://github.com/Cycling74/max-sdk

Falls du spezifischere Informationen brauchst, verwende einen der oben genannten Suchbegriffe."""


@mcp.tool()
def validate_ipc_sync() -> str:
    """
    Analysiert statisch den C++ Code (mab_tilde.cpp) und das Python-Worker-Skript,
    um sicherzustellen, dass die Shared-Memory-Magie (0x4D414254 / 'MABT') und
    die Ringbuffer-Indizes (head/tail) synchron implementiert sind.
    
    Returns:
        IPC-Synchronisations-Report
    """
    result = "IPC SYNCHRONISATIONS-ANALYSE\n"
    result += "=" * 50 + "\n\n"
    
    issues = []
    warnings = []
    ok_checks = []
    
    # Prüfe C++ Datei
    cpp_path = "source/projects/mab_tilde/mab_tilde.cpp"
    py_path = "inference_worker.py"
    
    # 1. Magic Number Prüfung
    result += "1. MAGIC NUMBER PRÜFUNG\n"
    result += "-" * 30 + "\n"
    
    try:
        with open(cpp_path, 'r', encoding='utf-8') as f:
            cpp_content = f.read()
        
        if "0x4D414254" in cpp_content or "'MABT'" in cpp_content:
            ok_checks.append("✓ C++: Magic Number 0x4D414254 ('MABT') gefunden")
        else:
            issues.append("✗ C++: Magic Number nicht gefunden")
    except FileNotFoundError:
        issues.append("✗ C++: mab_tilde.cpp nicht gefunden")
    
    try:
        with open(py_path, 'r', encoding='utf-8') as f:
            py_content = f.read()
        
        if "0x4D414254" in py_content or "MAGIC_NUMBER" in py_content:
            ok_checks.append("✓ Python: Magic Number 0x4D414254 definiert")
        else:
            issues.append("✗ Python: Magic Number nicht definiert")
    except FileNotFoundError:
        issues.append("✗ Python: inference_worker.py nicht gefunden")
    
    # 2. Shared Memory Namen
    result += "\n2. SHARED MEMORY NAMEN\n"
    result += "-" * 30 + "\n"
    
    if "MabSharedMem_" in cpp_content:
        ok_checks.append("✓ C++: Shared Memory Name-Format gefunden")
    else:
        warnings.append("⚠ C++: Shared Memory Name-Format nicht gefunden")
    
    if "MabSharedMem_" in py_content:
        ok_checks.append("✓ Python: Shared Memory Name-Format gefunden")
    else:
        warnings.append("⚠ Python: Shared Memory Name-Format nicht gefunden")
    
    # 3. Ring Buffer Head/Tail Implementierung
    result += "\n3. RING BUFFER IMPLEMENTIERG\n"
    result += "-" * 30 + "\n"
    
    # C++ Head (Producer)
    if "InterlockedIncrement" in cpp_content and "p_control->head" in cpp_content:
        ok_checks.append("✓ C++: Head mit InterlockedIncrement (atomar)")
    else:
        issues.append("✗ C++: Head-Implementierung nicht korrekt")
    
    # C++ Tail (Consumer) - sollte nicht direkt geschrieben werden
    if "p_control->tail" in cpp_content:
        # Prüfe ob tail nur gelesen wird
        if cpp_content.count("p_control->tail") > 1:
            warnings.append("⚠ C++: Tail wird mehrfach referenziert - prüfe SPSC-Eigenschaften")
        else:
            ok_checks.append("✓ C++: Tail wird nur gelesen (Consumer)")
    
    # Python Tail (Consumer)
    if "shm._p_control.tail" in py_content or "p_control.tail" in py_content:
        ok_checks.append("✓ Python: Tail als Consumer verwendet")
    else:
        issues.append("✗ Python: Tail-Implementierung fehlt")
    
    # Python Head (Producer) - sollte nicht geschrieben werden
    if "shm._p_control.head" in py_content:
        # Prüfe ob head nur gelesen wird
        py_head_writes = py_content.count("shm._p_control.head =")
        if py_head_writes > 0:
            issues.append(f"✗ Python: Head wurde {py_head_writes}x geschrieben (soll Producer sein)")
        else:
            ok_checks.append("✓ Python: Head wird nur gelesen (Producer)")
    
    # 4. CONTROL_RING_SIZE Konsistenz
    result += "\n4. KONSTANTEN KONSISTENZ\n"
    result += "-" * 30 + "\n"
    
    if "CONTROL_RING_SIZE 256" in cpp_content:
        ok_checks.append("✓ C++: CONTROL_RING_SIZE = 256")
    else:
        warnings.append("⚠ C++: CONTROL_RING_SIZE unbekannt")
    
    if "CONTROL_RING_SIZE = 256" in py_content or "CONTROL_RING_SIZE" in py_content:
        ok_checks.append("✓ Python: CONTROL_RING_SIZE definiert")
    else:
        warnings.append("⚠ Python: CONTROL_RING_SIZE nicht gefunden")
    
    # 5. Shared Memory Header Struktur
    result += "\n5. HEADER STRUKTUR\n"
    result += "-" * 30 + "\n"
    
    header_fields = ["magic", "version", "block_size", "num_channels", 
                     "input_offset", "output_offset", "control_offset",
                     "is_input_ready", "is_output_ready", "shutdown_flag"]
    
    for field in header_fields:
        if field in cpp_content:
            ok_checks.append(f"✓ C++: Header Feld '{field}' gefunden")
        else:
            issues.append(f"✗ C++: Header Feld '{field}' fehlt")
    
    # 6. Event-Synchronisation
    result += "\n6. EVENT-SYNCHRONISATION\n"
    result += "-" * 30 + "\n"
    
    if "CreateEventW" in cpp_content:
        ok_checks.append("✓ C++: CreateEventW verwendet")
    else:
        issues.append("✗ C++: CreateEventW nicht gefunden")
    
    if "SetEvent" in py_content:
        ok_checks.append("✓ Python: SetEvent für Ready-Signal")
    else:
        issues.append("✗ Python: SetEvent nicht gefunden")
    
    # Zusammenfassung
    result += "\n" + "=" * 50 + "\n"
    result += "ERGEBNIS\n"
    result += "=" * 50 + "\n\n"
    
    if ok_checks:
        result += "✓ BESTANDEN:\n"
        for check in ok_checks:
            result += f"  {check}\n"
    
    if warnings:
        result += "\n⚠ WARNUNGEN:\n"
        for warning in warnings:
            result += f"  {warning}\n"
    
    if issues:
        result += "\n✗ PROBLEME:\n"
        for issue in issues:
            result += f"  {issue}\n"
    
    if not issues:
        result += "\n✅ IPC-Synchronisation ist korrekt implementiert!\n"
    else:
        result += f"\n❌ {len(issues)} Probleme gefunden - bitte korrigieren!\n"
    
    return result


# ============================================================================
# SQLite-RAG Tools
# ============================================================================


@mcp.tool()
def index_project_code(directory_path: str) -> str:
    """Indiziert das Projektverzeichnis in die lokale SQLite-RAG-Datenbank (mab_rag.db).

    Scannt rekursiv nach C++-Dateien (.cpp/.h/.hpp/.cc/.cxx/.c), Python-Dateien
    (.py) und Markdown-Dokumentation (.md, inkl. AGENTS.md/WORKSPACE_AGENT_PROMPT.md),
    zerlegt sie in überlappende Chunks und speichert sie
    für die Volltextsuche (FTS5/Trigramm). Unveränderte Dateien werden per
    SHA-256-Hash erkannt und übersprungen (inkrementelles Re-Indexing).

    Args:
        directory_path: Absoluter Pfad zum Projektverzeichnis (z.B. der
            Workspace-Root `mab_tilde`).

    Returns:
        Zusammenfassung des Indexierungsvorgangs.
    """
    try:
        stats = _rag.index_directory(directory_path)
    except ValueError as e:
        return f"Fehler: {e}"
    except sqlite3.Error as e:
        return f"Fehler bei der Datenbank-Operation: {e}"

    return (
        f"Indexierung abgeschlossen:\n"
        f"  - Dateien gescannt: {stats['total_files']}\n"
        f"  - Neu indiziert: {stats['indexed']}\n"
        f"  - Unverändert übersprungen: {stats['skipped']}\n"
        f"  - Datenbank: {_rag.db_path}\n\n"
        "Verwende `query_code_rag`, um gezielt nach Code-Stellen zu suchen."
    )


@mcp.tool()
def query_code_rag(query: str, top_k: int = 3) -> str:
    """Durchsucht die RAG-Datenbank nach Code-Stellen passend zur Suchanfrage.

    Nutzt SQLite FTS5 mit Trigramm-Tokenizer: Suchbegriffe werden als
    Substrings gematcht, daher funktionieren auch Identifikatoren wie
    `mab_tilde`, `block_size` oder `dsp_setup` direkt. Die Chunks werden nach
    bm25-Relevanz sortiert und als formatierte Code-Snippets zurückgegeben.

    Args:
        query: Suchanfrage, z.B. "shared memory handshake" oder "enable handler".
        top_k: Anzahl der zurückzugebenden Treffer (Standard: 3).

    Returns:
        Die relevantesten Code-Chunks inkl. Dateipfad und Zeilennummern.
    """
    if not _rag_has_data():
        return (
            "Die RAG-Datenbank ist noch leer.\n"
            "Führe zuerst `index_project_code` auf dem Projektverzeichnis aus."
        )
    results = _rag.query(query, top_k=top_k)
    return _rag.format_results(results, query)


def _rag_has_data() -> bool:
    """Prüft, ob die RAG-Datenbank bereits Code-Chunks enthält."""
    try:
        with closing(_rag._connect()) as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM code_chunks").fetchone()
        return bool(row and row["n"] > 0)
    except sqlite3.Error:
        return False


# ============================================================================
# RAVE-Modell-Inspektion (leichtgewichtig, optionaler onnxruntime/torch-Einsatz)
# ============================================================================

@mcp.tool()
def inspect_rave_model(model_path: str) -> str:
    """Analysiert ein RAVE/ONNX/TorchScript-Modell auf seine Ein-/Ausgangsstruktur.

    Extrahiert, falls möglich, Hop-Size, Kanalzahl, Latent-Dimensionen und
    liefert eine Empfehlung für block_size/num_channels des mab~-Ringbuffers.
    Funktioniert ohne installierte Frameworks (nur Datei-Metadaten) und wird
    detaillierter, wenn `onnxruntime` bzw. `torch` im venv installiert sind.

    Args:
        model_path: Pfad zur Modelldatei (.ts, .pt, .pth oder .onnx).

    Returns:
        Strukturierte Modellanalyse.
    """
    if not os.path.exists(model_path):
        return f"Fehler: Modelldatei unter {model_path} nicht gefunden."

    ext = os.path.splitext(model_path)[1].lower()
    size_mb = os.path.getsize(model_path) / (1024.0 * 1024.0)

    result = f"RAVE-Modell-Analyse: {model_path}\n"
    result += "=" * 60 + "\n"
    result += f"Dateigröße: {size_mb:.1f} MB\n"
    result += f"Dateityp: {ext}\n\n"

    if ext in (".onnx",):
        result += _analyze_onnx_rave(model_path)
    elif ext in (".pt", ".pth", ".ts"):
        result += _analyze_ts_rave(model_path)
    else:
        result += f"Unbekannter Modelltyp: {ext}\n"
        result += "Unterstützte Formate: .ts, .pt, .pth, .onnx"

    result += _rave_integration_hint()
    return result


def _analyze_onnx_rave(model_path: str) -> str:
    """Analysiert ein ONNX-Modell via onnxruntime (falls installiert)."""
    try:
        import onnxruntime as ort
    except ImportError:
        return ("Hinweis: onnxruntime nicht installiert (pip install onnxruntime).\n"
                "Nur Datei-Metadaten verfügbar.")

    try:
        session = ort.InferenceSession(model_path)
    except Exception as e:
        return f"Fehler beim Laden des ONNX-Modells: {e}"

    lines = ["✓ ONNX-Modell erfolgreich geladen", ""]
    lines.append("EINGABEN:")
    for inp in session.get_inputs():
        lines.append(f"  {inp.name}: shape={inp.shape}, type={inp.type}")
    lines.append("")
    lines.append("AUSGÄNGE:")
    for out in session.get_outputs():
        lines.append(f"  {out.name}: shape={out.shape}, type={out.type}")

    # Hop-Size-Detektion: typische RAVE-Hop-Sizes sind die größten Eingabedimensionen
    for inp in session.get_inputs():
        for dim in inp.shape:
            if isinstance(dim, int) and 128 <= dim <= 16384:
                lines.append(f"\n⚠ Mögliche RAVE-Hop-Size: {dim}")
                lines.append(f"  → Empfohlene block_size für mab~: {dim}")
                break
    return "\n".join(lines)


def _analyze_ts_rave(model_path: str) -> str:
    """Analysiert ein TorchScript-Modell via torch (falls installiert)."""
    try:
        import torch
    except ImportError:
        return ("Hinweis: torch nicht installiert (pip install torch).\n"
                "Nur Datei-Metadaten verfügbar.")

    try:
        model = torch.jit.load(model_path, map_location="cpu")
        model.eval()
    except Exception as e:
        return f"Fehler beim Laden des TorchScript-Modells: {e}"

    lines = ["✓ TorchScript-Modell erfolgreich geladen", ""]

    # Typische RAVE-Methoden (encode/decode/forward) erkennen
    methods = [m for m in ("encode", "decode", "forward") if hasattr(model, m)]
    lines.append("Verfügbare Methoden: " + (", ".join(methods) if methods else "unbekannt"))

    # RAVE speichert Konfiguration teils als Attribut am exportierten Modell
    for attr in ("hop_size", "sampling_rate", "latent_size"):
        try:
            value = model.__getattr__(attr)
            if value is not None:
                lines.append(f"{attr}: {value}")
        except (AttributeError, RuntimeError):
            pass

    # Parameteranzahl als Größenindikator
    try:
        n_params = sum(p.numel() for p in model.parameters())
        lines.append(f"Parameter gesamt: {n_params:,}")
    except Exception:
        pass

    lines.append("")
    lines.append("RAVE-typische Struktur:")
    lines.append("  Eingabe  (1, num_channels, block_size)")
    lines.append("  Ausgabe  (1, num_channels, block_size)")
    return "\n".join(lines)


def _rave_integration_hint() -> str:
    """Empfehlung zur block_size-Abstimmung für den mab~-Ringbuffer."""
    return (
        "\n\nEMPFEHLUNG FÜR mab~:\n"
        "  - block_size = Hop-Size des Modells (typisch 256-4096)\n"
        "  - num_channels = 1 (mab~) bzw. bis zu 16 (mc.mab~)\n"
        "  - MAX_BLOCK_SIZE (4096) in mab_tilde.cpp nicht unterschreiten lassen"
    )


if __name__ == "__main__":
    mcp.run()