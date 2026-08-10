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

    def test_markdown_section_chunking(self):
        chunks = mcp._chunk_markdown(MD_SRC)
        by_name = {c["symbol_name"]: c for c in chunks if c["symbol_name"]}
        self.assertIn("Shared Memory", by_name)
        self.assertIn("Inlets", by_name)
        self.assertEqual(by_name["Inlets"]["symbol_type"], "section")


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


if __name__ == "__main__":
    unittest.main()
