import ast
import re
from models import Category, Finding, Severity

SECRET_HINTS = ("password", "secret", "api_key", "apikey", "token")
DANGEROUS_CALLS = {"eval", "exec"}
SUBPROCESS_FUNCS = {"run", "call", "Popen", "check_output"}


class ASTAnalyzer(ast.NodeVisitor):
    """Walks the syntax tree (Visitor pattern) and flags known risky patterns."""

    def __init__(self):
        self.findings: list[Finding] = []
        self._loop_depth = 0

    def analyze(self, code: str) -> list[Finding]:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [Finding(category=Category.BUG, severity=Severity.CRITICAL,
                            title="Syntax error", line_start=e.lineno,
                            explanation=str(e), suggested_fix="Correct the syntax.",
                            source="ast")]
        self.visit(tree)
        return self.findings

    def _add(self, node, category, severity, title, explanation, fix):
        self.findings.append(Finding(
            category=category, severity=severity, title=title,
            line_start=node.lineno, explanation=explanation,
            suggested_fix=fix, source="ast"))

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Name) and func.id in DANGEROUS_CALLS:
            self._add(node, Category.SECURITY, Severity.HIGH,
                      f"Use of {func.id}()",
                      "Executes arbitrary code; dangerous with untrusted input.",
                      "Use ast.literal_eval or explicit parsing.")
        if isinstance(func, ast.Attribute):
            if func.attr in SUBPROCESS_FUNCS and any(
                    kw.arg == "shell" and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True for kw in node.keywords):
                self._add(node, Category.SECURITY, Severity.HIGH,
                          "subprocess with shell=True",
                          "Allows command injection if any part is user-controlled.",
                          "Pass an argument list and keep shell=False.")
            if func.attr == "execute" and node.args and isinstance(
                    node.args[0], (ast.JoinedStr, ast.BinOp)):
                self._add(node, Category.SECURITY, Severity.CRITICAL,
                          "Possible SQL injection",
                          "Query is built with string formatting or concatenation.",
                          "Use parameterized queries: execute(sql, params).")
        self.generic_visit(node)

    def visit_Assign(self, node):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) \
                and node.value.value:
            for target in node.targets:
                if isinstance(target, ast.Name) and any(
                        h in target.id.lower() for h in SECRET_HINTS):
                    self._add(node, Category.SECURITY, Severity.CRITICAL,
                              "Hardcoded secret",
                              f"'{target.id}' stores a credential as a string literal.",
                              "Load it from an environment variable or secrets manager.")
        self.generic_visit(node)

    def _visit_loop(self, node):
        self._loop_depth += 1
        if self._loop_depth == 3:          # report once, at the 3rd level
            self._add(node, Category.PERFORMANCE, Severity.MEDIUM,
                      "Deeply nested loops",
                      "Three or more nested loops suggest O(n^3) or worse.",
                      "Use sets/dicts for lookups or precompute values.")
        self.generic_visit(node)
        self._loop_depth -= 1

    visit_For = visit_While = _visit_loop

    def visit_ExceptHandler(self, node):
        if node.type is None:
            self._add(node, Category.QUALITY, Severity.LOW, "Bare except",
                      "Catches every exception, including KeyboardInterrupt.",
                      "Catch specific exception types.")
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        for default in node.args.defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self._add(node, Category.BUG, Severity.MEDIUM,
                          "Mutable default argument",
                          "The default object is created once and shared across calls.",
                          "Default to None and create the object inside the function.")
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef


def static_check(code: str) -> list[Finding]:
    return ASTAnalyzer().analyze(code)


def detect_language(code: str) -> str:
    try:
        ast.parse(code)
        return "python"
    except SyntaxError:
        pass
    heuristics = [
        ("java", r"public static void main|System\.out\.println"),
        ("c/c++", r"#include\s*<"),
        ("javascript", r"console\.log|\bfunction\s+\w+\s*\(|=>"),
        ("python", r"^\s*def \w+\(.*\):|^\s*import \w+"),
    ]
    for lang, pattern in heuristics:
        if re.search(pattern, code, re.MULTILINE):
            return lang
    return "unknown"