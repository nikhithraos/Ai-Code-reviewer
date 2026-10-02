import ast
import json
import re
from models import Category, Finding, FixResult, ReviewResult


def extract_json(text: str) -> dict:
    """LLMs sometimes wrap JSON in prose or code fences; grab the outermost object."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0) if match else text)


def number_lines(code: str) -> str:
    return "\n".join(f"{i}: {line}" for i, line in enumerate(code.splitlines(), 1))


class BaseAgent:
    """Template Method: subclasses only supply name, category and system prompt."""
    name = "BaseAgent"
    category: Category = Category.BUG
    system_prompt = ""

    def __init__(self, llm, max_retries: int = 2):
        self.llm, self.max_retries = llm, max_retries

    def build_prompt(self, code: str, hints: list[Finding]) -> str:
        hint_text = "\n".join(f"- line {h.line_start}: {h.title}" for h in hints) or "None"
        return (
            "Review the code below.\n\n"
            f"STATIC ANALYSIS HINTS (already verified, do not repeat):\n{hint_text}\n\n"
            f"CODE (with line numbers):\n{number_lines(code)}\n\n"
            'Respond ONLY with JSON: {"findings": [{"severity": "Critical|High|Medium|Low", '
            '"title": "", "line_start": 0, "explanation": "", "suggested_fix": ""}]}\n'
            'If there are no issues return {"findings": []}.'
        )

    def run(self, code: str, hints: list[Finding] | None = None) -> ReviewResult:
        prompt, errors = self.build_prompt(code, hints or []), []
        for attempt in range(1, self.max_retries + 2):
            try:
                raw = self.llm.generate(self.system_prompt, prompt, json_mode=True)
                data = extract_json(raw)
                findings = [
                    # category is forced by the agent so the LLM cannot mislabel it
                    Finding(**{**item, "category": self.category, "source": "llm"})
                    for item in data.get("findings", [])
                ]
                return ReviewResult(findings=findings, errors=errors)
            except (ValueError, TypeError, AttributeError) as e:
                # JSONDecodeError and pydantic ValidationError are both ValueErrors
                errors.append(f"{self.name} attempt {attempt}: invalid output ({e})")
                prompt += "\n\nYour previous output was invalid. Return ONLY valid JSON."
            except Exception as e:                       # network, timeout, model down
                errors.append(f"{self.name}: LLM call failed ({e})")
                break
        return ReviewResult(errors=errors)               # degrade gracefully


class BugAgent(BaseAgent):
    name, category = "BugAgent", Category.BUG
    system_prompt = (
        "You are a meticulous bug-hunting code reviewer. Report ONLY real defects: "
        "logic errors, wrong conditions, off-by-one errors, incorrect loops, misused or "
        "undefined variables, unhandled edge cases (empty input, None, division by zero). "
        "Ignore style. Explain WHY each issue is wrong. If unsure, lower the severity "
        "instead of inventing issues."
    )


class SecurityAgent(BaseAgent):
    name, category = "SecurityAgent", Category.SECURITY
    system_prompt = (
        "You are an application security engineer. Find vulnerabilities: hardcoded "
        "secrets, SQL injection, command injection, path traversal, insecure "
        "deserialization (pickle, yaml.load), weak hashing (md5/sha1 for passwords), "
        "missing input validation, insecure file handling. For each, describe the "
        "attack scenario and the mitigation. Critical = remotely exploitable."
    )


class PerformanceAgent(BaseAgent):
    name, category = "PerformanceAgent", Category.PERFORMANCE
    system_prompt = (
        "You are a performance engineer. Find inefficient algorithms (state the time "
        "complexity), repeated computation inside loops, string concatenation in loops, "
        "list membership tests where a set would do, unnecessary copies, and loading "
        "whole files into memory. Suggest a concrete faster alternative. "
        "Ignore micro-optimizations."
    )


def defined_names(code: str) -> set[str]:
    """Names of all functions and classes in the code (empty set if unparsable)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    return {n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


class FixAgent:
    system_prompt = (
        "You are a careful refactoring engineer. Fix ONLY the listed issues. Preserve "
        "all function and class names, signatures and behavior. Do not add unrelated "
        "features or reformat unrelated code. Respond ONLY with JSON: "
        '{"improved_code": "<full corrected code>", "changes": ["<why each change>"]}'
    )

    def __init__(self, llm, max_retries: int = 1):
        self.llm, self.max_retries = llm, max_retries

    def run(self, code: str, findings: list[Finding]) -> FixResult:
        issues = [{"id": f.id, "title": f.title, "line": f.line_start,
                   "explanation": f.explanation, "suggested_fix": f.suggested_fix}
                  for f in findings]
        prompt = f"CODE:\n{code}\n\nISSUES TO FIX:\n{json.dumps(issues, indent=2)}"
        reason = "no attempt made"
        for _ in range(self.max_retries + 1):
            try:
                raw = self.llm.generate(self.system_prompt, prompt, json_mode=True)
                result = FixResult(**extract_json(raw))
                ast.parse(result.improved_code)                       # safeguard 1: valid syntax
                missing = defined_names(code) - defined_names(result.improved_code)
                if missing:                                           # safeguard 2: API preserved
                    raise ValueError(f"fix removed definitions: {sorted(missing)}")
                return result
            except (ValueError, TypeError, AttributeError, SyntaxError) as e:
                reason = str(e)
                prompt += f"\n\nYour previous answer was rejected ({reason}). Try again."
            except Exception as e:
                reason = f"LLM call failed: {e}"
                break
        return FixResult(improved_code=code,
                         changes=[f"Fix rejected ({reason}); original code kept."])