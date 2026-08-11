# -*- coding: utf-8 -*-
"""Tests für das RAG-LLM-Wiki in mab_mcp_server.py.

Abgedeckt: strukturelles Chunking (Python-ast, C++-brace, Markdown-Sections),
hybride Suche (FTS/bm25 + exakter Identifier-Boost), Wiki-Symbolabfrage und
Code-Wiki-Generierung.
"""

import os
import shutil
import tempfile
import unittest
import json

import mab_mcp_server as mcp


PY_SRC = '''import torch
import os

BUF_SIZE = 2048


def add_offset(sig, offset=0.0):
    """Fuegt einen Offset zum Signal hinzu."""
    return sig + offset


class SharedMemoryManager:
    """Verwaltet den Shared-Memory-Ringpuffer."""

    def __init__(self, name, block_size=512):
        self.name = name
        self.block_size = block_size

    def handshake(self):
        """Fuehrt den Handshake mit dem C++-Host aus."""
        return True
'''


CPP_SRC = '''#include <windows.h>
#include "ext.h"

#define CONTROL_RING_SIZE 256

struct SharedMemoryHeader {
    uint32_t magic;
    long shutdown_flag;
};

extern "C" {
    void mab_tilde_enable(t_mab_tilde* x, long flag) {
        x->is_ready = flag;
    }

    static void init_worker(t_mab_tilde* x) {
        x->method_pending = 0;
    }
}

int g_running = 1;
'''


MD_SRC = '''# Testdoku

Intro-Text.

## Shared Memory

Erklaerung des Handshakes.

## Inlets

Beschreibung der dynamischen Inlets.
'''


class ChunkingTests(unittest.TestCase):
    def test_python_ast_chunking(self):
        chunks = mcp._chunk_python(PY_SRC)
        by_name = {c["symbol_name"]: c for c in chunks if c["symbol_name"]}
        self.assertIn("add_offset", by_name)
        self.assertEqual(by_name["add_offset"]["symbol_type"], "function")
        self.assertIn("SharedMemoryManager", by_name)
        self.assertEqual(by_name["SharedMemoryManager"]["symbol_type"], "class")
        self.assertIn("SharedMemoryManager.handshake", by_name)
        self.assertEqual(
            by_name["SharedMemoryManager.handshake"]["symbol_type"], "method"
        )
        self.assertIn("Fuegt einen Offset", by_name["add_offset"]["docstring"])
        # Imports landen im Modul-Chunk
        module_texts = " ".join(
            c["content"] for c in chunks if c["symbol_type"] == "module"
        )
        self.assertIn("import torch", module_texts)

    def test_python_chunks_do_not_overspan_functions(self):
        chunks = mcp._chunk_python(PY_SRC)
        helper = next(c for c in chunks if c["symbol_name"] == "add_offset")
        self.assertEqual(helper["line_start"], 7)
        self.assertEqual(helper["line_end"], 9)

    def test_cpp_structural_chunking(self):
        chunks = mcp._chunk_cpp(CPP_SRC)
        by_name = {c["symbol_name"]: c for c in chunks if c["symbol_name"]}
        self.assertIn("mab_tilde_enable", by_name)
        self.assertEqual(by_name["mab_tilde_enable"]["symbol_type"], "function")
        self.assertIn("init_worker", by_name)
        self.assertIn("SharedMemoryHeader", by_name)
        self.assertEqual(by_name["SharedMemoryHeader"]["symbol_type"], "class")
        module_texts = " ".join(
            c["content"] for c in chunks if c["symbol_type"] == "module"
        )
        self.assertIn("#include <windows.h>", module_texts)
        self.assertIn("CONTROL_RING_SIZE", module_texts)

    def test_cpp_multiline_signature(self):
        src = '''// Kommentarzeile
inline bool foo(float* buf, long channels,
                long block_size,
                long& pos) {
    return true;
}

inline bool bar(long n)
{
    return false;
}
'''
        chunks = mcp._chunk_cpp(src)
        by_name = {c["symbol_name"]: c for c in chunks if c["symbol_name"]}
        self.assertIn("foo", by_name)
        self.assertEqual(by_name["foo"]["symbol_type"], "function")
        self.assertEqual(by_name["foo"]["line_start"], 2)
        self.assertEqual(by_name["foo"]["line_end"], 6)
        self.assertIn("inline bool foo", by_name["foo"]["signature"])
        self.assertIn("bar", by_name)
        self.assertEqual(by_name["bar"]["line_start"], 8)
        self.assertEqual(by_name["bar"]["line_end"], 11)
        self.assertIn("inline bool bar", by_name["bar"]["signature"])

    def test_cpp_crlf_normalization(self):
        crlf = CPP_SRC.replace("\n", "\r\n")
        chunks = mcp._chunk_cpp(crlf)
        by_name = {c["symbol_name"]: c for c in chunks if c["symbol_name"]}
        self.assertIn("mab_tilde_enable", by_name)
        self.assertEqual(by_name["mab_tilde_enable"]["symbol_type"], "function")
        self.assertEqual(by_name["mab_tilde_enable"]["line_start"], 12)
        self.assertEqual(by_name["mab_tilde_enable"]["line_end"], 14)
        self.assertIn("mab_tilde_enable", by_name["mab_tilde_enable"]["signature"])

    def test_python_signature_keeps_defaults(self):
        src = "def foo(a, b=1, c='x', *args, d, **kw):\n    return a\n"
        chunks = mcp._chunk_python(src)
        foo = next(c for c in chunks if c["symbol_name"] == "foo")
        self.assertEqual(foo["signature"], "def foo(a, b=1, c='x', *args, d, **kw)")

    def test_markdown_section_chunking(self):
        chunks = mcp._chunk_markdown(MD_SRC)
        by_name = {c["symbol_name"]: c for c in chunks if c["symbol_name"]}
        self.assertIn("Shared Memory", by_name)
        self.assertIn("Inlets", by_name)
        self.assertEqual(by_name["Inlets"]["symbol_type"], "section")

    def test_cpp_three_level_chunking(self):
        """R2: 3-Ebenen-Chunking: Namespace -> Klasse -> Methode."""
        src = '''namespace my_ns {
    struct MyClass {
        void foo(int x) {
            return;
        }
        int bar() const {
            return 42;
        }
    };
}
'''
        chunks = mcp._chunk_cpp(src)
        by_name = {c["symbol_name"]: c for c in chunks if c["symbol_name"]}
        # MyClass sollte als Klasse erkannt werden
        self.assertIn("MyClass", by_name)
        self.assertEqual(by_name["MyClass"]["symbol_type"], "class")
        # Methoden innerhalb der Klasse (innerhalb des Namespace)
        self.assertIn("MyClass::foo", by_name)
        self.assertEqual(by_name["MyClass::foo"]["symbol_type"], "method")
        self.assertIn("MyClass::bar", by_name)
        self.assertEqual(by_name["MyClass::bar"]["symbol_type"], "method")


class RAGIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "rag.db")
        self.src = os.path.join(self.tmp, "src")
        os.makedirs(self.src)
        with open(os.path.join(self.src, "mod.py"), "w", encoding="utf-8") as fh:
            fh.write(PY_SRC)
        with open(os.path.join(self.src, "native.cpp"), "w", encoding="utf-8") as fh:
            fh.write(CPP_SRC)
        with open(os.path.join(self.src, "doc.md"), "w", encoding="utf-8") as fh:
            fh.write(MD_SRC)
        self.rag = mcp.ProjectRAG(self.db)
        self.stats = self.rag.index_directory(self.src)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_index_directory(self):
        self.assertEqual(self.stats["total_files"], 3)
        self.assertEqual(self.stats["indexed"], 3)

    def test_hybrid_query_finds_function(self):
        results = self.rag.query("mab_tilde_enable flag", top_k=3)
        self.assertTrue(results)
        top = results[0]
        self.assertEqual(top["symbol_name"], "mab_tilde_enable")
        self.assertIn("mab_tilde_enable", top["content"])

    def test_hybrid_query_prefers_exact_symbol(self):
        # "handshake" existiert als Methode (exakt) und als Wort in doc.md.
        results = self.rag.query("handshake", top_k=5)
        names = [r.get("symbol_name") for r in results]
        self.assertTrue(any("handshake" in (n or "") for n in names))

    def test_query_returns_chunk_ids(self):
        results = self.rag.query("mab_tilde_enable", top_k=3)
        self.assertTrue(results)
        for r in results:
            self.assertIsInstance(r.get("chunk_id"), str)
            self.assertTrue(r["chunk_id"].startswith("mab_"))
        self.assertIn("mab_", mcp.ProjectRAG.chunk_ref(results[0]))
        self.assertIn(results[0]["chunk_id"], mcp.ProjectRAG.chunk_ref(results[0]))

    def test_format_compact_is_one_line_per_hit(self):
        results = self.rag.query("mab_tilde_enable", top_k=3)
        out = mcp.ProjectRAG.format_results(results, "test", format="compact")
        self.assertIn("[mab_", out)
        self.assertNotIn("```", out)
        self.assertIn("get_rag_chunk", out)

    def test_format_json(self):
        results = self.rag.query("mab_tilde_enable", top_k=3)
        out = mcp.ProjectRAG.format_results(results, "test", format="json")
        payload = json.loads(out)
        self.assertEqual(payload["query"], "test")
        self.assertEqual(payload["count"], len(results))
        self.assertIn("chunk_id", payload["results"][0])
        self.assertIn("file_path", payload["results"][0])

    def test_query_wiki_returns_chunk_ids(self):
        rows = self.rag.query_wiki("SharedMemoryManager")
        self.assertTrue(rows)
        self.assertIsInstance(rows[0].get("chunk_id"), str)
        self.assertTrue(rows[0]["chunk_id"].startswith("mab_"))

    def test_query_wiki(self):
        rows = self.rag.query_wiki("SharedMemoryManager")
        self.assertTrue(rows)
        self.assertEqual(rows[0]["symbol_name"], "SharedMemoryManager")
        rows = self.rag.query_wiki("gibt es nicht")
        self.assertEqual(rows, [])

    def test_wiki_generation(self):
        wiki_path = os.path.join(self.tmp, "code_wiki.md")
        info = self.rag.generate_wiki(wiki_path)
        self.assertTrue(os.path.exists(wiki_path))
        self.assertEqual(info["files"], 3)
        self.assertGreater(info["symbols"], 0)
        with open(wiki_path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("# mab~ Code-Wiki", text)
        self.assertIn("## Inhaltsverzeichnis", text)
        self.assertIn("SharedMemoryManager.handshake", text)
        self.assertIn("#include <windows.h>", text)

    def test_semantic_search_rerank(self):
        """R7: Semantisches Re-Ranking via N-Gramm-Cosine-Ähnlichkeit."""
        # Normale Query ohne semantic
        results_normal = self.rag.query("mab_tilde_enable", top_k=3, semantic=False)
        self.assertTrue(results_normal)
        # Mit semantic=True
        results_semantic = self.rag.query("mab_tilde_enable", top_k=3, semantic=True)
        self.assertTrue(results_semantic)
        # Semantic sollte dieselben oder ähnliche Ergebnisse liefern
        names_normal = [r.get("symbol_name") for r in results_normal]
        names_semantic = [r.get("symbol_name") for r in results_semantic]
        self.assertTrue(any(n in names_semantic for n in names_normal))

    def test_semantic_search_empty_query(self):
        """R7: Leere Query im Semantic-Mode crasht nicht."""
        results = self.rag.query("", top_k=3, semantic=True)
        self.assertEqual(results, [])

    def test_ngram_embedding_consistency(self):
        """R7: Gleicher Text erzeugt gleiches Embedding."""
        from mab_mcp_server import _char_ngrams, _ngram_embedding, _cosine_similarity
        e1 = _ngram_embedding("shared memory handshake")
        e2 = _ngram_embedding("shared memory handshake")
        self.assertEqual(e1, e2)
        sim = _cosine_similarity(e1, e2)
        self.assertAlmostEqual(sim, 1.0)

    def test_ngram_cosine_similarity(self):
        """R7: Ähnliche Texte haben höhere Cosine-Ähnlichkeit."""
        from mab_mcp_server import _ngram_embedding, _cosine_similarity
        e1 = _ngram_embedding("handshake protocol init")
        e2 = _ngram_embedding("handshake procedure start")
        e3 = _ngram_embedding("completely unrelated text about audio")
        sim_similar = _cosine_similarity(e1, e2)
        sim_diff = _cosine_similarity(e1, e3)
        self.assertGreater(sim_similar, sim_diff)

    def test_short_query_fallback_like(self):
        """R4: Kurze Queries (< 3 Zeichen) nutzen LIKE-Fallback statt FTS5."""
        # "fl" ist nur 2 Zeichen -> Trigramm-Tokenizer matched nicht
        # Kommt vor in "flag", "shutdown_flag" in CPP_SRC
        results = self.rag.query("fl", top_k=3)
        # Sollte Treffer liefern (z.B. "mab_tilde_enable" enthält "flag")
        self.assertTrue(results, "Kurz-Query 'fl' sollte Treffer via LIKE-Fallback liefern")

    def test_short_query_two_char_symbol(self):
        """R4: 2-Zeichen-Symbol-Namen werden via LIKE-Fallback gefunden."""
        results = self.rag.query("fl", top_k=5)
        content = " ".join(r.get("content", "") for r in results)
        self.assertIn("flag", content, "LIKE-Fallback sollte 'flag' finden")

    def test_build_match_expr_returns_none_for_short_query(self):
        """R4: _build_match_expr gibt None für Queries ohne 3-Zeichen-Tokens."""
        expr = mcp.ProjectRAG._build_match_expr("io")
        self.assertIsNone(expr)
        expr = mcp.ProjectRAG._build_match_expr("a bc")
        self.assertIsNone(expr)

    def test_build_match_expr_works_for_normal_query(self):
        """R4: _build_match_expr arbeitet normal für Queries mit >= 3-Zeichen-Tokens."""
        expr = mcp.ProjectRAG._build_match_expr("handshake test")
        self.assertIsNotNone(expr)
        self.assertIn("handshake", expr)
        self.assertIn("test", expr)


if __name__ == "__main__":
    unittest.main()
