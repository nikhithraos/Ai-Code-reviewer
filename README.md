#  Agentic AI Code Review & Developer Assistant

A multi-agent code review tool that combines **Python AST static analysis** with **local LLM reasoning** to find bugs, security vulnerabilities, and performance problems, explain them, generate fixes, and verify the result. It runs fully offline using [Ollama](https://ollama.com), so there are no API keys, no cost, and your code never leaves your machine.


---

##  Features

- **Multi-agent pipeline:** an orchestrator coordinates specialized Bug, Security, and Performance agents.
- **Hybrid analysis:** deterministic AST checks provide exact, verified findings; the LLM adds semantic reasoning (logic errors, edge cases).
- **Severity ranking:** every issue is rated Critical, High, Medium, or Low and explained clearly.
- **Fix Agent with safeguards:** generates corrected code, then rejects it if it is not valid Python or if it removes existing functions or classes.
- **Verification loop:** re-checks the improved code and reports what was **Resolved**, **Remaining**, or **Newly introduced**.
- **Swappable LLM provider:** agents depend on an abstract `LLMProvider` interface, so changing models or vendors means writing one small class.
- **Graceful degradation:** retries on invalid JSON; if an agent fails or times out, the pipeline continues and reports a warning.
- **Streamlit web UI:** findings dashboard, side-by-side diff, and downloadable Markdown report.

---

##  Architecture

```
User Code
    ↓
Language Detection ── AST Static Analyzer   (deterministic, exact line numbers)
    ↓
Review Manager (Orchestrator)
    ↓
┌───────────────┬─────────────────┬───────────────────┐
│   Bug Agent   │  Security Agent │ Performance Agent │   (LLM, receives AST hints)
└───────────────┴─────────────────┴───────────────────┘
    ↓
Merge + Deduplicate + Rank by severity
    ↓
Fix Agent  →  validated: parses with ast.parse, keeps all function/class names
    ↓
Verification (Quick: AST re-check  |  Deep: full LLM re-review)
    ↓
Report: Resolved / Remaining / Newly introduced
```

### Design ideas

| Concept | How it is used |
|---|---|
| **Strategy pattern** | `LLMProvider` interface with `OllamaProvider` and `MockProvider` implementations |
| **Visitor pattern** | `ASTAnalyzer` extends `ast.NodeVisitor`, one `visit_X` method per rule |
| **Template Method** | `BaseAgent` holds the shared retry and parse logic; each agent only supplies a name, category, and prompt |
| **Schema validation** | Pydantic models validate LLM JSON output; invalid output triggers a corrective retry |
| **Hybrid grounding** | AST findings are passed into the LLM prompts as verified evidence to reduce duplicates and hallucination |

---

##  Project Structure

```
Ai-Code-reviewer/
├── models.py          # Pydantic schemas (Finding, FixResult, PipelineResult)
├── llm.py             # LLMProvider interface, Ollama + Mock providers, factory
├── static_check.py    # AST analyzer + language detection
├── agents.py          # BaseAgent, Bug/Security/Performance agents, FixAgent
├── orchestrator.py    # ReviewManager (pipeline) + Markdown report builder
├── app.py             # Streamlit UI
├── sample_buggy.py    # Demo input with planted issues
├── test_basic.py      # Unit and integration tests (no LLM needed)
├── requirements.txt
└── docs/              # Screenshots
```

---

##  Getting Started

### Prerequisites

- Python **3.10+**
- [Ollama](https://ollama.com) installed and running
- 8 GB RAM minimum (16 GB recommended for the 7B model)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/nikhithraos/Ai-Code-reviewer.git
cd Ai-Code-reviewer

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download a local coding model
ollama pull qwen2.5-coder:7b
# Low on RAM? Use the smaller model instead:
# ollama pull qwen2.5-coder:3b
```

### Run the tests (no LLM required)

```bash
python -m pytest -v
```

### Launch the app

```bash
streamlit run app.py
```

Open http://localhost:8501, paste code or upload a `.py` file (try `sample_buggy.py`), and click **Run Review**.

### Sidebar settings

| Setting | Meaning |
|---|---|
| **Ollama model** | Model name exactly as shown by `ollama list` |
| **Run agents in parallel** | Faster on strong hardware; on CPU-only laptops leave it **off** |
| **Quick verify** | Verifies fixes with the instant AST check instead of a second LLM review (recommended) |

---

##  What It Detects

**Static (AST), deterministic:** hardcoded secrets, `eval`/`exec`, `subprocess` with `shell=True`, SQL built with string formatting, mutable default arguments, bare `except`, deeply nested loops, syntax errors.

**LLM agents, semantic:** off-by-one errors, unhandled edge cases (empty input, division by zero), insecure deserialization, weak hashing, inefficient algorithms, and other issues that need reasoning about intent.

---

## 📸 Screenshots

| Findings | Diff of generated fix |
|---|---|
| ![Findings](docs/findings.png) | ![Diff](docs/diff.png) |

![Final report](docs/report.png)

---

## 🧪 Testing

The test suite runs with `MockProvider`, so it needs no LLM and finishes in about a second.

- **Unit tests:** every AST rule (positive and negative cases), language detection, agent retry and severity normalization, Fix Agent safeguards.
- **Integration tests:** the full pipeline with a mocked LLM, covering both the quick-verify path and the deep LLM re-review path.

```bash
python -m pytest -v
```

---

##  Results

Evaluated on `sample_buggy.py`, which contains 8 planted issues. *(Fill in with your own measured runs.)*

| Metric | Value |
|---|---|
| Planted issues | 8 |
| Detected by AST (deterministic) | _/8 |
| Additionally detected by LLM agents | _/8 |
| Fixes accepted by safeguards | _ |
| End-to-end time (7B model, CPU, quick verify) | _ min |

---

##  Limitations

- **Python-first.** Language detection works for several languages, but AST analysis and fix verification support Python only.
- **LLM variability.** Local models can miss issues or report false positives, and results differ between runs.
- **Fixes are verified structurally, not semantically.** A fix must parse and preserve function and class names, but it can still change behavior (for example, raising an exception instead of returning a value). Running the user's own tests against the fix is future work.
- **Quick verify only confirms AST findings.** LLM-found issues are re-checked only in deep mode.
- **Deduplication is by line number.** Two distinct issues on the same line may be merged into one.
- **Speed.** On a CPU-only laptop a full run can take several minutes because output generation is slow.
- **Context limits.** Very large files must be split before review.

---

##  Future Enhancements

- Fix only the affected functions instead of rewriting the whole file (faster and safer)
- Run user-provided unit tests against generated fixes
- Multi-language analysis with tree-sitter
- GitHub repository and pull request review
- Bandit / Semgrep integration as additional static sources
- Persistent review history (SQLite)
- Result caching and streaming progress in the UI
- RAG over a project's own coding standards

---

##  Tech Stack

Python · Ollama (`qwen2.5-coder`) · `ast` · Pydantic · Streamlit · pytest · Requests

---


##  Author

**Nikhith Rao S**, [@nikhithraos](https://github.com/nikhithraos)
