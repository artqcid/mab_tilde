# mab~ Code-Wiki

_Automatisch generiert von `index_project_code` (MCP-Server). 41 Dateien, 857 Chunks, 568 Symbole._

Dieses Wiki ist der strukturierte Symbolindex der Codebasis. Coding-Agents
lesen es einmalig pro Session als stabilen Kontext (prompt-cache-freundlich)
und verifizieren Details immer am echten Quellcode (Pfad + Zeilennummern).

## Inhaltsverzeichnis
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\AGENTS.md`](#agents)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\MCP_README.md`](#mcp-readme)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\WORKSPACE_AGENT_PROMPT.md`](#workspace-agent-prompt)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\doc\implementation_plan.md`](#implementation-plan)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\doc\nn_tilde_parity.md`](#nn-tilde-parity)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\doc\toolchain.md`](#toolchain)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\inference_worker.py`](#inference-worker)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\mab_mcp_server.py`](#mab-mcp-server)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\block_accumulator.h`](#block-accumulator)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\mab_info.cpp`](#mab-info)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\mab_tilde.cpp`](#mab-tilde)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\max_path_resolve.cpp`](#max-path-resolve)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\max_path_resolve.h`](#max-path-resolve)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\worker_launch.cpp`](#worker-launch)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\worker_launch.h`](#worker-launch)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_anything_handler.cpp`](#test-anything-handler)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_attribute_passthrough.py`](#test-attribute-passthrough)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_block_accumulator.cpp`](#test-block-accumulator)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_block_size_extraction.py`](#test-block-size-extraction)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_crash_monitoring.cpp`](#test-crash-monitoring)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_ext_main.cpp`](#test-ext-main)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_handshake_integration.cpp`](#test-handshake-integration)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_init_worker.cpp`](#test-init-worker)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_init_worker_thread.cpp`](#test-init-worker-thread)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_init_worker_thread_comprehensive.cpp`](#test-init-worker-thread-comprehensive)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_mab_tilde_assist.cpp`](#test-mab-tilde-assist)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_mab_tilde_dsp64.cpp`](#test-mab-tilde-dsp64)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_mab_tilde_free.cpp`](#test-mab-tilde-free)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_mab_tilde_new.cpp`](#test-mab-tilde-new)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_mab_tilde_perform64.cpp`](#test-mab-tilde-perform64)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_message_handlers.cpp`](#test-message-handlers)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_method_layout.py`](#test-method-layout)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_multichannel_layout.cpp`](#test-multichannel-layout)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_python_shared_memory.py`](#test-python-shared-memory)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_query_mode.py`](#test-query-mode)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_rag_wiki.py`](#test-rag-wiki)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_shared_memory_header.cpp`](#test-shared-memory-header)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_shared_memory_header_compatibility.cpp`](#test-shared-memory-header-compatibility)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_shared_memory_management.cpp`](#test-shared-memory-management)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_shared_memory_v2.py`](#test-shared-memory-v2)
- [`C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_worker_launch.cpp`](#test-worker-launch)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\AGENTS.md

- Sprache: `markdown`

Symbole:
- `AGENTS.md – mab_tilde Projekt` (section, Zeilen 1-6) - # AGENTS.md – mab_tilde Projekt
- `Zentrale Anleitung` (section, Zeilen 7-11) - ## Zentrale Anleitung
- `Projekt-Kurzüberblick` (section, Zeilen 12-30) - ## Projekt-Kurzüberblick
- `Kernregeln (Architektur)` (section, Zeilen 31-59) - ## Kernregeln (Architektur)
- `Projektwissen per RAG (MCP)` (section, Zeilen 60-71) - ## Projektwissen per RAG (MCP)
- `Referenz-Code: nn_tilde (Paritäts-Quelle)` (section, Zeilen 72-84) - ## Referenz-Code: nn_tilde (Paritäts-Quelle)
- `Subagent-Rechte (Autopilot)` (section, Zeilen 85-95) - ## Subagent-Rechte (Autopilot)
- `Doku-Pflicht` (section, Zeilen 96-100) - ## Doku-Pflicht

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\MCP_README.md

- Sprache: `markdown`

Symbole:
- `MAB-RAVE MCP Server` (section, Zeilen 1-4) - # MAB-RAVE MCP Server
- `Installation` (section, Zeilen 5-10) - ## Installation
- `Verwendung` (section, Zeilen 11-12) - ## Verwendung
- `Manueller Start` (section, Zeilen 13-18) - ### Manueller Start
- `Über VS Code MCP Integration` (section, Zeilen 19-24) - ### Über VS Code MCP Integration
- `Verfügbare Tools` (section, Zeilen 25-26) - ## Verfügbare Tools
- ``check_max_sdk_headers()`` (section, Zeilen 27-29) - ### `check_max_sdk_headers()`
- ``validate_rave_config(model_path: str)`` (section, Zeilen 30-35) - ### `validate_rave_config(model_path: str)`
- ``run_cpp_tests()`` (section, Zeilen 36-38) - ### `run_cpp_tests()`
- ``check_shared_memory_config()`` (section, Zeilen 39-41) - ### `check_shared_memory_config()`
- ``analyze_inference_worker()`` (section, Zeilen 42-44) - ### `analyze_inference_worker()`
- ``get_project_info()`` (section, Zeilen 45-47) - ### `get_project_info()`
- ``inspect_model_metadata(model_path: str)` ⭐ NEU` (section, Zeilen 48-57) - ### `inspect_model_metadata(model_path: str)` ⭐ NEU
- ``search_max_sdk_docs(query: str)` ⭐ NEU` (section, Zeilen 58-67) - ### `search_max_sdk_docs(query: str)` ⭐ NEU
- ``validate_ipc_sync()` ⭐ NEU` (section, Zeilen 68-75) - ### `validate_ipc_sync()` ⭐ NEU
- `SQLite-RAG-Tools (v3.1) & Code-Wiki` (section, Zeilen 76-84) - ## SQLite-RAG-Tools (v3.1) & Code-Wiki
- `Strukturelles Chunking (statt Zeilenblöcken)` (section, Zeilen 85-93) - ### Strukturelles Chunking (statt Zeilenblöcken)
- ``index_project_code(directory_path: str)`` (section, Zeilen 94-112) - ### `index_project_code(directory_path: str)`
- ``query_code_rag(query: str, top_k: int = 3)`` (section, Zeilen 113-120) - ### `query_code_rag(query: str, top_k: int = 3)`
- ``query_code_wiki(query: str, max_results: int = 12)`` (section, Zeilen 121-128) - ### `query_code_wiki(query: str, max_results: int = 12)`
- ``inspect_rave_model(model_path: str)`` (section, Zeilen 129-134) - ### `inspect_rave_model(model_path: str)`
- `Verpflichtender Workflow für Coding-Agents` (section, Zeilen 135-143) - ### Verpflichtender Workflow für Coding-Agents
- `RAG-Datenbank & Git` (section, Zeilen 144-149) - ### RAG-Datenbank & Git
- `Projektstruktur` (section, Zeilen 150-161) - ## Projektstruktur
- `Shared Memory Handshake-Protokoll` (section, Zeilen 162-165) - ## Shared Memory Handshake-Protokoll
- `Neue Tools (v2.0)` (section, Zeilen 166-167) - ## Neue Tools (v2.0)
- ``inspect_model_metadata(model_path)`` (section, Zeilen 168-174) - ### `inspect_model_metadata(model_path)`
- ``search_max_sdk_docs(query)`` (section, Zeilen 175-180) - ### `search_max_sdk_docs(query)`
- ``validate_ipc_sync()`` (section, Zeilen 181-187) - ### `validate_ipc_sync()`
- `Lizenz` (section, Zeilen 188-190) - ## Lizenz

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\WORKSPACE_AGENT_PROMPT.md

- Sprache: `markdown`

Symbole:
- `Workspace Agent Prompt – Elite C++ (MaxMSP Min-API) & Python (PyTorch, CUDA, Multiprocessing) Developer` (section, Zeilen 1-11) - # Workspace Agent Prompt – Elite C++ (MaxMSP Min-API) & Python (PyTorch, CUDA, Multiprocessing) Developer
- `Project Goal` (section, Zeilen 12-16) - ## Project Goal
- `1. MaxMSP Objects & Syntax Parity to `nn_tilde`` (section, Zeilen 17-18) - ## 1. MaxMSP Objects & Syntax Parity to `nn_tilde`
- ``mab~` (Single Channel / Stream)` (section, Zeilen 19-31) - ### `mab~` (Single Channel / Stream)
- ``mc.mab~` (Multi‑Channel)` (section, Zeilen 32-35) - ### `mc.mab~` (Multi‑Channel)
- ``mcs.mab~` (Batched Multi‑Channel)` (section, Zeilen 36-39) - ### `mcs.mab~` (Batched Multi‑Channel)
- ``mab.info` (Model Inspection)` (section, Zeilen 40-46) - ### `mab.info` (Model Inspection)
- `2. Full Message & Attribute Catalog (1:1 with `nn_tilde`)` (section, Zeilen 47-64) - ## 2. Full Message & Attribute Catalog (1:1 with `nn_tilde`)
- `3. Critical Architecture Requirements` (section, Zeilen 65-66) - ## 3. Critical Architecture Requirements
- `3.1 Asynchronous Background Initialization (Non-Blocking Startup)` (section, Zeilen 67-74) - ### 3.1 Asynchronous Background Initialization (Non-Blocking Startup)
- `3.2 State Management: Bypass, `enable 0`, and DSP Toggling` (section, Zeilen 75-80) - ### 3.2 State Management: Bypass, `enable 0`, and DSP Toggling
- `3.3 Clean Shutdown & Destructor Logic` (section, Zeilen 81-89) - ### 3.3 Clean Shutdown & Destructor Logic
- `3.4 Crash Recovery & Monitoring` (section, Zeilen 90-96) - ### 3.4 Crash Recovery & Monitoring
- `3.5 Real-Time Safety (No OS Locks in Audio Thread)` (section, Zeilen 97-100) - ### 3.5 Real-Time Safety (No OS Locks in Audio Thread)
- `3.6 Shared Memory Handshake & Lifecycle` (section, Zeilen 101-104) - ### 3.6 Shared Memory Handshake & Lifecycle
- `3.7 Multi-Channel Memory Layout (`mc.mab~`)` (section, Zeilen 105-108) - ### 3.7 Multi-Channel Memory Layout (`mc.mab~`)
- `3.8 Real-Time Priority: Worker Must Never Starve the Audio Thread` (section, Zeilen 109-129) - ### 3.8 Real-Time Priority: Worker Must Never Starve the Audio Thread
- `4. Build Instructions (VS Code)` (section, Zeilen 130-131) - ## 4. Build Instructions (VS Code)
- `Prerequisites:` (section, Zeilen 132-136) - ### Prerequisites:
- `Build Architecture (Native Max SDK)` (section, Zeilen 137-144) - ### Build Architecture (Native Max SDK)
- `Build Steps in VS Code:` (section, Zeilen 145-157) - ### Build Steps in VS Code:
- `4.1 Deploy nach Max 9 (Max-Package) + Worker-Pfad-Auflösung` (section, Zeilen 158-164) - ### 4.1 Deploy nach Max 9 (Max-Package) + Worker-Pfad-Auflösung
- `External kopieren (bei jedem Rebuild)` (section, Zeilen 165-166) - # External kopieren (bei jedem Rebuild)
- `Worker-Skript (einmalig nach jeder Änderung an inference_worker.py)` (section, Zeilen 167-168) - # Worker-Skript (einmalig nach jeder Änderung an inference_worker.py)
- `venv-Junction (einmalig; vermeidet GB-Kopie von torch)` (section, Zeilen 169-198) - # venv-Junction (einmalig; vermeidet GB-Kopie von torch)
- `VS Code Tasks:` (section, Zeilen 199-202) - ### VS Code Tasks:
- `Debugging in Max MSP:` (section, Zeilen 203-209) - ### Debugging in Max MSP:
- `Build Troubleshooting:` (section, Zeilen 210-223) - ### Build Troubleshooting:
- `5. Python Environment Setup` (section, Zeilen 224-243) - ## 5. Python Environment Setup
- `6. MCP Server & SQLite-RAG (Projektwissen für Cloud-Codierung)` (section, Zeilen 244-249) - ## 6. MCP Server & SQLite-RAG (Projektwissen für Cloud-Codierung)
- `6.1 RAG-Tools (MCP)` (section, Zeilen 250-267) - ### 6.1 RAG-Tools (MCP)
- `6.2 Regeln für Coding-Agents` (section, Zeilen 268-284) - ### 6.2 Regeln für Coding-Agents
- `6.3 RAG-Datenbank & Code-Wiki` (section, Zeilen 285-304) - ### 6.3 RAG-Datenbank & Code-Wiki
- `7. Required Deliverables` (section, Zeilen 305-330) - ## 7. Required Deliverables

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\doc\implementation_plan.md

- Sprache: `markdown`

Symbole:
- `Implementation Plan & Checklist for mab_tilde Project` (section, Zeilen 1-7) - # Implementation Plan & Checklist for mab_tilde Project
- `1. Overview` (section, Zeilen 8-18) - ## 1. Overview
- `2. First Debug Test Milestone` (section, Zeilen 19-20) - ## 2. First Debug Test Milestone
- `Goal: First successful test in Max MSP` (section, Zeilen 21-23) - ### Goal: First successful test in Max MSP
- `Prerequisites` (section, Zeilen 24-30) - ### Prerequisites
- `Success Criteria for First Test:` (section, Zeilen 31-40) - ### Success Criteria for First Test:
- `Test Procedure:` (section, Zeilen 41-42) - ### Test Procedure:
- `Step 1: Build the External` (section, Zeilen 43-44) - #### Step 1: Build the External
- `Clean build from project root` (section, Zeilen 45-51) - # Clean build from project root
- `Step 2: Verify Unit Tests Pass` (section, Zeilen 52-53) - #### Step 2: Verify Unit Tests Pass
- `Run all C++ unit tests` (section, Zeilen 54-70) - # Run all C++ unit tests
- `Run all Python unit tests` (section, Zeilen 71-76) - # Run all Python unit tests
- `Step 3: Install External in Max` (section, Zeilen 77-90) - #### Step 3: Install External in Max
- `Step 4: Create Test Patch` (section, Zeilen 91-100) - #### Step 4: Create Test Patch
- `Step 5: Verify External Loads` (section, Zeilen 101-108) - #### Step 5: Verify External Loads
- `Step 6: Verify Python Handshake` (section, Zeilen 109-120) - #### Step 6: Verify Python Handshake
- `Step 7: Verify Audio Pass-Through` (section, Zeilen 121-125) - #### Step 7: Verify Audio Pass-Through
- `Step 8: Verify Message Handlers` (section, Zeilen 126-135) - #### Step 8: Verify Message Handlers
- `Step 9: Verify Clean Shutdown` (section, Zeilen 136-141) - #### Step 9: Verify Clean Shutdown
- `Step 10: Verify Crash Recovery` (section, Zeilen 142-153) - #### Step 10: Verify Crash Recovery
- `3. Critical Architecture Requirements` (section, Zeilen 154-155) - ## 3. Critical Architecture Requirements
- `3.1 Asynchronous Background Initialization (Non-Blocking Startup)` (section, Zeilen 156-163) - ### 3.1 Asynchronous Background Initialization (Non-Blocking Startup)
- `3.2 State Management: Bypass, `enable 0`, and DSP Toggling` (section, Zeilen 164-169) - ### 3.2 State Management: Bypass, `enable 0`, and DSP Toggling
- `3.3 Clean Shutdown & Destructor Logic` (section, Zeilen 170-178) - ### 3.3 Clean Shutdown & Destructor Logic
- `3.4 Crash Recovery & Monitoring` (section, Zeilen 179-185) - ### 3.4 Crash Recovery & Monitoring
- `3.5 Real-Time Safety (No OS Locks in Audio Thread)` (section, Zeilen 186-189) - ### 3.5 Real-Time Safety (No OS Locks in Audio Thread)
- `3.6 Shared Memory Handshake & Lifecycle` (section, Zeilen 190-193) - ### 3.6 Shared Memory Handshake & Lifecycle
- `3.7 Multi-Channel Memory Layout (`mc.mab~`)` (section, Zeilen 194-197) - ### 3.7 Multi-Channel Memory Layout (`mc.mab~`)
- `3.8 Method-Aware Inlets/Outlets (`encode`/`decode`/`forward`)` (section, Zeilen 198-201) - ### 3.8 Method-Aware Inlets/Outlets (`encode`/`decode`/`forward`)
- `3.9 Prozess-Isolierte Modell-Inspektion (`mab.info`)` (section, Zeilen 202-207) - ### 3.9 Prozess-Isolierte Modell-Inspektion (`mab.info`)
- `4. Detailed Checklist` (section, Zeilen 208-209) - ## 4. Detailed Checklist
- `Phase 0 – Setup ✅ (COMPLETE)` (section, Zeilen 210-225) - ### Phase 0 – Setup ✅ (COMPLETE)
- `Phase 1 – Core C++ External (with Critical Architecture)` (section, Zeilen 226-227) - ### Phase 1 – Core C++ External (with Critical Architecture)
- `1.1 Object Registration ✅ (COMPLETE)` (section, Zeilen 228-234) - #### 1.1 Object Registration ✅ (COMPLETE)
- `1.2 Asynchronous Initialization ✅ (COMPLETE)` (section, Zeilen 235-245) - #### 1.2 Asynchronous Initialization ✅ (COMPLETE)
- `1.3 Shared Memory Management (Handshake Protocol) ✅ (COMPLETE)` (section, Zeilen 246-264) - #### 1.3 Shared Memory Management (Handshake Protocol) ✅ (COMPLETE)
- `1.4 Multi-Channel Memory Layout ✅ (COMPLETE)` (section, Zeilen 265-270) - #### 1.4 Multi-Channel Memory Layout ✅ (COMPLETE)
- `1.5 Real-Time Safe Synchronization ✅ (COMPLETE)` (section, Zeilen 271-284) - #### 1.5 Real-Time Safe Synchronization ✅ (COMPLETE)
- `1.6 Process Lifecycle ✅ (COMPLETE)` (section, Zeilen 285-291) - #### 1.6 Process Lifecycle ✅ (COMPLETE)
- `1.7 Message Handlers ✅ (COMPLETE)` (section, Zeilen 292-302) - #### 1.7 Message Handlers ✅ (COMPLETE)
- `1.8 Memory Cleanup ✅ (COMPLETE)` (section, Zeilen 303-306) - #### 1.8 Memory Cleanup ✅ (COMPLETE)
- `Phase 2 – Python Backend (with Critical Architecture)` (section, Zeilen 307-308) - ### Phase 2 – Python Backend (with Critical Architecture)
- `2.1 Argument Parsing ✅ (COMPLETE)` (section, Zeilen 309-314) - #### 2.1 Argument Parsing ✅ (COMPLETE)
- `2.2 Shared Memory Creation (Handshake Protocol) ✅ (COMPLETE)` (section, Zeilen 315-321) - #### 2.2 Shared Memory Creation (Handshake Protocol) ✅ (COMPLETE)
- `2.3 Multi-Channel Memory Layout ✅ (COMPLETE)` (section, Zeilen 322-326) - #### 2.3 Multi-Channel Memory Layout ✅ (COMPLETE)
- `2.4 Ring Buffer (Control Messages) ✅ (COMPLETE)` (section, Zeilen 327-330) - #### 2.4 Ring Buffer (Control Messages) ✅ (COMPLETE)
- `2.5 Model Management ✅ (COMPLETE)` (section, Zeilen 331-336) - #### 2.5 Model Management ✅ (COMPLETE)
- `2.6 Inference Loop ✅ (COMPLETE)` (section, Zeilen 337-342) - #### 2.6 Inference Loop ✅ (COMPLETE)
- `2.7 Runtime Attributes ✅ (COMPLETE)` (section, Zeilen 343-347) - #### 2.7 Runtime Attributes ✅ (COMPLETE)
- `2.8 Model Inspection (`dump`) ✅ (COMPLETE)` (section, Zeilen 348-350) - #### 2.8 Model Inspection (`dump`) ✅ (COMPLETE)
- `2.9 Graceful Exit ✅ (COMPLETE)` (section, Zeilen 351-356) - #### 2.9 Graceful Exit ✅ (COMPLETE)
- `Phase 3 – Method-Aware Processing & Latent Inlets (encode/decode/forward)` (section, Zeilen 357-387) - ### Phase 3 – Method-Aware Processing & Latent Inlets (encode/decode/forward)
- `Task 3.1 – Model-Method-Metadaten-Handshake (Python + C++) ✅` (section, Zeilen 388-403) - #### Task 3.1 – Model-Method-Metadaten-Handshake (Python + C++) ✅
- `Task 3.2 – Latent-Buffer & Ratio-Handling (Python) ✅` (section, Zeilen 404-417) - #### Task 3.2 – Latent-Buffer & Ratio-Handling (Python) ✅
- `Task 3.3 – Dynamische Inlets/Outlets (C++, nativer Max-SDK) ✅` (section, Zeilen 418-429) - #### Task 3.3 – Dynamische Inlets/Outlets (C++, nativer Max-SDK) ✅
- `Task 3.4 – Verifikation (in Max, offen)` (section, Zeilen 430-440) - #### Task 3.4 – Verifikation (in Max, offen)
- `Phase 4 – `mab.info` (Modell-Inspektor, analog `nn.info`)` (section, Zeilen 441-448) - ### Phase 4 – `mab.info` (Modell-Inspektor, analog `nn.info`)
- `Design` (section, Zeilen 449-464) - #### Design
- `Tasks` (section, Zeilen 465-476) - #### Tasks
- `Phase 4.5 – Real-Time-Schutz (ASIO-XRun-Prävention) 🟢 FERTIG` (section, Zeilen 477-485) - ### Phase 4.5 – Real-Time-Schutz (ASIO-XRun-Prävention) 🟢 FERTIG
- `Implementiert` (section, Zeilen 486-499) - #### Implementiert
- `Pflicht für Phase 5/6` (section, Zeilen 500-506) - #### Pflicht für Phase 5/6
- `Phase 4.6 – nn_tilde-Paritäts-Delta (Modell-Parameter/Optionen) 🟢 GROSSTEILS FERTIG` (section, Zeilen 507-529) - ### Phase 4.6 – nn_tilde-Paritäts-Delta (Modell-Parameter/Optionen) 🟢 GROSSTEILS FERTIG
- `Phase 5 – `mc.mab~` (Multichannel, analog `mc.nn~`)` (section, Zeilen 530-539) - ### Phase 5 – `mc.mab~` (Multichannel, analog `mc.nn~`)
- `Tasks` (section, Zeilen 540-556) - #### Tasks
- `Phase 6 – `mcs.mab~` (Batched Multichannel, analog `mcs.nn~`)` (section, Zeilen 557-566) - ### Phase 6 – `mcs.mab~` (Batched Multichannel, analog `mcs.nn~`)
- `Tasks` (section, Zeilen 567-578) - #### Tasks
- `5. Success Criteria` (section, Zeilen 579-588) - ## 5. Success Criteria
- `6. Technical Details` (section, Zeilen 589-590) - ## 6. Technical Details
- `6.1 Shared Memory Header Structure (C++/Python)` (section, Zeilen 591-643) - ### 6.1 Shared Memory Header Structure (C++/Python)
- `6.2 Audio Callback (dsp64) - Lock-Free Implementation` (section, Zeilen 644-703) - ### 6.2 Audio Callback (dsp64) - Lock-Free Implementation
- `6.3 Python Initialization Sequence` (section, Zeilen 704-711) - ### 6.3 Python Initialization Sequence
- `6.4 C++ Background Thread Sequence` (section, Zeilen 712-724) - ### 6.4 C++ Background Thread Sequence
- `7. Comparison with nn_tilde` (section, Zeilen 725-726) - ## 7. Comparison with nn_tilde
- `Windows Performance Issues in nn_tilde` (section, Zeilen 727-731) - ### Windows Performance Issues in nn_tilde
- `How mab_tilde Solves These` (section, Zeilen 732-739) - ### How mab_tilde Solves These
- `8. Next Milestone: Phase 1.2/1.3 & Phase 2.1/2.2` (section, Zeilen 740-741) - ## 8. Next Milestone: Phase 1.2/1.3 & Phase 2.1/2.2
- `Goal: Asynchronous Background Initialization & Windows Shared Memory Handshake` (section, Zeilen 742-743) - ### Goal: Asynchronous Background Initialization & Windows Shared Memory Handshake
- `Phase 1.2 – Asynchronous Initialization (C++)` (section, Zeilen 744-759) - ### Phase 1.2 – Asynchronous Initialization (C++)
- `Phase 1.3 – Shared Memory Management (C++)` (section, Zeilen 760-769) - ### Phase 1.3 – Shared Memory Management (C++)
- `Phase 2.1 – Argument Parsing (Python)` (section, Zeilen 770-778) - ### Phase 2.1 – Argument Parsing (Python)
- `Phase 2.2 – Shared Memory Creation (Handshake Protocol)` (section, Zeilen 779-789) - ### Phase 2.2 – Shared Memory Creation (Handshake Protocol)
- `Phase 2.3 – Inference Loop (Python)` (section, Zeilen 790-802) - ### Phase 2.3 – Inference Loop (Python)
- `9. Implementation Order (Recommended)` (section, Zeilen 803-816) - ## 9. Implementation Order (Recommended)
- `10. Current Implementation Status Summary` (section, Zeilen 817-818) - ## 10. Current Implementation Status Summary
- `✅ COMPLETE - All Core Phases Implemented` (section, Zeilen 819-832) - ### ✅ COMPLETE - All Core Phases Implemented
- `⚠️ PARTIALLY COMPLETE - Missing Features` (section, Zeilen 833-844) - ### ⚠️ PARTIALLY COMPLETE - Missing Features
- `🔲 NICHT GESTARTET - Geplante Phasen (dieses Dokument)` (section, Zeilen 845-852) - ### 🔲 NICHT GESTARTET - Geplante Phasen (dieses Dokument)
- `✅ COMPLETE - All Unit Tests` (section, Zeilen 853-875) - ### ✅ COMPLETE - All Unit Tests

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\doc\nn_tilde_parity.md

- Sprache: `markdown`

Symbole:
- `nn_tilde → mab~ Paritäts-Delta (fehlende Modell-Parameter/-Optionen)` (section, Zeilen 1-9) - # nn_tilde → mab~ Paritäts-Delta (fehlende Modell-Parameter/-Optionen)
- `1. Argumente (positionale Objekt-Argumente)` (section, Zeilen 10-25) - ## 1. Argumente (positionale Objekt-Argumente)
- `2. Messages` (section, Zeilen 26-45) - ## 2. Messages
- `3. Attribute (Max-Attribute)` (section, Zeilen 46-56) - ## 3. Attribute (Max-Attribute)
- `4. Modell-Attribute-Passthrough — KRITISCH` (section, Zeilen 57-68) - ## 4. Modell-Attribute-Passthrough — KRITISCH
- `5. Buffer~-Handling` (section, Zeilen 69-76) - ## 5. Buffer~-Handling
- `6. Model-Download (IRCAM Forum API)` (section, Zeilen 77-85) - ## 6. Model-Download (IRCAM Forum API)
- `7. mc./mcs.` (section, Zeilen 86-92) - ## 7. mc./mcs.
- `8. Undokumentierte Optionen (implementiert, nicht in Help/Maxref)` (section, Zeilen 93-103) - ## 8. Undokumentierte Optionen (implementiert, nicht in Help/Maxref)
- `9. Demo-Modell-Attribute (nn_tilde `src/source/*.py`) — Testmodell-Vorlage` (section, Zeilen 104-117) - ## 9. Demo-Modell-Attribute (nn_tilde `src/source/*.py`) — Testmodell-Vorlage
- `Priorisierung (Empfehlung für mab~)` (section, Zeilen 118-125) - ## Priorisierung (Empfehlung für mab~)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\doc\toolchain.md

- Sprache: `markdown`

Symbole:
- `Toolchain & Build System Documentation` (section, Zeilen 1-7) - # Toolchain & Build System Documentation
- `1. Überblick` (section, Zeilen 8-13) - ## 1. Überblick
- `2. Build Tools` (section, Zeilen 14-22) - ## 2. Build Tools
- `Installierte VS 2026 Komponenten` (section, Zeilen 23-29) - ### Installierte VS 2026 Komponenten
- `3. Build-Architektur` (section, Zeilen 30-31) - ## 3. Build-Architektur
- `3.1 Root CMakeLists.txt` (section, Zeilen 32-70) - ### 3.1 Root CMakeLists.txt
- `3.2 SDK-Struktur` (section, Zeilen 71-84) - ### 3.2 SDK-Struktur
- `3.3 Output` (section, Zeilen 85-91) - ### 3.3 Output
- `4. Build-Befehle` (section, Zeilen 92-93) - ## 4. Build-Befehle
- `Clean Build (empfohlen)` (section, Zeilen 94-95) - ### Clean Build (empfohlen)
- `Im Projekt-Root-Verzeichnis ausführen:` (section, Zeilen 96-101) - # Im Projekt-Root-Verzeichnis ausführen:
- `Schnell-Build (nach Konfigurierung)` (section, Zeilen 102-106) - ### Schnell-Build (nach Konfigurierung)
- `Release Build` (section, Zeilen 107-114) - ### Release Build
- `5. Wichtige Max SDK API-Namen (Native)` (section, Zeilen 115-128) - ## 5. Wichtige Max SDK API-Namen (Native)
- `6. Bekannte Probleme & Lösungen` (section, Zeilen 129-130) - ## 6. Bekannte Probleme & Lösungen
- `6.1 LNK1104: c74support.lib nicht gefunden` (section, Zeilen 131-134) - ### 6.1 LNK1104: c74support.lib nicht gefunden
- `6.2 Unknown CMake command "min_project"` (section, Zeilen 135-138) - ### 6.2 Unknown CMake command "min_project"
- `6.3 Compiler-Fehler: CLASS_NOFLOAT nicht definiert` (section, Zeilen 139-142) - ### 6.3 Compiler-Fehler: CLASS_NOFLOAT nicht definiert
- `6.4 std::wstring Konvertierungsfehler` (section, Zeilen 143-146) - ### 6.4 std::wstring Konvertierungsfehler
- `6.5 MSVC 2026 Generator nicht gefunden` (section, Zeilen 147-150) - ### 6.5 MSVC 2026 Generator nicht gefunden
- `6.6 Crash beim Objekt-Instanziieren (std::atomic in C-Struct)` (section, Zeilen 151-154) - ### 6.6 Crash beim Objekt-Instanziieren (std::atomic in C-Struct)
- `6.7 Falscher Einstiegspunkt (main statt ext_main)` (section, Zeilen 155-158) - ### 6.7 Falscher Einstiegspunkt (main statt ext_main)
- `6.8 Symbol nicht exportiert (undefined ext_main)` (section, Zeilen 159-170) - ### 6.8 Symbol nicht exportiert (undefined ext_main)
- `6.9 C++ Name Mangling bei Callbacks` (section, Zeilen 171-183) - ### 6.9 C++ Name Mangling bei Callbacks
- `6.10 Dateiname vs. Klassenname` (section, Zeilen 184-194) - ### 6.10 Dateiname vs. Klassenname
- `6.11 Makro-Neudefinition Warnungen (WIN32_LEAN_AND_MEAN, NOMINMAX)` (section, Zeilen 195-198) - ### 6.11 Makro-Neudefinition Warnungen (WIN32_LEAN_AND_MEAN, NOMINMAX)
- `6.12 Debug-Ausgaben für Instanziierungs-Fehler` (section, Zeilen 199-214) - ### 6.12 Debug-Ausgaben für Instanziierungs-Fehler
- `7. Build-Verifikation` (section, Zeilen 215-230) - ## 7. Build-Verifikation

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\inference_worker.py

- Sprache: `python`
- Abhängigkeiten: import sys, import os, import ctypes, import struct, import time, import threading, import argparse, import traceback, import urllib.request, import urllib.parse, import numpy as np, import torch, from typing import Optional, Tuple

Symbole:
- `SharedMemoryHeader` (class, Zeilen 60-85) - class SharedMemoryHeader(ctypes.Structure) - Header structure that Python creates and C++ reads.
- `ControlRingBuffer` (class, Zeilen 91-97) - class ControlRingBuffer(ctypes.Structure) - Lock-free SPSC ring buffer for control messages.
- `SharedMemoryManager` (class, Zeilen 103-319) - class SharedMemoryManager - Manages shared memory creation and handshake with C++.
- `SharedMemoryManager.__init__` (method, Zeilen 114-177) - def __init__(self, shm_name, ready_event_name, block_size, channels_in, channels_out) - buffers are sized for the MAXIMUM channel counts across all methods,
- `SharedMemoryManager.create` (method, Zeilen 179-245) - def create(self) - Create shared memory and initialize header.
- `SharedMemoryManager.apply_method` (method, Zeilen 247-259) - def apply_method(self, method, method_params) - Publish the active method layout to the header (read by C++).
- `SharedMemoryManager.signal_ready` (method, Zeilen 261-283) - def signal_ready(self) - Signal to C++ that Python is ready.
- `SharedMemoryManager.get_numpy_input` (method, Zeilen 285-297) - def get_numpy_input(self, channels=0) - Get NumPy view of input buffer (zero-copy), sliced to `channels`.
- `SharedMemoryManager.get_numpy_output` (method, Zeilen 299-309) - def get_numpy_output(self, channels=0) - Get NumPy view of output buffer (zero-copy), sliced to `channels`.
- `SharedMemoryManager.cleanup` (method, Zeilen 311-319) - def cleanup(self) - Clean up handles.
- `LockFreeRingBuffer` (class, Zeilen 326-358) - class LockFreeRingBuffer - Lock-free SPSC ring buffer for control messages.
- `LockFreeRingBuffer.__init__` (method, Zeilen 332-336) - def __init__(self, max_items=1024)
- `LockFreeRingBuffer.enqueue` (method, Zeilen 338-348) - def enqueue(self, msg_ptr) - Enqueue a message (called by C++ side).
- `LockFreeRingBuffer.dequeue` (method, Zeilen 350-358) - def dequeue(self) - Dequeue a message (called by Python side).
- `resolve_model_path` (function, Zeilen 365-403) - def resolve_model_path(path, worker_dir=None) - Resolve a model name/path to an absolute file path.
- `load_model` (function, Zeilen 406-416) - def load_model(model_path, use_gpu) - Load a TorchScript model, moving it to CPU or CUDA as requested.
- `extract_block_size` (function, Zeilen 419-466) - def extract_block_size(model) - Extract the expected block size from the model's input shape.
- `get_method_params` (function, Zeilen 469-498) - def get_method_params(model) - Extract {method}_params for every method a TorchScript model exposes.
- `detect_model_type` (function, Zeilen 505-526) - def detect_model_type(model) - Heuristic model-type detection (RAVE / AFTER / MusicNet / ...).
- `get_method_labels` (function, Zeilen 529-539) - def get_method_labels(model, method) - Return ({method}_input_labels, {method}_output_labels) or (None, None).
- `get_method_attributes` (function, Zeilen 542-561) - def get_method_attributes(model, method_params) - Extra values in {method}_params beyond (ci, in_ratio, co, out_ratio).
- `detect_model_attributes` (function, Zeilen 572-596) - def detect_model_attributes(model) - Scan the module for small, readable attributes (bounded values only).
- `collect_model_info` (function, Zeilen 599-619) - def collect_model_info(model, model_path) - Build the metadata dict for a loaded model (no file I/O beyond size).
- `print_info_block` (function, Zeilen 622-648) - def print_info_block(info) - Print the MABJSON line + MAB_INFO block for C++ parsing.
- `query_model` (function, Zeilen 651-685) - def query_model(model_path) - Load a model, print a machine-readable info block to stdout, exit 0.
- `compute_layout` (function, Zeilen 688-703) - def compute_layout(method_params, requested_block_size) - Choose block size and channel maxima from all method layouts.
- `infer_method` (function, Zeilen 706-751) - def infer_method(model, device, method, method_params, input_block) - Run one audio block through the model using nn_tilde semantics.
- `_coerce_value` (function, Zeilen 758-803) - def _coerce_value(raw, current=None) - nn_tilde-style type coercion for attribute values.
- `_read_model_attribute` (function, Zeilen 806-829) - def _read_model_attribute(model, name) - Read a model attribute (TorchScript or Python), bounded for output.
- `_apply_model_attribute` (function, Zeilen 832-874) - def _apply_model_attribute(model, name, value) - Set a model attribute with type coercion (nn_tilde passthrough).
- `_reapply_attributes` (function, Zeilen 877-884) - def _reapply_attributes(model, runtime_attrs) - Re-apply all stored attributes after a model reload / device switch.
- `_list_model_attributes` (function, Zeilen 887-929) - def _list_model_attributes(model, runtime_attrs) - Union of runtime-stored + model-declared attribute names (sorted).
- `RuntimeAttributes` (class, Zeilen 932-953) - class RuntimeAttributes - Container for mutable model attributes (nn_tilde `register_attribute`).
- `RuntimeAttributes.__init__` (method, Zeilen 935-936) - def __init__(self)
- `RuntimeAttributes.set` (method, Zeilen 938-947) - def set(self, name, value, model=None) - Set an attribute: applies it to the model (if present), coerced by
- `RuntimeAttributes.get` (method, Zeilen 949-953) - def get(self, name, model=None) - Get an attribute value (runtime cache first, then the model).
- `_models_dir` (function, Zeilen 956-960) - def _models_dir(worker_dir=None) - Directory used for model download / delete (the package `models` dir).
- `list_local_models` (function, Zeilen 963-981) - def list_local_models(worker_dir=None) - Map <filename> -> abs path of every .ts found in the known model dirs.
- `_remote_available_models` (function, Zeilen 984-1002) - def _remote_available_models() - Best-effort list of downloadable model cards from the IRCAM API.
- `download_model` (function, Zeilen 1005-1029) - def download_model(card, name=None, worker_dir=None) - Download a model card from the IRCAM API into the package models dir.
- `delete_model` (function, Zeilen 1032-1048) - def delete_model(card, worker_dir=None) - Delete a local .ts model (only within the known model directories).
- `dump_model_info` (function, Zeilen 1051-1078) - def dump_model_info(model_path, method, device, attrs, model=None, method_params=None) - Print model information to stdout (captured by Max).
- `_limit_inference_threads` (function, Zeilen 1085-1104) - def _limit_inference_threads(cores) - Begrenzt die PyTorch-Inference-Threads (NUR im CPU-Modus relevant).
- `_load_and_configure` (function, Zeilen 1107-1119) - def _load_and_configure(model_path, use_gpu, active_method, method_params, attrs, shm) - Load a model, re-validate the method, publish the layout and re-apply
- `main` (function, Zeilen 1122-1415) - def main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\mab_mcp_server.py

- Sprache: `python`
- Abhängigkeiten: from fastmcp import FastMCP, import subprocess, import os, import sys, import re, import ast, import json, import hashlib, import sqlite3, from contextlib import closing

Symbole:
- `_emit_chunk` (function, Zeilen 102-112) - def _emit_chunk(lines, start, end, symbol_type, symbol_name, signature, docstring) - Baut einen Chunk-Datensatz aus 0-basiertem Zeilenbereich [start, end].
- `_module_chunks` (function, Zeilen 115-125) - def _module_chunks(lines, start, end) - Zerlegt einen Bereich ohne benannte Symbole in max. 60-Zeilen-Blöcke.
- `_py_arglist` (function, Zeilen 128-147) - def _py_arglist(args) - Baut aus einem ast.arguments eine kompakte Parameterliste (mit Defaults).
- `_py_bases` (function, Zeilen 150-159) - def _py_bases(node)
- `_chunk_python` (function, Zeilen 162-214) - def _chunk_python(source) - Zerlegt Python-Code über das stdlib-`ast` in Klassen/Funktionen/Methoden.
- `_cpp_def_kind` (function, Zeilen 222-246) - def _cpp_def_kind(header) - Klassifiziert einen C++-Block-Kopf -> (kind, name).
- `_cpp_collect_header` (function, Zeilen 249-275) - def _cpp_collect_header(lines, idx, prefix) - Rekonstruiert den vollständigen Block-Kopf (mehrzeilige Signaturen).
- `_cpp_sub_blocks` (function, Zeilen 278-310) - def _cpp_sub_blocks(lines, start, end, base) - Findet Blöcke auf Tiefe base+1 im Bereich [start, end].
- `_chunk_cpp_class` (function, Zeilen 313-336) - def _chunk_cpp_class(lines, start, end, base, name) - Zerlegt eine C++-Klasse: Methoden separat, Header/Members als class-Chunk.
- `_chunk_cpp_region` (function, Zeilen 339-366) - def _chunk_cpp_region(lines, start, end, base) - Zerlegt einen C++-Bereich: Blöcke auf Tiefe base+1 + Modul-Lücken.
- `_chunk_cpp` (function, Zeilen 369-373) - def _chunk_cpp(source) - Zerlegt C++-Code strukturiert (brace-basiert, ohne tree-sitter).
- `_chunk_markdown` (function, Zeilen 376-391) - def _chunk_markdown(source) - Zerlegt Markdown nach Überschriften (Sections = Chunks).
- `ProjectRAG` (class, Zeilen 394-839) - class ProjectRAG - Verwaltet die lokale SQLite-FTS5-Datenbank für den Code-Retrieval.
- `ProjectRAG.__init__` (method, Zeilen 397-399) - def __init__(self, db_path=RAG_DB_PATH)
- `ProjectRAG._connect` (method, Zeilen 402-408) - def _connect(self) - Öffnet eine frische Verbindung (thread-sicher für parallele MCP-Aufrufe).
- `ProjectRAG._init_schema` (method, Zeilen 411-457) - def _init_schema(self) - Legt die Tabellen an; migriert alte Schemas (Zeilen-Chunking -> v2).
- `ProjectRAG._scan_directory` (method, Zeilen 460-494) - def _scan_directory(self, directory_path) - Sammelt alle indizierbaren Quelldateien unter directory_path.
- `ProjectRAG._chunk_file` (method, Zeilen 496-502) - def _chunk_file(self, language, content) - Chunkt eine Quelldatei sprachabhängig (strukturell statt Zeilenblöcke).
- `ProjectRAG.index_directory` (method, Zeilen 505-560) - def index_directory(self, directory_path) - Indiziert (bzw. aktualisiert inkrementell) alle Code-Dateien.
- `ProjectRAG._find_stale_paths` (method, Zeilen 563-579) - def _find_stale_paths(conn, directory_path, scanned_paths) - Findet indizierte Pfade unter directory_path, die nicht mehr existieren.
- `ProjectRAG._build_match_expr` (method, Zeilen 583-592) - def _build_match_expr(query) - Baut aus der Suchanfrage einen sicheren FTS5-MATCH-Ausdruck.
- `ProjectRAG.query` (method, Zeilen 594-630) - def query(self, query, top_k=3) - Hybride Suche: FTS5/bm25-Kandidaten + Re-Ranking nach exakten Treffern.
- `ProjectRAG.query_wiki` (method, Zeilen 633-653) - def query_wiki(self, query, max_results=12) - Symbol-basierte Suche im Code-Wiki (name/signature/docstring).
- `ProjectRAG.chunk_ref` (method, Zeilen 657-659) - def chunk_ref(r) - Stabile Kurz-Referenz für einen Chunk: [mab_123].
- `ProjectRAG.format_results` (method, Zeilen 662-698) - def format_results(results, query, format='text') - Formatiert die Suchergebnisse als lesbaren Markdown-Block für den Chat.
- `ProjectRAG.format_compact` (method, Zeilen 701-720) - def format_compact(results, query) - Kompakte Ausgabe: eine Zeile pro Treffer (Token-sparsam, #2 Evidence-Aliasing).
- `ProjectRAG.format_json` (method, Zeilen 723-743) - def format_json(results, query) - Maschinenlesbare JSON-Ausgabe der Treffer (stabile Felder inkl. Chunk-ID).
- `ProjectRAG._file_dependencies` (method, Zeilen 747-770) - def _file_dependencies(conn, file_path, language) - Sammelt Importe/#includes einer Datei aus den Modul-Chunks.
- `ProjectRAG.generate_wiki` (method, Zeilen 772-839) - def generate_wiki(self, wiki_path=WIKI_PATH) - Generiert das Code-Wiki (stabiler Symbolindex) als Markdown-Datei.
- `_wiki_anchor` (function, Zeilen 842-845) - def _wiki_anchor(path) - Baut einen GitHub-Stil-Markdown-Anker aus einem Dateipfad.
- `check_max_sdk_headers` (function, Zeilen 853-874) - def check_max_sdk_headers() - Durchsucht das Projekt nach typischen Max/MSP API Headern und prüft die Einbindung.
- `validate_rave_config` (function, Zeilen 878-939) - def validate_rave_config(model_path) - Überprüft ein RAVE ONNX/Torch-Modell auf Kompatibilität mit dem C++ Worker.
- `run_cpp_tests` (function, Zeilen 943-973) - def run_cpp_tests() - Führt lokale Tests oder den Build-Prozess für das mab~ External aus.
- `check_shared_memory_config` (function, Zeilen 977-1010) - def check_shared_memory_config() - Prüft die Shared Memory-Konfiguration zwischen C++ und Python.
- `analyze_inference_worker` (function, Zeilen 1014-1053) - def analyze_inference_worker() - Analysiert den inference_worker.py und gibt Strukturinformationen zurück.
- `get_project_info` (function, Zeilen 1057-1092) - def get_project_info() - Gibt allgemeine Informationen über das mab~ Projekt zurück.
- `inspect_model_metadata` (function, Zeilen 1096-1243) - def inspect_model_metadata(model_path) - Lädt ein ONNX- oder TorchScript-Modell (RAVE) und extrahiert automatisch
- `search_max_sdk_docs` (function, Zeilen 1247-1355) - def search_max_sdk_docs(query) - Durchsucht lokale Markdown-Notizen oder Header-Dateien des Max SDK
- `validate_ipc_sync` (function, Zeilen 1359-1519) - def validate_ipc_sync() - Analysiert statisch den C++ Code (mab_tilde.cpp) und das Python-Worker-Skript,
- `index_project_code` (function, Zeilen 1528-1576) - def index_project_code(directory_path) - Indiziert das Projektverzeichnis in die SQLite-RAG-Datenbank (mab_rag.db).
- `query_code_rag` (function, Zeilen 1580-1605) - def query_code_rag(query, top_k=3, format='text') - Durchsucht die RAG-Datenbank nach Code-Stellen passend zur Suchanfrage.
- `get_rag_chunk` (function, Zeilen 1609-1657) - def get_rag_chunk(chunk_id) - Holt den vollständigen Inhalt eines einzelnen RAG-Chunks (transient).
- `query_code_wiki` (function, Zeilen 1661-1707) - def query_code_wiki(query, max_results=12, format='text') - Durchsucht den Code-Wiki-Symbolindex nach Klassen, Funktionen und Methoden.
- `_rag_has_data` (function, Zeilen 1710-1717) - def _rag_has_data() - Prüft, ob die RAG-Datenbank bereits Code-Chunks enthält.
- `inspect_rave_model` (function, Zeilen 1725-1759) - def inspect_rave_model(model_path) - Analysiert ein RAVE/ONNX/TorchScript-Modell auf seine Ein-/Ausgangsstruktur.
- `_analyze_onnx_rave` (function, Zeilen 1762-1791) - def _analyze_onnx_rave(model_path) - Analysiert ein ONNX-Modell via onnxruntime (falls installiert).
- `_analyze_ts_rave` (function, Zeilen 1794-1834) - def _analyze_ts_rave(model_path) - Analysiert ein TorchScript-Modell via torch (falls installiert).
- `_rave_integration_hint` (function, Zeilen 1837-1844) - def _rave_integration_hint() - Empfehlung zur block_size-Abstimmung für den mab~-Ringbuffer.

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\block_accumulator.h

- Sprache: `cpp`

Symbole:
- `block_accumulate_write` (function, Zeilen 19-38) - inline bool block_accumulate_write(float* buffer, long channels, long block_size, long n, const double* const* ins, long numins, long& pos)
- `block_accumulate_read` (function, Zeilen 45-73) - inline bool block_accumulate_read(float* buffer, long channels, long block_size, long n, double** outs, long numouts, long& pos)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\mab_info.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <windows.h>, #include <thread>, #include <string>, #include <cstring>, #include <cstdio>, #include "ext.h", #include "ext_obex.h", #include "ext_dictionary.h", #include "ext_dictobj.h", #include "max_path_resolve.h", #include "worker_launch.h"

Symbole:
- `mab_info_query_thread` (function, Zeilen 57-113) - static void mab_info_query_thread(t_mab_info* x)
- `mab_info_make_dict` (function, Zeilen 119-140) - static void mab_info_make_dict(t_mab_info* x, t_dictionary** out_dict)
- `mab_info_out_dict` (function, Zeilen 142-146) - static void mab_info_out_dict(t_mab_info* x, t_dictionary* d)
- `mab_info_apply` (function, Zeilen 152-174) - static void mab_info_apply(t_mab_info* x)
- `mab_info_start_query` (function, Zeilen 180-192) - static void mab_info_start_query(t_mab_info* x)
- `mab_info_set` (function, Zeilen 194-205) - static void mab_info_set(t_mab_info* x, t_symbol* s, long argc, t_atom* argv)
- `mab_info_path` (function, Zeilen 207-213) - static void mab_info_path(t_mab_info* x, t_symbol* s, long argc, t_atom* argv)
- `mab_info_bang` (function, Zeilen 215-223) - static void mab_info_bang(t_mab_info* x)
- `mab_info_dump` (function, Zeilen 225-248) - static void mab_info_dump(t_mab_info* x)
- `mab_info_methods` (function, Zeilen 250-252) - static void mab_info_methods(t_mab_info* x)
- `mab_info_attributes` (function, Zeilen 254-257) - static void mab_info_attributes(t_mab_info* x)
- `mab_info_parameters` (function, Zeilen 259-270) - static void mab_info_parameters(t_mab_info* x, t_symbol* s, long argc, t_atom* argv)
- `mab_info_dump_dict` (function, Zeilen 272-276) - static void mab_info_dump_dict(t_mab_info* x)
- `mab_info_dict` (function, Zeilen 278-285) - static void mab_info_dict(t_mab_info* x, t_symbol* name)
- `mab_info_new` (function, Zeilen 291-317) - static void* mab_info_new(t_symbol* s, long argc, t_atom* argv)
- `mab_info_free` (function, Zeilen 319-330) - static void mab_info_free(t_mab_info* x)
- `mab_info_assist` (function, Zeilen 332-344) - static void mab_info_assist(t_mab_info* x, void* b, long m, long a, char* s)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\mab_tilde.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <windows.h>, #include <thread>, #include <atomic>, #include <process.h>, #include <string>, #include <cstring>, #include <cstdio>, #include "ext.h", #include "ext_obex.h", #include "z_dsp.h", #include "block_accumulator.h", #include "max_path_resolve.h", #include "worker_launch.h"

Symbole:
- `ControlRingBuffer` (class, Zeilen 24-28) - struct ControlRingBuffer {
- `SharedMemoryHeader` (class, Zeilen 33-51) - struct SharedMemoryHeader {
- `ext_main` (function, Zeilen 139-167) - void ext_main(void* r)
- `mab_tilde_new` (function, Zeilen 169-282) - void* mab_tilde_new(t_symbol* s, long argc, t_atom* argv)
- `mab_tilde_free` (function, Zeilen 284-331) - void mab_tilde_free(t_mab_tilde* x)
- `mab_tilde_assist` (function, Zeilen 333-355) - void mab_tilde_assist(t_mab_tilde* x, void* b, long m, long a, char* s)
- `mab_tilde_dsp64` (function, Zeilen 357-359) - void mab_tilde_dsp64(t_mab_tilde* x, t_object* dsp64, short* count, double samplerate, long maxvectorsize, long flags)
- `mab_tilde_perform64` (function, Zeilen 361-461) - void mab_tilde_perform64(t_mab_tilde* x, t_object* dsp64, double** ins, long numins, double** outs, long numouts, long sampleframes, long flags, void* userparam)
- `mab_tilde_apply_io` (function, Zeilen 466-518) - void mab_tilde_apply_io(t_mab_tilde* x)
- `init_worker_thread` (function, Zeilen 601-603) - void init_worker_thread(t_mab_tilde* x)
- `mab_enqueue_control` (function, Zeilen 612-629) - static bool mab_enqueue_control(t_mab_tilde* x, const char* msg)
- `mab_tilde_enable` (function, Zeilen 631-639) - void mab_tilde_enable(t_mab_tilde* x, long flag)
- `mab_tilde_gpu` (function, Zeilen 641-652) - void mab_tilde_gpu(t_mab_tilde* x, long flag)
- `mab_tilde_reload` (function, Zeilen 654-723) - void mab_tilde_reload(t_mab_tilde* x, t_symbol* s)
- `mab_tilde_dump` (function, Zeilen 725-748) - void mab_tilde_dump(t_mab_tilde* x)
- `mab_tilde_set` (function, Zeilen 750-794) - void mab_tilde_set(t_mab_tilde* x, t_symbol* s, long argc, t_atom* argv)
- `mab_tilde_get` (function, Zeilen 796-822) - void mab_tilde_get(t_mab_tilde* x, t_symbol* s)
- `mab_tilde_method` (function, Zeilen 824-838) - void mab_tilde_method(t_mab_tilde* x, t_symbol* s, long argc, t_atom* argv)
- `mab_tilde_load` (function, Zeilen 840-851) - void mab_tilde_load(t_mab_tilde* x, t_symbol* s)
- `mab_tilde_anything` (function, Zeilen 854-885) - void mab_tilde_anything(t_mab_tilde* x, t_symbol* s, long argc, t_atom* argv)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\max_path_resolve.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include "max_path_resolve.h", #include <cstdio>, #include <cstring>, #include "ext.h", #include "ext_obex.h", #include "ext_path.h", #include <windows.h>

Symbole:
- `path_is_file` (function, Zeilen 20-25) - static bool path_is_file(const char* path)
- `try_max_resolve` (function, Zeilen 27-40) - static bool try_max_resolve(const char* name, char* out, size_t out_size)
- `mab_resolve_model_path` (function, Zeilen 42-67) - bool mab_resolve_model_path(const char* name, char* out, size_t out_size)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\max_path_resolve.h

- Sprache: `cpp`
- Abhängigkeiten: #include <cstddef>

(keine benannten Symbole - nur Text/Markdown)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\worker_launch.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include "worker_launch.h", #include <cstdio>, #include <cstring>, #include <string>

Symbole:
- `worker_parse_info_block` (function, Zeilen 60-125) - bool worker_parse_info_block(const char* text, WorkerModelInfo* info)
- `worker_resolve_project_dir` (function, Zeilen 127-139) - bool worker_resolve_project_dir(wchar_t* out, size_t out_size)
- `worker_find_venv_python` (function, Zeilen 141-155) - bool worker_find_venv_python(const wchar_t* project_dir, wchar_t* out, size_t out_size)
- `worker_launch` (function, Zeilen 157-266) - void worker_launch(const char* arg_string, bool capture_stdout, WorkerProcess* out)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\source\projects\mab_tilde\worker_launch.h

- Sprache: `cpp`
- Abhängigkeiten: #include <windows.h>, #include <cstddef>

Symbole:
- `WorkerProcess` (class, Zeilen 18-21) - struct WorkerProcess {
- `WorkerModelInfo` (class, Zeilen 24-37) - struct WorkerModelInfo {

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_anything_handler.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <cstdint>, #include <cstring>

Symbole:
- `_mab_tilde` (class, Zeilen 14-24) - struct _mab_tilde {
- `main` (function, Zeilen 31-58) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_attribute_passthrough.py

- Sprache: `python`
- Abhängigkeiten: import os, import sys, import tempfile, import unittest, from unittest import mock, import torch, from inference_worker import (

Symbole:
- `RealMod` (class, Zeilen 38-50) - class RealMod(torch.nn.Module) - A torch.nn.Module that becomes a real ScriptModule (with `_c`) when
- `RealMod.__init__` (method, Zeilen 42-47) - def __init__(self)
- `RealMod.forward` (method, Zeilen 49-50) - def forward(self, x)
- `scripted` (function, Zeilen 53-54) - def scripted()
- `TestCoerceValue` (class, Zeilen 57-83) - class TestCoerceValue(unittest.TestCase)
- `TestCoerceValue.test_bool_literals` (method, Zeilen 58-62) - def test_bool_literals(self)
- `TestCoerceValue.test_int_float_str_fallback` (method, Zeilen 64-68) - def test_int_float_str_fallback(self)
- `TestCoerceValue.test_typed_float` (method, Zeilen 70-72) - def test_typed_float(self)
- `TestCoerceValue.test_typed_int` (method, Zeilen 74-76) - def test_typed_int(self)
- `TestCoerceValue.test_typed_bool` (method, Zeilen 78-80) - def test_typed_bool(self)
- `TestCoerceValue.test_typed_str_untouched` (method, Zeilen 82-83) - def test_typed_str_untouched(self)
- `TestApplyModelAttribute` (class, Zeilen 86-125) - class TestApplyModelAttribute(unittest.TestCase)
- `TestApplyModelAttribute.setUp` (method, Zeilen 87-88) - def setUp(self)
- `TestApplyModelAttribute.test_float_attr` (method, Zeilen 90-95) - def test_float_attr(self)
- `TestApplyModelAttribute.test_int_attr` (method, Zeilen 97-101) - def test_int_attr(self)
- `TestApplyModelAttribute.test_bool_attr` (method, Zeilen 103-107) - def test_bool_attr(self)
- `TestApplyModelAttribute.test_unknown_attr_fails_on_scriptmodule` (method, Zeilen 109-112) - def test_unknown_attr_fails_on_scriptmodule(self)
- `TestApplyModelAttribute.test_unknown_attr_does_not_raise_on_plain_object` (method, Zeilen 114-121) - def test_unknown_attr_does_not_raise_on_plain_object(self)
- `TestApplyModelAttribute.test_no_model` (method, Zeilen 123-125) - def test_no_model(self)
- `TestReadListReapply` (class, Zeilen 128-152) - class TestReadListReapply(unittest.TestCase)
- `TestReadListReapply.setUp` (method, Zeilen 129-131) - def setUp(self)
- `TestReadListReapply.test_read_model_attribute` (method, Zeilen 133-135) - def test_read_model_attribute(self)
- `TestReadListReapply.test_list_model_attributes` (method, Zeilen 137-144) - def test_list_model_attributes(self)
- `TestReadListReapply.test_reapply` (method, Zeilen 146-152) - def test_reapply(self)
- `TestRuntimeAttributes` (class, Zeilen 155-171) - class TestRuntimeAttributes(unittest.TestCase)
- `TestRuntimeAttributes.test_set_get_cached` (method, Zeilen 156-159) - def test_set_get_cached(self)
- `TestRuntimeAttributes.test_get_falls_back_to_model` (method, Zeilen 161-163) - def test_get_falls_back_to_model(self)
- `TestRuntimeAttributes.test_apply_to_model_stores_coerced` (method, Zeilen 165-171) - def test_apply_to_model_stores_coerced(self)
- `TestLocalModels` (class, Zeilen 174-202) - class TestLocalModels(unittest.TestCase)
- `TestLocalModels.setUp` (method, Zeilen 175-185) - def setUp(self)
- `TestLocalModels.tearDown` (method, Zeilen 187-188) - def tearDown(self)
- `TestLocalModels.test_list_local_models_finds_package_models` (method, Zeilen 190-193) - def test_list_local_models_finds_package_models(self)
- `TestLocalModels.test_delete_model_removes_file` (method, Zeilen 195-198) - def test_delete_model_removes_file(self)
- `TestLocalModels.test_delete_unknown` (method, Zeilen 200-202) - def test_delete_unknown(self)
- `TestDownloadModel` (class, Zeilen 205-238) - class TestDownloadModel(unittest.TestCase)
- `TestDownloadModel.test_download_uses_api_and_writes_file` (method, Zeilen 206-228) - def test_download_uses_api_and_writes_file(self)
- `TestDownloadModel.test_download_reports_network_failure` (method, Zeilen 230-238) - def test_download_reports_network_failure(self)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_block_accumulator.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <cstdio>, #include <cassert>, #include <cstring>, #include <cstdint>, #include <vector>, #include "../source/projects/mab_tilde/block_accumulator.h"

Symbole:
- `test_accumulate_across_ticks` (function, Zeilen 19-37) - static void test_accumulate_across_ticks()
- `test_write_truncates_at_boundary` (function, Zeilen 40-58) - static void test_write_truncates_at_boundary()
- `test_multichannel_write_read` (function, Zeilen 61-96) - static void test_multichannel_write_read()
- `test_read_silences_stale_tail` (function, Zeilen 100-119) - static void test_read_silences_stale_tail()
- `test_missing_outlets_skipped` (function, Zeilen 122-134) - static void test_missing_outlets_skipped()
- `test_missing_inlets_zero_filled` (function, Zeilen 137-150) - static void test_missing_inlets_zero_filled()
- `main` (function, Zeilen 152-163) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_block_size_extraction.py

- Sprache: `python`
- Abhängigkeiten: import unittest, import sys, import os, from inference_worker import extract_block_size, MAGIC_NUMBER, SharedMemoryHeader

Symbole:
- `TestExtractBlockSize` (class, Zeilen 23-46) - class TestExtractBlockSize(unittest.TestCase) - Test the extract_block_size function.
- `TestExtractBlockSize.test_returns_zero_for_none` (method, Zeilen 26-29) - def test_returns_zero_for_none(self) - Test that extract_block_size returns 0 for None model.
- `TestExtractBlockSize.test_returns_zero_for_object_without_graph` (method, Zeilen 31-37) - def test_returns_zero_for_object_without_graph(self) - Test that extract_block_size returns 0 for objects without graph.
- `TestExtractBlockSize.test_returns_zero_for_object_without_parameters` (method, Zeilen 39-46) - def test_returns_zero_for_object_without_parameters(self) - Test that extract_block_size returns 0 for objects without parameters.
- `TestMagicNumber` (class, Zeilen 49-58) - class TestMagicNumber(unittest.TestCase) - Test the magic number constant.
- `TestMagicNumber.test_magic_number_value` (method, Zeilen 52-54) - def test_magic_number_value(self) - Test that magic number is correct.
- `TestMagicNumber.test_magic_number_hex` (method, Zeilen 56-58) - def test_magic_number_hex(self) - Test that magic number hex representation is correct.
- `TestSharedMemoryHeaderPython` (class, Zeilen 61-110) - class TestSharedMemoryHeaderPython(unittest.TestCase) - Test the Python SharedMemoryHeader structure (v2).
- `TestSharedMemoryHeaderPython.test_header_has_control_offset` (method, Zeilen 64-68) - def test_header_has_control_offset(self) - Test that the header has a control_offset field.
- `TestSharedMemoryHeaderPython.test_header_field_count` (method, Zeilen 70-77) - def test_header_field_count(self) - Test that the header has the correct number of fields.
- `TestSharedMemoryHeaderPython.test_header_has_method_fields` (method, Zeilen 79-85) - def test_header_has_method_fields(self) - Test that the header exposes the method-aware fields.
- `TestSharedMemoryHeaderPython.test_header_size` (method, Zeilen 87-90) - def test_header_size(self) - Test that the header size matches C++ (128 bytes).
- `TestSharedMemoryHeaderPython.test_header_offsets_match_cpp` (method, Zeilen 92-110) - def test_header_offsets_match_cpp(self) - Test that field offsets match the C++ layout.
- `TestControlRingBuffer` (class, Zeilen 113-129) - class TestControlRingBuffer(unittest.TestCase) - Test the ControlRingBuffer structure.
- `TestControlRingBuffer.test_control_ring_buffer_exists` (method, Zeilen 116-119) - def test_control_ring_buffer_exists(self) - Test that ControlRingBuffer class exists.
- `TestControlRingBuffer.test_control_ring_size` (method, Zeilen 121-124) - def test_control_ring_size(self) - Test that control ring size is correct.
- `TestControlRingBuffer.test_control_msg_size` (method, Zeilen 126-129) - def test_control_msg_size(self) - Test that control message size is correct.

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_crash_monitoring.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <cstdint>, #include <cstdio>, #include <cassert>, #include <cstring>, #include <windows.h>

Symbole:
- `SharedMemoryHeader` (class, Zeilen 12-30) - struct SharedMemoryHeader {
- `ControlRingBuffer` (class, Zeilen 33-37) - struct ControlRingBuffer {
- `t_mab_tilde` (class, Zeilen 40-57) - struct t_mab_tilde {
- `test_crash_detection` (function, Zeilen 60-91) - void test_crash_detection()
- `test_active_process_detection` (function, Zeilen 94-126) - void test_active_process_detection()
- `test_crash_state_transition` (function, Zeilen 129-164) - void test_crash_state_transition()
- `test_still_active_constant` (function, Zeilen 167-174) - void test_still_active_constant()
- `main` (function, Zeilen 176-193) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_ext_main.cpp

- Sprache: `cpp`

Symbole:
- `main` (function, Zeilen 12-22) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_handshake_integration.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <cstdint>, #include <cstdio>, #include <cassert>, #include <cstring>, #include <windows.h>

Symbole:
- `SharedMemoryHeader` (class, Zeilen 14-32) - struct SharedMemoryHeader {
- `test_shm_name_generation` (function, Zeilen 35-52) - void test_shm_name_generation()
- `test_shared_memory_creation` (function, Zeilen 55-167) - void test_shared_memory_creation()
- `test_atomic_flags` (function, Zeilen 170-201) - void test_atomic_flags()
- `test_buffer_calculations` (function, Zeilen 204-244) - void test_buffer_calculations()
- `main` (function, Zeilen 246-263) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_init_worker.cpp

- Sprache: `cpp`

Symbole:
- `main` (function, Zeilen 12-16) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_init_worker_thread.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <thread>

Symbole:
- `main` (function, Zeilen 17-36) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_init_worker_thread_comprehensive.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <cstdint>, #include <cassert>, #include <cstring>, #include <thread>, #include <atomic>, #include <windows.h>

Symbole:
- `SharedMemoryHeader` (class, Zeilen 239-257) - struct SharedMemoryHeader {
- `test_shared_memory_header_layout` (function, Zeilen 295-333) - void test_shared_memory_header_layout()
- `test_mab_tilde_structure_layout` (function, Zeilen 339-371) - void test_mab_tilde_structure_layout()
- `test_instance_id_generation` (function, Zeilen 377-387) - void test_instance_id_generation()
- `test_shared_memory_name_generation` (function, Zeilen 393-406) - void test_shared_memory_name_generation()
- `test_buffer_size_validation` (function, Zeilen 412-426) - void test_buffer_size_validation()
- `test_channel_count_validation` (function, Zeilen 432-446) - void test_channel_count_validation()
- `test_atomic_flag_operations` (function, Zeilen 452-470) - void test_atomic_flag_operations()
- `test_thread_safety` (function, Zeilen 476-496) - void test_thread_safety()
- `test_process_handle_management` (function, Zeilen 502-512) - void test_process_handle_management()
- `test_memory_offset_calculations` (function, Zeilen 518-536) - void test_memory_offset_calculations()
- `main` (function, Zeilen 542-556) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_mab_tilde_assist.cpp

- Sprache: `cpp`

Symbole:
- `main` (function, Zeilen 14-31) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_mab_tilde_dsp64.cpp

- Sprache: `cpp`

Symbole:
- `main` (function, Zeilen 18-36) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_mab_tilde_free.cpp

- Sprache: `cpp`

Symbole:
- `main` (function, Zeilen 14-27) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_mab_tilde_new.cpp

- Sprache: `cpp`

Symbole:
- `main` (function, Zeilen 17-32) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_mab_tilde_perform64.cpp

- Sprache: `cpp`

Symbole:
- `main` (function, Zeilen 17-38) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_message_handlers.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <cstdint>, #include <cstring>

Symbole:
- `_mab_tilde` (class, Zeilen 24-32) - struct _mab_tilde {
- `main` (function, Zeilen 67-117) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_method_layout.py

- Sprache: `python`
- Abhängigkeiten: import unittest, import sys, import os, import numpy as np, import torch, from inference_worker import (

Symbole:
- `FakeScriptedModel` (class, Zeilen 37-65) - class FakeScriptedModel - Mimics a TorchScript model's method surface.
- `FakeScriptedModel.__init__` (method, Zeilen 44-49) - def __init__(self, params=MUSICNET_PARAMS)
- `FakeScriptedModel.forward` (method, Zeilen 51-53) - def forward(self, x)
- `FakeScriptedModel.encode` (method, Zeilen 55-57) - def encode(self, x)
- `FakeScriptedModel.decode` (method, Zeilen 59-61) - def decode(self, z)
- `FakeScriptedModel.prior` (method, Zeilen 63-65) - def prior(self, z)
- `TestGetMethodParams` (class, Zeilen 68-96) - class TestGetMethodParams(unittest.TestCase)
- `TestGetMethodParams.test_extracts_all_four_methods` (method, Zeilen 69-72) - def test_extracts_all_four_methods(self)
- `TestGetMethodParams.test_parses_musicnet_layout` (method, Zeilen 74-80) - def test_parses_musicnet_layout(self)
- `TestGetMethodParams.test_returns_empty_for_bare_object` (method, Zeilen 82-83) - def test_returns_empty_for_bare_object(self)
- `TestGetMethodParams.test_skips_method_without_params` (method, Zeilen 85-96) - def test_skips_method_without_params(self)
- `TestComputeLayout` (class, Zeilen 99-115) - class TestComputeLayout(unittest.TestCase)
- `TestComputeLayout.test_block_size_covers_max_ratio` (method, Zeilen 100-102) - def test_block_size_covers_max_ratio(self)
- `TestComputeLayout.test_respects_larger_requested_bufsize` (method, Zeilen 104-106) - def test_respects_larger_requested_bufsize(self)
- `TestComputeLayout.test_max_channels_over_all_methods` (method, Zeilen 108-111) - def test_max_channels_over_all_methods(self)
- `TestComputeLayout.test_empty_params_uses_requested_size` (method, Zeilen 113-115) - def test_empty_params_uses_requested_size(self)
- `TestInferMethodSemantics` (class, Zeilen 118-171) - class TestInferMethodSemantics(unittest.TestCase)
- `TestInferMethodSemantics.setUp` (method, Zeilen 119-121) - def setUp(self)
- `TestInferMethodSemantics.test_forward_feeds_full_block` (method, Zeilen 123-131) - def test_forward_feeds_full_block(self)
- `TestInferMethodSemantics.test_encode_holds_latent_frames` (method, Zeilen 133-140) - def test_encode_holds_latent_frames(self)
- `TestInferMethodSemantics.test_decode_takes_last_sample_per_channel` (method, Zeilen 142-151) - def test_decode_takes_last_sample_per_channel(self)
- `TestInferMethodSemantics.test_prior_takes_last_conditioning_sample` (method, Zeilen 153-161) - def test_prior_takes_last_conditioning_sample(self)
- `TestInferMethodSemantics.test_output_trims_extra_samples` (method, Zeilen 163-171) - def test_output_trims_extra_samples(self)
- `TestRealModelDispatch` (class, Zeilen 179-220) - class TestRealModelDispatch(unittest.TestCase) - Integration check of the dispatch against the real AFTER model.
- `TestRealModelDispatch.setUpClass` (method, Zeilen 183-186) - def setUpClass(cls)
- `TestRealModelDispatch.test_params_match_musicnet` (method, Zeilen 188-192) - def test_params_match_musicnet(self)
- `TestRealModelDispatch.test_real_decode_shapes` (method, Zeilen 194-199) - def test_real_decode_shapes(self)
- `TestRealModelDispatch.test_real_encode_shapes` (method, Zeilen 201-206) - def test_real_encode_shapes(self)
- `TestRealModelDispatch.test_real_forward_shapes` (method, Zeilen 208-213) - def test_real_forward_shapes(self)
- `TestRealModelDispatch.test_real_prior_shapes` (method, Zeilen 215-220) - def test_real_prior_shapes(self)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_multichannel_layout.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <cstdint>, #include <cstdio>, #include <cassert>, #include <cstring>

Symbole:
- `SharedMemoryHeader` (class, Zeilen 11-29) - struct SharedMemoryHeader {
- `test_single_channel_layout` (function, Zeilen 32-60) - void test_single_channel_layout()
- `test_stereo_layout` (function, Zeilen 63-91) - void test_stereo_layout()
- `test_quad_layout` (function, Zeilen 94-122) - void test_quad_layout()
- `test_buffer_pointer_calculations` (function, Zeilen 125-159) - void test_buffer_pointer_calculations()
- `test_numpy_reshape_dimensions` (function, Zeilen 162-190) - void test_numpy_reshape_dimensions()
- `test_channel_stride` (function, Zeilen 193-232) - void test_channel_stride()
- `main` (function, Zeilen 234-257) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_python_shared_memory.py

- Sprache: `python`
- Abhängigkeiten: import unittest, import sys, import os, import ctypes, import struct, import tempfile, import threading, import time

Symbole:
- `TestSharedMemoryHeader` (class, Zeilen 38-71) - class TestSharedMemoryHeader(unittest.TestCase) - Test the SharedMemoryHeader structure layout and validation.
- `TestSharedMemoryHeader.test_magic_number_constant` (method, Zeilen 41-47) - def test_magic_number_constant(self) - Test that magic number is correct.
- `TestSharedMemoryHeader.test_header_size` (method, Zeilen 49-71) - def test_header_size(self) - Test that header size is reasonable.
- `TestSharedMemoryNames` (class, Zeilen 74-95) - class TestSharedMemoryNames(unittest.TestCase) - Test shared memory and event name generation.
- `TestSharedMemoryNames.test_shm_name_format` (method, Zeilen 77-81) - def test_shm_name_format(self) - Test shared memory name format.
- `TestSharedMemoryNames.test_event_name_format` (method, Zeilen 83-87) - def test_event_name_format(self) - Test event name format.
- `TestSharedMemoryNames.test_name_uniqueness` (method, Zeilen 89-95) - def test_name_uniqueness(self) - Test that different instance IDs produce different names.
- `TestBufferCalculations` (class, Zeilen 98-134) - class TestBufferCalculations(unittest.TestCase) - Test buffer size and offset calculations.
- `TestBufferCalculations.test_input_offset_calculation` (method, Zeilen 101-108) - def test_input_offset_calculation(self) - Test input buffer offset calculation.
- `TestBufferCalculations.test_output_offset_calculation` (method, Zeilen 110-121) - def test_output_offset_calculation(self) - Test output buffer offset calculation.
- `TestBufferCalculations.test_total_size_calculation` (method, Zeilen 123-134) - def test_total_size_calculation(self) - Test total shared memory size calculation.
- `TestMultiChannelLayout` (class, Zeilen 137-170) - class TestMultiChannelLayout(unittest.TestCase) - Test multi-channel memory layout.
- `TestMultiChannelLayout.test_contiguous_layout` (method, Zeilen 140-150) - def test_contiguous_layout(self) - Test that multi-channel layout is contiguous.
- `TestMultiChannelLayout.test_numpy_reshape` (method, Zeilen 152-170) - def test_numpy_reshape(self) - Test NumPy array reshape for multi-channel.
- `TestArgumentParsing` (class, Zeilen 173-186) - class TestArgumentParsing(unittest.TestCase) - Test command-line argument parsing.
- `TestArgumentParsing.test_argument_names` (method, Zeilen 176-180) - def test_argument_names(self) - Test that argument names match expected values.
- `TestArgumentParsing.test_instance_id_format` (method, Zeilen 182-186) - def test_instance_id_format(self) - Test instance ID format for shared memory naming.
- `TestAtomicFlags` (class, Zeilen 189-202) - class TestAtomicFlags(unittest.TestCase) - Test atomic flag operations for lock-free synchronization.
- `TestAtomicFlags.test_flag_values` (method, Zeilen 192-202) - def test_flag_values(self) - Test that flag values are correct.

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_query_mode.py

- Sprache: `python`
- Abhängigkeiten: import io, import os, import sys, import unittest, from contextlib import redirect_stdout, import numpy as np, import torch, from inference_worker import (

Symbole:
- `FakeRaveModel` (class, Zeilen 41-64) - class FakeRaveModel - Mimics the surface of a scripted RAVE model (VariationalScriptedRAVE).
- `FakeRaveModel.__init__` (method, Zeilen 44-52) - def __init__(self)
- `FakeRaveModel._c` (method, Zeilen 55-64) - def _c(self)
- `TestResolveModelPath` (class, Zeilen 67-107) - class TestResolveModelPath(unittest.TestCase)
- `TestResolveModelPath.setUp` (method, Zeilen 68-73) - def setUp(self)
- `TestResolveModelPath.tearDown` (method, Zeilen 75-77) - def tearDown(self)
- `TestResolveModelPath.test_existing_absolute_path_unchanged` (method, Zeilen 79-80) - def test_existing_absolute_path_unchanged(self)
- `TestResolveModelPath.test_path_with_separator_not_searched` (method, Zeilen 82-84) - def test_path_with_separator_not_searched(self)
- `TestResolveModelPath.test_bare_name_found_in_models_dir` (method, Zeilen 86-89) - def test_bare_name_found_in_models_dir(self)
- `TestResolveModelPath.test_bare_name_found_in_worker_dir` (method, Zeilen 91-96) - def test_bare_name_found_in_worker_dir(self)
- `TestResolveModelPath.test_bare_name_without_extension_found` (method, Zeilen 98-102) - def test_bare_name_without_extension_found(self)
- `TestResolveModelPath.test_bare_name_not_found_unchanged` (method, Zeilen 104-107) - def test_bare_name_not_found_unchanged(self)
- `TestDetectModelType` (class, Zeilen 110-116) - class TestDetectModelType(unittest.TestCase)
- `TestDetectModelType.test_rave_detected` (method, Zeilen 111-112) - def test_rave_detected(self)
- `TestDetectModelType.test_unknown` (method, Zeilen 114-116) - def test_unknown(self)
- `TestLabelsAndAttributes` (class, Zeilen 119-140) - class TestLabelsAndAttributes(unittest.TestCase)
- `TestLabelsAndAttributes.setUp` (method, Zeilen 120-121) - def setUp(self)
- `TestLabelsAndAttributes.test_decode_labels` (method, Zeilen 123-127) - def test_decode_labels(self)
- `TestLabelsAndAttributes.test_missing_labels` (method, Zeilen 129-132) - def test_missing_labels(self)
- `TestLabelsAndAttributes.test_model_attributes_scan` (method, Zeilen 134-137) - def test_model_attributes_scan(self)
- `TestLabelsAndAttributes.test_method_attributes_empty` (method, Zeilen 139-140) - def test_method_attributes_empty(self)
- `TestCollectModelInfo` (class, Zeilen 143-157) - class TestCollectModelInfo(unittest.TestCase)
- `TestCollectModelInfo.setUp` (method, Zeilen 144-146) - def setUp(self)
- `TestCollectModelInfo.test_layout_and_methods` (method, Zeilen 148-157) - def test_layout_and_methods(self)
- `TestPrintInfoBlock` (class, Zeilen 160-199) - class TestPrintInfoBlock(unittest.TestCase)
- `TestPrintInfoBlock.test_block_contains_expected_lines` (method, Zeilen 161-190) - def test_block_contains_expected_lines(self)
- `TestPrintInfoBlock.test_error_block` (method, Zeilen 192-199) - def test_error_block(self)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_rag_wiki.py

- Sprache: `python`
- Abhängigkeiten: import os, import shutil, import tempfile, import unittest, import json, import mab_mcp_server as mcp

Symbole:
- `ChunkingTests` (class, Zeilen 80-165) - class ChunkingTests(unittest.TestCase)
- `ChunkingTests.test_python_ast_chunking` (method, Zeilen 81-97) - def test_python_ast_chunking(self)
- `ChunkingTests.test_python_chunks_do_not_overspan_functions` (method, Zeilen 99-103) - def test_python_chunks_do_not_overspan_functions(self)
- `ChunkingTests.test_cpp_structural_chunking` (method, Zeilen 105-117) - def test_cpp_structural_chunking(self)
- `ChunkingTests.test_cpp_multiline_signature` (method, Zeilen 119-142) - def test_cpp_multiline_signature(self)
- `ChunkingTests.test_cpp_crlf_normalization` (method, Zeilen 144-152) - def test_cpp_crlf_normalization(self)
- `ChunkingTests.test_python_signature_keeps_defaults` (method, Zeilen 154-158) - def test_python_signature_keeps_defaults(self)
- `ChunkingTests.test_markdown_section_chunking` (method, Zeilen 160-165) - def test_markdown_section_chunking(self)
- `RAGIntegrationTests` (class, Zeilen 168-250) - class RAGIntegrationTests(unittest.TestCase)
- `RAGIntegrationTests.setUp` (method, Zeilen 169-181) - def setUp(self)
- `RAGIntegrationTests.tearDown` (method, Zeilen 183-184) - def tearDown(self)
- `RAGIntegrationTests.test_index_directory` (method, Zeilen 186-188) - def test_index_directory(self)
- `RAGIntegrationTests.test_hybrid_query_finds_function` (method, Zeilen 190-195) - def test_hybrid_query_finds_function(self)
- `RAGIntegrationTests.test_hybrid_query_prefers_exact_symbol` (method, Zeilen 197-201) - def test_hybrid_query_prefers_exact_symbol(self)
- `RAGIntegrationTests.test_query_returns_chunk_ids` (method, Zeilen 203-209) - def test_query_returns_chunk_ids(self)
- `RAGIntegrationTests.test_format_compact_is_one_line_per_hit` (method, Zeilen 211-216) - def test_format_compact_is_one_line_per_hit(self)
- `RAGIntegrationTests.test_format_json` (method, Zeilen 218-225) - def test_format_json(self)
- `RAGIntegrationTests.test_query_wiki_returns_chunk_ids` (method, Zeilen 227-230) - def test_query_wiki_returns_chunk_ids(self)
- `RAGIntegrationTests.test_query_wiki` (method, Zeilen 232-237) - def test_query_wiki(self)
- `RAGIntegrationTests.test_wiki_generation` (method, Zeilen 239-250) - def test_wiki_generation(self)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_shared_memory_header.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <cstdint>, #include <cstring>, #include <cassert>

Symbole:
- `SharedMemoryHeader` (class, Zeilen 9-27) - struct SharedMemoryHeader {
- `main` (function, Zeilen 29-74) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_shared_memory_header_compatibility.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <cstdint>, #include <cstdio>, #include <cassert>, #include <cstring>, #include <cstddef>

Symbole:
- `SharedMemoryHeader` (class, Zeilen 15-33) - struct SharedMemoryHeader {
- `test_field_offsets` (function, Zeilen 37-100) - void test_field_offsets()
- `test_struct_size` (function, Zeilen 103-115) - void test_struct_size()
- `test_header_usage` (function, Zeilen 118-162) - void test_header_usage()
- `test_buffer_offsets` (function, Zeilen 165-195) - void test_buffer_offsets()
- `test_multichannel_layout` (function, Zeilen 198-223) - void test_multichannel_layout()
- `main` (function, Zeilen 225-245) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_shared_memory_management.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include <windows.h>, #include <cstdint>, #include <cstdio>, #include <cstring>

Symbole:
- `SharedMemoryHeader` (class, Zeilen 14-25) - struct SharedMemoryHeader {
- `main` (function, Zeilen 27-94) - int main()

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_shared_memory_v2.py

- Sprache: `python`
- Abhängigkeiten: import unittest, import sys, import os, import ctypes, from inference_worker import SharedMemoryHeader, SharedMemoryManager

Symbole:
- `TestHeaderLayoutV2` (class, Zeilen 29-56) - class TestHeaderLayoutV2(unittest.TestCase)
- `TestHeaderLayoutV2.test_header_size_is_128` (method, Zeilen 30-31) - def test_header_size_is_128(self)
- `TestHeaderLayoutV2.test_field_offsets_match_cpp` (method, Zeilen 33-51) - def test_field_offsets_match_cpp(self)
- `TestHeaderLayoutV2.test_flags_are_c_long` (method, Zeilen 53-56) - def test_flags_are_c_long(self)
- `_manager_with_header` (function, Zeilen 59-65) - def _manager_with_header()
- `TestApplyMethod` (class, Zeilen 68-111) - class TestApplyMethod(unittest.TestCase)
- `TestApplyMethod.test_decode_layout` (method, Zeilen 69-78) - def test_decode_layout(self)
- `TestApplyMethod.test_encode_layout` (method, Zeilen 80-89) - def test_encode_layout(self)
- `TestApplyMethod.test_forward_layout` (method, Zeilen 91-98) - def test_forward_layout(self)
- `TestApplyMethod.test_unknown_method_is_noop` (method, Zeilen 100-106) - def test_unknown_method_is_noop(self)
- `TestApplyMethod.test_no_params_is_noop` (method, Zeilen 108-111) - def test_no_params_is_noop(self)

## C:\Users\marku\Documents\GitHub\artqcid\ai-projects\mab_tilde\test\test_worker_launch.cpp

- Sprache: `cpp`
- Abhängigkeiten: #include "worker_launch.h", #include <cstdio>, #include <cstring>, #include <string>

Symbole:
- `read_all` (function, Zeilen 20-27) - static bool read_all(HANDLE pipe, std::string* out)
- `main` (function, Zeilen 29-154) - int main()

