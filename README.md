# RepoPilot 🤖

**A measurable, human-controllable AI agent for diagnosing and fixing CI failures.**

RepoPilot is a Python-based AI agent designed to inspect repositories, investigate CI failures, and assist with proposed fixes under human supervision. It uses a provider-independent architecture so the underlying language model can be changed without rewriting the agent's core logic.

> **Current status:** Foundation and read-only Git inspection implemented. Automated tests cover agent behavior, tool execution, provider message conversion, tracing, and failure handling. GitHub Actions diagnosis and automated fix generation are planned features.

## 🎯 Project Goals

* Build a lightweight ReAct-style AI agent without depending on a large agent framework.
* Separate agent logic from LLM provider integrations.
* Inspect repository state through controlled tools.
* Record execution events for debugging and evaluation.
* Keep consequential changes under human approval.
* Evaluate agent performance using reproducible test scenarios.

## 🏗️ Architecture

```text
RepoPilot
│
├── CLI
│   └── main.py
│
├── Core
│   ├── agent.py
│   └── tracing.py
│
├── Providers
│   ├── base.py
│   ├── gemini_adapter.py
│   └── ollama_adapter.py
│
├── Tools
│   └── git_tools.py
│
├── Tests
│   ├── test_agent.py
│   ├── test_providers.py
│   ├── test_tools.py
│   └── test_tracing.py
│
└── Evaluation
    └── harness.py
```

*The tree highlights the main project components; some files may be placeholders or under development.*

### Design principles

**Provider independence:** The core agent depends on the `LLMProvider` interface rather than directly importing a provider SDK.

**Controlled tool execution:** The currently implemented `git_status` tool performs read-only Git inspection.

**Observability:** Each run can record structured events, timings, tool outcomes, and an execution summary.

**Human control:** Repository-changing operations are not currently implemented. Future fix-generation and pull-request workflows will require explicit approval and safety checks.

## ⚙️ Technology Stack

| Component            | Technology                     |
| -------------------- | ------------------------------ |
| Language             | Python 3.12+                   |
| LLM integration      | Google Gemini API              |
| Provider abstraction | Custom `LLMProvider` interface |
| Data validation      | Pydantic                       |
| Configuration        | `python-dotenv`                |
| Testing              | pytest                         |
| Version control      | Git                            |
| Trace format         | JSON                           |

## 🚀 Getting Started

### 1. Prerequisites

* Python 3.12 or later
* Git
* A Gemini API key
* A supported Gemini model available to your API account

### 2. Create and activate a virtual environment

**Windows PowerShell:**

```powershell
cd D:\RepoPilot

python -m venv .venv

.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, invoke the virtual environment's Python executable directly instead of changing system execution policies.

### 3. Install dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 4. Configure environment variables

Copy `.env.example` to `.env` if the example file exists:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and configure your credentials and model:

```dotenv
REPOPILOT_PROVIDER=gemini
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=your_supported_model_name
```

Use a model currently available to your API account. Keep `.env` private and never commit your API key.

### 5. Run RepoPilot

Inspect the current repository:

```powershell
.\.venv\Scripts\python.exe -m repopilot.main --repo "D:\RepoPilot" "Check my repository status and explain any changes."
```

You can also inspect another existing local Git repository by replacing the `--repo` path.

RepoPilot currently supports read-only Git status inspection through its `git_status` tool.

## 🔍 Observability

RepoPilot includes a lightweight tracing component in `src/repopilot/core/tracing.py`.

A run can record:

* LLM interaction counts and durations
* Tool invocation events
* Tool execution results
* Errors encountered during execution
* Overall run duration and event counts

### Trace output

Generated JSON traces are saved under:

```text
.runs/
└── <run_id>.json
```

The `.runs/` directory is excluded from Git through `.gitignore`.

Trace data is intended for debugging and future evaluation. It should not be treated as a complete audit or security guarantee; sensitive data must be handled carefully as tracing evolves.

