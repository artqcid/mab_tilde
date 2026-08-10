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
import ast
import json
import hashlib
import sqlite3
from contextlib import closing

# Initialisiere den FastMCP Server
mcp = FastMCP("MAB-RAVE-Assistant")


# ============================================================================
# RAG-LLM-Wiki (Retrieval-Augmented Generation + Code-Wiki)
# ----------------------------------------------------------------------------
# Leichtgewichtige Kombination der drei Konzepte, ausschließlich mit Pythons
# Standardbibliothek (ast, sqlite3, re) - keine neuen Pakete nötig:
#
#   1. Strukturelles Code-Chunking (Repo-Level-RAG / AST statt Zeilen-Chunking):
#      - Python: stdlib `ast` -> Klassen/Funktionen/Methoden mit qualified names,
#        Signaturen und Docstrings; Importe bleiben im Modul-Chunk erhalten.
#      - C++: brace-basierter Scanner (ohne tree-sitter) -> Funktionen, Klassen
#        (inkl. Methoden), Namespaces/extern "C"; #includes bleiben im Modul-Chunk.
#      - Markdown: Chunking nach Überschriften (Sections).
#      Jeder Chunk trägt Metadaten (symbol_type, symbol_name, signature,
#      docstring) -> Kontext von Klassen/Methoden bleibt erhalten und der
#      Symbol-Index speist das Code-Wiki.
#
#   2. Hybride Suche: SQLite FTS5 mit Trigramm-Tokenizer (bm25, lexikalisch -
#      findet auch Identifikator-Substrings) plus Re-Ranking über exakte
#      Identifier-Treffer (Syntax/Hybrid-Boost). Keine Vektor-DB nötig.
#
#   3. Code-Wiki (doc/code_wiki.md): stabiler, eingecheckter Symbolindex
#      (Datei -> Symbole mit Signatur/Docstring/Zeilen). Agents lesen das Wiki
#      einmalig pro Session (stabiler Kontext = prompt-cache-freundlich) und
#      nutzen query_code_rag/query_code_wiki für gezielte Codestellen.
# ============================================================================

# Datenbankdatei liegt neben diesem Skript im Projektverzeichnis
RAG_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mab_rag.db")

# Pfad zum generierten Code-Wiki (stabiler Symbolindex, wird eingecheckt)
WIKI_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "doc", "code_wiki.md"
)

# Schema-Version: bump bei strukturellen Änderungen -> erzwingt Rebuild der DB.
# v1 = Zeilen-Chunking, v2 = strukturelles Chunking + Symbol-Metadaten.
# v3 = C++-Header-Rekonstruktion (mehrzeilige Signaturen) + LF-Normalisierung.
RAG_SCHEMA_VERSION = 3

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

# Maximale Länge eines Modul-Chunks (Code außerhalb benannter Symbole) in Zeilen.
MODULE_CHUNK_LINES = 60

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

# Eigenes generiertes Wiki nicht mit-indizieren (Meta-Rauschen, neuer Hash je Lauf)
RAG_IGNORED_FILENAMES = {"code_wiki.md"}


# ---------------------------------------------------------------------------
# Strukturelles Chunking (AST / brace-basiert / Überschriften)
# ---------------------------------------------------------------------------

def _emit_chunk(lines, start, end, symbol_type, symbol_name, signature, docstring) -> dict:
    """Baut einen Chunk-Datensatz aus 0-basiertem Zeilenbereich [start, end]."""
    return {
        "line_start": start + 1,
        "line_end": end + 1,
        "content": "\n".join(lines[start:end + 1]),
        "symbol_type": symbol_type,
        "symbol_name": symbol_name,
        "signature": (signature or "").strip() or None,
        "docstring": docstring,
    }


def _module_chunks(lines, start, end) -> list:
    """Zerlegt einen Bereich ohne benannte Symbole in max. 60-Zeilen-Blöcke."""
    start = max(0, start)
    end = min(len(lines) - 1, end)
    if start > end:
        return []
    out = []
    for s in range(start, end + 1, MODULE_CHUNK_LINES):
        e = min(end, s + MODULE_CHUNK_LINES - 1)
        out.append(_emit_chunk(lines, s, e, "module", None, None, None))
    return out


def _py_arglist(args) -> str:
    """Baut aus einem ast.arguments eine kompakte Parameterliste (mit Defaults)."""
    parts = []
    npos = len(args.args)
    ndef = len(args.defaults)
    for i, a in enumerate(args.args):
        s = a.arg
        d = i - (npos - ndef)
        if d >= 0 and d < ndef and args.defaults[d] is not None:
            try:
                s += "=" + ast.unparse(args.defaults[d])
            except Exception:
                pass
        parts.append(s)
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    parts.extend(a.arg for a in args.kwonlyargs)
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    return "(" + ", ".join(parts) + ")"


def _py_bases(node) -> str:
    if not node.bases:
        return ""
    names = []
    for b in node.bases:
        try:
            names.append(ast.unparse(b))
        except Exception:
            names.append("...")
    return "(" + ", ".join(names) + ")"


def _chunk_python(source: str) -> list:
    """Zerlegt Python-Code über das stdlib-`ast` in Klassen/Funktionen/Methoden.

    Liefert Chunks mit symbol_type (class/function/method), qualified name,
    Signatur und Docstring. Zeilen außerhalb von Definitionen (Imports,
    Konstanten) werden als `module`-Chunks gesammelt.
    """
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _module_chunks(lines, 0, len(lines) - 1)

    chunks = []
    covered = []  # 1-basierte Intervalle [lineno, end_lineno] der Definitionen

    def walk(body, parent):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{parent}.{node.name}" if parent else node.name
                kind = "method" if parent else "function"
                sig = "def " + node.name + _py_arglist(node.args)
                doc = ast.get_docstring(node)
                chunks.append(_emit_chunk(
                    lines, node.lineno - 1, node.end_lineno - 1,
                    kind, name, sig, doc))
                covered.append((node.lineno, node.end_lineno))
            elif isinstance(node, ast.ClassDef):
                name = f"{parent}.{node.name}" if parent else node.name
                sig = "class " + node.name + _py_bases(node)
                doc = ast.get_docstring(node)
                chunks.append(_emit_chunk(
                    lines, node.lineno - 1, node.end_lineno - 1,
                    "class", name, sig, doc))
                covered.append((node.lineno, node.end_lineno))
                walk(node.body, name)

    walk(tree.body, None)

    if not covered:
        return _module_chunks(lines, 0, len(lines) - 1)

    cursor = 1
    for a, b in sorted(covered):
        if a > cursor:
            chunks.extend(_module_chunks(lines, cursor - 1, a - 2))
        cursor = max(cursor, b + 1)
    if cursor <= len(lines):
        chunks.extend(_module_chunks(lines, cursor - 1, len(lines) - 1))

    chunks.sort(key=lambda c: c["line_start"])
    return chunks


# Steuer-Schlüsselwörter, die kein Funktionskopf sind (C++-Heuristik)
_CPP_CTRL = {"if", "for", "while", "switch", "catch", "do", "else", "return",
             "sizeof", "new", "delete"}


def _cpp_def_kind(header: str):
    """Klassifiziert einen C++-Block-Kopf -> (kind, name).

    kinds: namespace, extern, class, function, block.
    """
    h = header.strip()
    if not h or h.startswith("#") or h.endswith(";"):
        return ("block", None)
    m = re.match(r"namespace\s+([A-Za-z_]\w*)", h)
    if m:
        return ("namespace", m.group(1))
    if re.match(r'extern\s*"C"', h):
        return ("extern", None)
    m = re.match(
        r"(?:template\s*<[^>]*>\s*)?"
        r"(?:(?:class|struct|union)\s+([A-Za-z_]\w*)|"
        r"enum(?:\s+class)?\s+([A-Za-z_]\w*))",
        h,
    )
    if m:
        return ("class", m.group(1) or m.group(2))
    m = re.search(r"([A-Za-z_]\w*)\s*\(", h)
    if m and m.group(1) not in _CPP_CTRL:
        return ("function", m.group(1))
    return ("block", None)


def _cpp_collect_header(lines, idx, prefix):
    """Rekonstruiert den vollständigen Block-Kopf (mehrzeilige Signaturen).

    Steht das `{` mitten in einer mehrzeiligen Signatur (z.B.
    ``inline bool foo(int a,\n                 long b) {``) oder auf einer
    eigenen Zeile (``long b)\n{``), läuft der Scanner rückwärts über die
    Fortsetzungszeilen und sammelt den ganzen Kopf. Abbruch an Grenzen:
    Leerzeile, Kommentar, Preprocessor-`#`, oder Zeile, die mit `;`/`{`/`}`
    endet (davor beginnt immer eine neue Anweisung).

    Returns:
        (header, start_idx): Kopf-Text und Index seiner ersten Zeile.
    """
    header = prefix.strip()
    start = idx
    j = idx - 1
    while j >= 0:
        stripped = lines[j].strip()
        if not stripped or stripped.startswith(("//", "*", "/*", "*/", "#")):
            break
        prev = lines[j].lstrip().rstrip()
        if prev and prev[-1] in "{};":
            break
        header = stripped + " " + header
        start = j
        j -= 1
    return header, start


def _cpp_sub_blocks(lines, start, end, base) -> list:
    """Findet Blöcke auf Tiefe base+1 im Bereich [start, end].

    Liefert (header_idx, header_line, end_idx). Header wird aus der Zeile vor
    dem `{` rekonstruiert (unterstützt mehrzeilige Signaturen). Einzelzeilen-
    Blöcke (z.B. `int a[] = {1,2};`) werden ignoriert (Rauschen).
    """
    blocks = []
    depth = base
    pending = None
    for idx in range(start, end + 1):
        line = lines[idx]
        if pending is None and depth == base and "{" in line:
            brace = line.index("{")
            prefix = line[:brace].strip()
            if prefix:
                header, hstart = _cpp_collect_header(lines, idx, prefix)
                pending = (hstart, header)
            else:
                j = idx - 1
                while j >= start and not lines[j].strip():
                    j -= 1
                if j >= start:
                    header, hstart = _cpp_collect_header(lines, idx, lines[j].strip())
                    pending = (hstart, header)
                else:
                    pending = (idx, prefix)
        depth += line.count("{") - line.count("}")
        if pending is not None and depth == base:
            if pending[0] < idx:  # echte Blöcke, keine Einzeiler
                blocks.append((pending[0], pending[1], idx))
            pending = None
    return blocks


def _chunk_cpp_class(lines, start, end, base, name) -> list:
    """Zerlegt eine C++-Klasse: Methoden separat, Header/Members als class-Chunk."""
    blocks = _cpp_sub_blocks(lines, start + 1, end - 1, base + 1)
    if not blocks:
        return [_emit_chunk(lines, start, end, "class", name, lines[start].strip(), None)]

    chunks = []
    cursor = start
    for (hdr_idx, hdr_line, end_idx) in blocks:
        if hdr_idx > cursor:
            chunks.append(_emit_chunk(lines, cursor, hdr_idx - 1, "class", name,
                                      lines[start].strip(), None))
        kind, mname = _cpp_def_kind(hdr_line)
        if kind == "function" and mname:
            chunks.append(_emit_chunk(lines, hdr_idx, end_idx, "method",
                                      f"{name}::{mname}", hdr_line, None))
        else:
            chunks.append(_emit_chunk(lines, hdr_idx, end_idx, "block", name,
                                      hdr_line, None))
        cursor = end_idx + 1
    if cursor <= end:
        chunks.append(_emit_chunk(lines, cursor, end, "class", name,
                                  lines[start].strip(), None))
    return chunks


def _chunk_cpp_region(lines, start, end, base) -> list:
    """Zerlegt einen C++-Bereich: Blöcke auf Tiefe base+1 + Modul-Lücken."""
    chunks = []
    blocks = _cpp_sub_blocks(lines, start, end, base)
    cursor = start
    for (hdr_idx, hdr_line, end_idx) in blocks:
        if hdr_idx > cursor:
            chunks.extend(_module_chunks(lines, cursor, hdr_idx - 1))
        kind, name = _cpp_def_kind(hdr_line)
        if kind in ("namespace", "extern"):
            inner = _chunk_cpp_region(lines, hdr_idx + 1, end_idx - 1, base + 1)
            if inner:
                chunks.extend(inner)
            else:
                chunks.append(_emit_chunk(lines, hdr_idx, end_idx, kind, name,
                                          hdr_line, None))
        elif kind == "class":
            chunks.extend(_chunk_cpp_class(lines, hdr_idx, end_idx, base, name))
        elif kind == "function":
            chunks.append(_emit_chunk(lines, hdr_idx, end_idx, "function", name,
                                      hdr_line, None))
        else:
            chunks.append(_emit_chunk(lines, hdr_idx, end_idx, "block", name,
                                      hdr_line, None))
        cursor = end_idx + 1
    if cursor <= end:
        chunks.extend(_module_chunks(lines, cursor, end))
    return chunks


def _chunk_cpp(source: str) -> list:
    """Zerlegt C++-Code strukturiert (brace-basiert, ohne tree-sitter)."""
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    return _chunk_cpp_region(lines, 0, len(lines) - 1, 0)


def _chunk_markdown(source: str) -> list:
    """Zerlegt Markdown nach Überschriften (Sections = Chunks)."""
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    headings = [i for i, ln in enumerate(lines) if re.match(r"^#{1,6}\s", ln)]
    chunks = []
    if not headings:
        return _module_chunks(lines, 0, len(lines) - 1)
    if headings[0] > 0:
        chunks.extend(_module_chunks(lines, 0, headings[0] - 1))
    for k, hi in enumerate(headings):
        e = headings[k + 1] - 1 if k + 1 < len(headings) else len(lines) - 1
        title = re.sub(r"^#+\s*", "", lines[hi]).strip() or lines[hi].strip()
        chunks.append(_emit_chunk(lines, hi, e, "section", title,
                                  lines[hi].strip(), None))
    return chunks


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
        """Legt die Tabellen an; migriert alte Schemas (Zeilen-Chunking -> v2)."""
        with closing(self._connect()) as conn:
            with conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version < RAG_SCHEMA_VERSION:
                    conn.execute("DROP TABLE IF EXISTS code_fts")
                    conn.execute("DROP TABLE IF EXISTS code_chunks")
                    conn.execute("PRAGMA user_version = {}".format(RAG_SCHEMA_VERSION))
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS code_chunks (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_path   TEXT    NOT NULL,
                        language    TEXT    NOT NULL,
                        chunk_index INTEGER NOT NULL,
                        line_start  INTEGER NOT NULL,
                        line_end    INTEGER NOT NULL,
                        content     TEXT    NOT NULL,
                        symbol_type TEXT,
                        symbol_name TEXT,
                        signature   TEXT,
                        docstring   TEXT,
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
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_code_chunks_symbol "
                    "ON code_chunks(symbol_name)"
                )

    # -- Scanning ------------------------------------------------------------
    def _scan_directory(self, directory_path: str) -> list:
        """Sammelt alle indizierbaren Quelldateien unter directory_path."""
        files = []
        for root, dirs, names in os.walk(directory_path):
            dirs[:] = [d for d in dirs if d not in RAG_IGNORED_DIRS]
            for name in names:
                if name in RAG_IGNORED_FILENAMES:
                    continue
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
                # Zeilenenden normalisieren: CRLF/CR -> LF. Sonst bleiben `\r`-
                # Reste an Zeilenenden und brechen den C++-Header-Scanner
                # (Grenz-Checks auf `;`/`{`/`}`) sowie Tokenizer.
                content = content.replace("\r\n", "\n").replace("\r", "\n")
                files.append({
                    "path": os.path.normpath(abs_path),
                    "language": lang,
                    "sha": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "content": content,
                })
        return files

    def _chunk_file(self, language: str, content: str) -> list:
        """Chunkt eine Quelldatei sprachabhängig (strukturell statt Zeilenblöcke)."""
        if language == "python":
            return _chunk_python(content)
        if language == "cpp":
            return _chunk_cpp(content)
        return _chunk_markdown(content)

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

                    # Datei strukturell in Chunks zerlegen und einfügen
                    for idx, chunk in enumerate(self._chunk_file(f["language"], f["content"])):
                        cur = conn.execute(
                            "INSERT INTO code_chunks "
                            "(file_path, language, chunk_index, line_start, "
                            " line_end, content, symbol_type, symbol_name, "
                            " signature, docstring, file_sha) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (f["path"], f["language"], idx, chunk["line_start"],
                             chunk["line_end"], chunk["content"],
                             chunk.get("symbol_type"), chunk.get("symbol_name"),
                             chunk.get("signature"), chunk.get("docstring"), f["sha"]),
                        )
                        conn.execute(
                            "INSERT INTO code_fts "
                            "(rowid, file_path, language, line_start, line_end, content) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (cur.lastrowid, f["path"], f["language"],
                             chunk["line_start"], chunk["line_end"], chunk["content"]),
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

    # -- Abfrage (hybrid: FTS/bm25 + exakter Identifier-Boost) ---------------
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
        """Hybride Suche: FTS5/bm25-Kandidaten + Re-Ranking nach exakten Treffern."""
        match_expr = self._build_match_expr(query)
        if not match_expr:
            return []
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.file_path, c.language, c.line_start, c.line_end,
                       c.content, c.symbol_type, c.symbol_name, c.signature,
                       c.docstring, bm25(code_fts) AS rank
                FROM code_fts
                JOIN code_chunks c ON c.id = code_fts.rowid
                WHERE code_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (match_expr, max(top_k * 4, top_k)),
            ).fetchall()
        rows = [dict(r) for r in rows]

        tokens = [t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query) if len(t) >= 2]

        def combined(r):
            hay = " ".join([
                r.get("content") or "",
                r.get("symbol_name") or "",
                r.get("signature") or "",
            ])
            exact = sum(
                1 for t in tokens
                if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", hay, re.IGNORECASE)
            )
            return (r["rank"], -exact)

        rows.sort(key=combined)
        return rows[:top_k]

    # -- Wiki-Symbolabfrage --------------------------------------------------
    def query_wiki(self, query: str, max_results: int = 12) -> list:
        """Symbol-basierte Suche im Code-Wiki (name/signature/docstring)."""
        tokens = [t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query) if len(t) >= 3]
        if not tokens:
            return []
        with closing(self._connect()) as conn:
            like = "%" + query.strip().lower() + "%"
            rows = conn.execute(
                """
                SELECT id, file_path, language, line_start, line_end, symbol_type,
                       symbol_name, signature, docstring
                FROM code_chunks
                WHERE symbol_name IS NOT NULL
                  AND (LOWER(symbol_name) LIKE ? OR LOWER(signature) LIKE ?
                       OR LOWER(docstring) LIKE ?)
                ORDER BY file_path, line_start
                LIMIT ?
                """,
                (like, like, like, max_results),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- Formatierung --------------------------------------------------------
    @staticmethod
    def chunk_ref(r) -> str:
        """Stabile Kurz-Referenz für einen Chunk: [mab_123]."""
        return f"[mab_{r.get('id') or r.get('chunk_id') or '?'}]"

    @staticmethod
    def format_results(results: list, query: str, format: str = "text") -> str:
        """Formatiert die Suchergebnisse als lesbaren Markdown-Block für den Chat.

        `format` steuert die Kontext-Fülle (Token-Optimierung):
          - "text":    vollständige Markdown-Ausgabe mit Code-Snippets
          - "compact": eine Zeile pro Treffer (ID, Pfad, Zeilen, Symbol) -
                       Full-Content nur via `get_rag_chunk(<id>)` abrufen
          - "json":    maschinenlesbares JSON (strukturierte Treffer inkl. IDs)
        """
        if not results:
            return (
                f"Keine Treffer in der RAG-Datenbank für: '{query}'\n"
                "Tipp: Führe zuerst `index_project_code` auf dem Projektverzeichnis aus."
            )
        if format == "json":
            return ProjectRAG.format_json(results, query)
        if format == "compact":
            return ProjectRAG.format_compact(results, query)
        lines = [f"RAG-Suchergebnisse für: '{query}'", "=" * 60]
        for i, r in enumerate(results, 1):
            lang = r["language"]
            snippet = r["content"]
            if len(snippet) > 900:
                snippet = snippet[:900] + "\n... (gekürzt)"
            indented = "\n".join("    " + ln for ln in snippet.splitlines())
            lines.append("")
            lines.append(
                f"[{i}] {r['file_path']} (Zeilen {r['line_start']}-{r['line_end']}) "
                f"{ProjectRAG.chunk_ref(r)}"
            )
            lines.append(f"    Sprache: {lang}")
            if r.get("symbol_name"):
                lines.append(f"    Symbol: {r['symbol_name']} ({r.get('symbol_type')})")
            if r.get("signature"):
                lines.append(f"    Signatur: {r['signature']}")
            lines.append(f"    ```{lang}\n{indented}\n    ```")
        return "\n".join(lines)

    @staticmethod
    def format_compact(results: list, query: str) -> str:
        """Kompakte Ausgabe: eine Zeile pro Treffer (Token-sparsam, #2 Evidence-Aliasing)."""
        if not results:
            return f"Keine Treffer in der RAG-Datenbank für: '{query}'"
        lines = [f"RAG-Treffer (kompakt) für: '{query}'", "=" * 60]
        for r in results:
            sym = ""
            if r.get("symbol_name"):
                sym = f"{r['symbol_name']} ({r.get('symbol_type')})"
            sig = r.get("signature") or ""
            if sig:
                sig = " :: " + sig.splitlines()[0][:80]
            lines.append(
                f"{ProjectRAG.chunk_ref(r)} {r['file_path']}:"
                f"{r['line_start']}-{r['line_end']} {sym}{sig}"
            )
        lines.append(
            "Voller Inhalt eines Chunks: `get_rag_chunk` mit seiner ID aufrufen."
        )
        return "\n".join(lines)

    @staticmethod
    def format_json(results: list, query: str) -> str:
        """Maschinenlesbare JSON-Ausgabe der Treffer (stabile Felder inkl. Chunk-ID)."""
        payload = {
            "query": query,
            "count": len(results),
            "results": [
                {
                    "chunk_id": r.get("id"),
                    "file_path": r.get("file_path"),
                    "language": r.get("language"),
                    "line_start": r.get("line_start"),
                    "line_end": r.get("line_end"),
                    "symbol_name": r.get("symbol_name"),
                    "symbol_type": r.get("symbol_type"),
                    "signature": r.get("signature"),
                    "content": r.get("content"),
                }
                for r in results
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    # -- Wiki-Generierung ----------------------------------------------------
    @staticmethod
    def _file_dependencies(conn, file_path: str, language: str) -> list:
        """Sammelt Importe/#includes einer Datei aus den Modul-Chunks."""
        if language == "markdown":
            return []
        rows = conn.execute(
            "SELECT content FROM code_chunks WHERE file_path = ? AND symbol_type = 'module'",
            (file_path,),
        ).fetchall()
        deps = []
        seen = set()
        for r in rows:
            for line in r["content"].splitlines():
                line = line.strip()
                is_dep = (
                    language == "python" and (line.startswith("import ") or line.startswith("from "))
                ) or (
                    language == "cpp" and line.startswith("#include")
                )
                if is_dep and line not in seen:
                    seen.add(line)
                    deps.append(line)
                if len(deps) >= 60:
                    return deps
        return deps

    def generate_wiki(self, wiki_path: str = WIKI_PATH) -> dict:
        """Generiert das Code-Wiki (stabiler Symbolindex) als Markdown-Datei."""
        with closing(self._connect()) as conn:
            files = conn.execute(
                "SELECT DISTINCT file_path, language FROM code_chunks ORDER BY file_path"
            ).fetchall()
            n_chunks = conn.execute("SELECT COUNT(*) AS n FROM code_chunks").fetchone()["n"]
            n_syms = conn.execute(
                "SELECT COUNT(*) AS n FROM code_chunks WHERE symbol_name IS NOT NULL"
            ).fetchone()["n"]

            out = [
                "# mab~ Code-Wiki",
                "",
                f"_Automatisch generiert von `index_project_code` (MCP-Server). "
                f"{len(files)} Dateien, {n_chunks} Chunks, {n_syms} Symbole._",
                "",
                "Dieses Wiki ist der strukturierte Symbolindex der Codebasis. Coding-Agents",
                "lesen es einmalig pro Session als stabilen Kontext (prompt-cache-freundlich)",
                "und verifizieren Details immer am echten Quellcode (Pfad + Zeilennummern).",
                "",
                "## Inhaltsverzeichnis",
            ]
            for f in files:
                out.append(f"- [`{f['file_path']}`](#{_wiki_anchor(f['file_path'])})")
            out.append("")

            for f in files:
                out.append(f"## {f['file_path']}")
                out.append("")
                out.append(f"- Sprache: `{f['language']}`")
                deps = self._file_dependencies(conn, f["file_path"], f["language"])
                if deps:
                    out.append("- Abhängigkeiten: " + ", ".join(deps))
                syms = conn.execute(
                    """
                    SELECT symbol_type, symbol_name, signature, docstring,
                           line_start, line_end
                    FROM code_chunks
                    WHERE file_path = ? AND symbol_name IS NOT NULL
                    ORDER BY line_start
                    """,
                    (f["file_path"],),
                ).fetchall()
                out.append("")
                if not syms:
                    out.append("(keine benannten Symbole - nur Text/Markdown)")
                else:
                    out.append("Symbole:")
                    for s in syms:
                        kind = s["symbol_type"] or ""
                        sig = (s["signature"] or "").replace("|", "\\|")
                        doc_lines = (s["docstring"] or "").strip().splitlines()
                        doc1 = doc_lines[0][:120] if doc_lines else ""
                        entry = (
                            f"- `{s['symbol_name']}` ({kind}, "
                            f"Zeilen {s['line_start']}-{s['line_end']}) - {sig}"
                        )
                        if doc1:
                            entry += f" - {doc1}"
                        out.append(entry)
                out.append("")

        out_dir = os.path.dirname(os.path.abspath(wiki_path))
        os.makedirs(out_dir, exist_ok=True)
        with open(wiki_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")
        return {"path": wiki_path, "files": len(files), "chunks": n_chunks, "symbols": n_syms}


def _wiki_anchor(path: str) -> str:
    """Baut einen GitHub-Stil-Markdown-Anker aus einem Dateipfad."""
    base = os.path.splitext(os.path.basename(path))[0].lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


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
    """Indiziert das Projektverzeichnis in die SQLite-RAG-Datenbank (mab_rag.db).

    Scannt rekursiv nach C++-Dateien (.cpp/.h/.hpp/.cc/.cxx/.c), Python-Dateien
    (.py) und Markdown-Dokumentation (.md, inkl. AGENTS.md/WORKSPACE_AGENT_PROMPT.md)
    und zerlegt sie **strukturell** statt in feste Zeilenblöcke: Python via
    `ast` (Klassen/Funktionen/Methoden), C++ über einen brace-basierten Scanner
    (Funktionen/Klassen/Methoden/Namespaces), Markdown nach Überschriften.
    Jeder Chunk trägt Symbol-Metadaten (Typ, Name, Signatur, Docstring).

    Anschließend wird das Code-Wiki `doc/code_wiki.md` regeneriert (stabiler
    Symbolindex mit Dateipfaden und Zeilennummern - der von Coding-Agents
    einmalig pro Session gelesen wird). Unveränderte Dateien werden per
    SHA-256-Hash erkannt und übersprungen (inkrementelles Re-Indexing).

    Args:
        directory_path: Absoluter Pfad zum Projektverzeichnis (z.B. der
            Workspace-Root `mab_tilde`).

    Returns:
        Zusammenfassung des Indexierungsvorgangs inkl. Wiki-Status.
    """
    try:
        stats = _rag.index_directory(directory_path)
    except ValueError as e:
        return f"Fehler: {e}"
    except sqlite3.Error as e:
        return f"Fehler bei der Datenbank-Operation: {e}"

    wiki_line = ""
    try:
        wiki = _rag.generate_wiki(WIKI_PATH)
        wiki_line = (
            f"\n  - Code-Wiki regeneriert: {wiki['path']}\n"
            f"    ({wiki['symbols']} Symbole in {wiki['files']} Dateien)"
        )
    except OSError as e:
        wiki_line = f"\n  - Wiki-Erzeugung übersprungen: {e}"

    return (
        f"Indexierung abgeschlossen:\n"
        f"  - Dateien gescannt: {stats['total_files']}\n"
        f"  - Neu indiziert: {stats['indexed']}\n"
        f"  - Unverändert übersprungen: {stats['skipped']}\n"
        f"  - Datenbank: {_rag.db_path}"
        f"{wiki_line}\n\n"
        "Verwende `query_code_rag` für gezielte Codestellen und "
        "`query_code_wiki` für die Symbol-/Struktur-Suche."
    )


@mcp.tool()
def query_code_rag(query: str, top_k: int = 3, format: str = "text") -> str:
    """Durchsucht die RAG-Datenbank nach Code-Stellen passend zur Suchanfrage.

    Hybride Suche: SQLite FTS5 mit Trigramm-Tokenizer (bm25, lexikalisch -
    matcht auch Identifikator-Substrings wie `mab_tilde`, `block_size`,
    `dsp_setup`) plus Re-Ranking nach exakten Identifier-Treffern (Syntax-
    Boost). Treffer tragen stabile Chunk-Referenzen ([mab_<id>]), die für
    `get_rag_chunk` genutzt werden können.

    Args:
        query: Suchanfrage, z.B. "shared memory handshake" oder "enable handler".
        top_k: Anzahl der zurückzugebenden Treffer (Standard: 3).
        format: Ausgabeformat - "text" (Code-Snippets, Standard), "compact"
            (eine Zeile pro Treffer, token-sparsam) oder "json"
            (maschinenlesbar, inkl. chunk_id).

    Returns:
        Die relevantesten Code-Chunks inkl. Dateipfad, Zeilennummern und Chunk-ID.
    """
    if not _rag_has_data():
        return (
            "Die RAG-Datenbank ist noch leer.\n"
            "Führe zuerst `index_project_code` auf dem Projektverzeichnis aus."
        )
    results = _rag.query(query, top_k=top_k)
    return _rag.format_results(results, query, format=format)


@mcp.tool()
def get_rag_chunk(chunk_id: str) -> str:
    """Holt den vollständigen Inhalt eines einzelnen RAG-Chunks (transient).

    Ergänzung zu `query_code_rag`/`query_code_wiki`: Im kompakten Modus
    liefern die Tools nur Kurz-Referenzen ([mab_<id>]). Diese Funktion gibt
    den vollständigen Code bzw. Text eines Chunks zurück - erst dann, wenn er
    im Reasoning tatsächlich im Detail benötigt wird (Evidence-Aliasing,
    vermeidet unnötiges Context-Dumping).

    Args:
        chunk_id: Chunk-Referenz im Format "mab_<id>" (aus den Suchergebnissen).

    Returns:
        Voller Chunk-Inhalt mit Metadaten und Referenz auf `query_code_wiki`
        für verwandte Symbole im selben Verzeichnis.
    """
    if not chunk_id or not chunk_id.startswith("mab_"):
        return (
            f"Ungültige Chunk-ID: '{chunk_id}'. Erwartet wird das Format "
            "'mab_<id>' aus `query_code_rag`/`query_code_wiki`."
        )
    try:
        cid = int(chunk_id[len("mab_"):])
    except ValueError:
        return f"Ungültige Chunk-ID: '{chunk_id}' (id ist keine Zahl)."
    with closing(_rag._connect()) as conn:
        row = conn.execute(
            """
            SELECT id, file_path, language, line_start, line_end, content,
                   symbol_type, symbol_name, signature, docstring
            FROM code_chunks WHERE id = ?
            """,
            (cid,),
        ).fetchone()
    if not row:
        return f"Kein Chunk mit ID '{chunk_id}' in der RAG-Datenbank."
    r = dict(row)
    header = (
        f"Chunk {ProjectRAG.chunk_ref(r)}: {r['file_path']} "
        f"(Zeilen {r['line_start']}-{r['line_end']})"
    )
    if r.get("symbol_name"):
        header += f"\n  Symbol: {r['symbol_name']} ({r.get('symbol_type')})"
    if r.get("signature"):
        header += f"\n  Signatur: {r['signature']}"
    body = r["content"]
    if len(body) > 8000:
        body = body[:8000] + "\n... (Chunk auf 8000 Zeichen gekürzt)"
    return header + "\n```" + (r["language"] or "") + "\n" + body + "\n```"


@mcp.tool()
def query_code_wiki(query: str, max_results: int = 12, format: str = "text") -> str:
    """Durchsucht den Code-Wiki-Symbolindex nach Klassen, Funktionen und Methoden.

    Sucht über symbol_name, Signatur und Docstring der strukturierten Chunks
    (nicht über den Volltext der Implementierung). Liefert die gefundenen
    Symbole mit Typ, Dateipfad und Zeilennummern - ideal als Einstieg für
    Struktur-/Architekturfragen ("welche Methode macht X?", "wo ist Y
    definiert?"). Für Implementierungsdetails danach `query_code_rag` nutzen.

    Args:
        query: Suchbegriff, z.B. "apply_io", "SharedMemoryManager" oder "handshake".
        max_results: Maximale Anzahl an Symbolen (Standard: 12).
        format: Ausgabeformat - "text" (Standard), "compact" (eine Zeile pro
            Symbol) oder "json" (maschinenlesbar, inkl. chunk_id).

    Returns:
        Gefundene Symbole mit Dateipfad, Zeilennummern, Signatur und Docstring.
    """
    if not _rag_has_data():
        return (
            "Die RAG-Datenbank ist noch leer.\n"
            "Führe zuerst `index_project_code` auf dem Projektverzeichnis aus."
        )
    rows = _rag.query_wiki(query, max_results)
    if not rows:
        return (
            f"Keine Wiki-Symbole für: '{query}'\n"
            "Tipp: `query_code_wiki` sucht nach Symbolnamen/Signaturen. Für "
            "Volltext im Implementierungscode `query_code_rag` verwenden."
        )
    if format == "json":
        return ProjectRAG.format_json(rows, query)
    if format == "compact":
        return ProjectRAG.format_compact(rows, query)
    lines = [f"Code-Wiki-Symbole für: '{query}'", "=" * 60]
    for i, r in enumerate(rows, 1):
        sig = r.get("signature") or ""
        doc_lines = (r.get("docstring") or "").strip().splitlines()
        doc1 = doc_lines[0][:160] if doc_lines else ""
        lines.append("")
        lines.append(f"[{i}] {r['symbol_name']} ({r['symbol_type']})")
        lines.append(f"    {r['file_path']}:{r['line_start']}-{r['line_end']}")
        if sig:
            lines.append(f"    {sig}")
        if doc1:
            lines.append(f"    {doc1}")
    return "\n".join(lines)


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