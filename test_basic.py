import json
from agents import BugAgent, FixAgent
from llm import MockProvider
from models import Severity
from orchestrator import ReviewManager
from static_check import detect_language, static_check

EMPTY = json.dumps({"findings": []})


# ---------- unit: static analysis ----------
def test_detects_hardcoded_secret():
    f = static_check('API_KEY = "sk-123"\n')
    assert f[0].severity == Severity.CRITICAL and f[0].line_start == 1

def test_detects_eval():
    assert any("eval" in f.title for f in static_check("x = eval(input())\n"))

def test_detects_sql_injection():
    assert any("SQL" in f.title for f in static_check('cur.execute(f"SELECT * FROM t WHERE id={uid}")\n'))

def test_detects_mutable_default():
    assert any("Mutable" in f.title for f in static_check("def f(x=[]):\n    return x\n"))

def test_clean_code_has_no_findings():
    assert static_check("def add(a, b):\n    return a + b\n") == []

def test_syntax_error_reported():
    assert static_check("def broken(:\n")[0].title == "Syntax error"

def test_language_detection():
    assert detect_language("def f():\n    pass\n") == "python"
    assert detect_language('#include <stdio.h>\nint main(){}') == "c/c++"


# ---------- unit: agents (with MockProvider) ----------
def test_agent_retries_and_normalizes_severity():
    good = json.dumps({"findings": [{"severity": "high", "title": "Off by one",
                                     "line_start": 2, "explanation": "x", "suggested_fix": "y"}]})
    result = BugAgent(MockProvider(["not json at all", good])).run("x = 1")
    assert len(result.findings) == 1
    assert result.findings[0].severity == Severity.HIGH      # "high" was normalized
    assert result.errors                                     # the first attempt was logged

def test_agent_degrades_gracefully():
    result = BugAgent(MockProvider(["garbage"])).run("x = 1")
    assert result.findings == [] and result.errors


# ---------- unit: fix agent safeguards ----------
def test_fix_rejects_invalid_python():
    bad = json.dumps({"improved_code": "def broken(:", "changes": []})
    assert FixAgent(MockProvider([bad])).run("x = 1\n", []).improved_code == "x = 1\n"

def test_fix_rejects_removed_function():
    bad = json.dumps({"improved_code": "y = 2\n", "changes": []})
    original = "def keep_me():\n    return 1\n"
    assert FixAgent(MockProvider([bad])).run(original, []).improved_code == original


# ---------- integration: full pipeline with a mocked LLM ----------
def test_pipeline_marks_finding_resolved():
    bug = json.dumps({"findings": [{"severity": "High", "title": "Index out of range",
                                    "line_start": 2, "explanation": "len(xs) is out of range",
                                    "suggested_fix": "use len(xs) - 1"}]})
    fix = json.dumps({"improved_code": "def f(xs):\n    return xs[len(xs) - 1]\n",
                      "changes": ["Fixed index"]})
    # call order: 3 agents (initial), fix agent, 3 agents (final review)
    llm = MockProvider([bug, EMPTY, EMPTY, fix, EMPTY, EMPTY, EMPTY])
    result = ReviewManager(llm).run_pipeline("def f(xs):\n    return xs[len(xs)]\n", quick_verify=False) 
    assert len(result.resolved) == 1
    assert not result.remaining and not result.introduced

def test_quick_verify_resolves_ast_finding():
    fix = json.dumps({"improved_code": "def f(x=None):\n    return x or []\n",
                      "changes": ["Replaced mutable default"]})
    # call order: 3 agents (initial), then the fix agent. No LLM re-review in quick mode.
    llm = MockProvider([EMPTY, EMPTY, EMPTY, fix])
    result = ReviewManager(llm).run_pipeline("def f(x=[]):\n    return x\n")
    assert any("Mutable" in f.title for f in result.resolved)
    assert not result.remaining