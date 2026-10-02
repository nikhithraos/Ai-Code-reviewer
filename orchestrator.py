from concurrent.futures import ThreadPoolExecutor
from agents import BugAgent, FixAgent, PerformanceAgent, SecurityAgent
from models import Finding, PipelineResult
from static_check import detect_language, static_check

SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def _key(f: Finding) -> tuple:
    return (f.category.value, f.title.strip().lower())


class ReviewManager:
    """Orchestrator: decides what runs, merges results, drives the fix loop."""

    def __init__(self, llm, parallel: bool = False):
        self.agents = [BugAgent(llm), SecurityAgent(llm), PerformanceAgent(llm)]
        self.fixer = FixAgent(llm)
        self.parallel = parallel      # local models often handle parallel requests poorly

    def review(self, code: str, language: str):
        static = static_check(code) if language == "python" else []
        if self.parallel:
            with ThreadPoolExecutor(max_workers=len(self.agents)) as pool:
                results = list(pool.map(lambda a: a.run(code, static), self.agents))
        else:
            results = [a.run(code, static) for a in self.agents]
        findings = static + [f for r in results for f in r.findings]
        errors = [e for r in results for e in r.errors]
        return self._dedupe_and_rank(findings), errors

    @staticmethod
    def _dedupe_and_rank(findings: list[Finding]) -> list[Finding]:
        seen, unique = set(), []
        for f in findings:          # AST findings come first, so they win duplicates
            k = f.line_start if f.line_start is not None else f.title.lower()
            if k not in seen:
                seen.add(k)
                unique.append(f)
        unique.sort(key=lambda f: SEV_ORDER[f.severity.value])
        for i, f in enumerate(unique, 1):
            f.id = f"F{i:03d}"
        return unique

    def run_pipeline(self, code: str) -> PipelineResult:
        language = detect_language(code)
        initial, errors = self.review(code, language)

        if language != "python":
            errors.append("Fix and re-review skipped: only Python is supported for fixes.")
            return PipelineResult(language=language, initial=initial, errors=errors)
        if not initial:
            return PipelineResult(language=language, errors=errors)

        fix = self.fixer.run(code, initial)
        if fix.improved_code == code:                 # fix rejected, nothing to re-review
            final = initial
        else:
            final, final_errors = self.review(fix.improved_code, language)
            errors += final_errors

        initial_keys, final_keys = {_key(f) for f in initial}, {_key(f) for f in final}
        return PipelineResult(
            language=language, initial=initial, fix=fix, final=final,
            resolved=[f for f in initial if _key(f) not in final_keys],
            remaining=[f for f in initial if _key(f) in final_keys],
            introduced=[f for f in final if _key(f) not in initial_keys],
            errors=errors,
        )


def build_markdown(r: PipelineResult) -> str:
    lines = ["# Code Review Report", f"**Language:** {r.language}", "",
             f"**Issues found:** {len(r.initial)} | **Resolved:** {len(r.resolved)} | "
             f"**Remaining:** {len(r.remaining)} | **Newly introduced:** {len(r.introduced)}",
             "", "## Findings"]
    for f in r.initial:
        lines += [f"### {f.id} [{f.severity.value}] {f.title} (line {f.line_start})",
                  f"- **Category:** {f.category.value} ({f.source})",
                  f"- **Explanation:** {f.explanation}",
                  f"- **Suggested fix:** {f.suggested_fix}", ""]
    if r.fix:
        lines += ["## Changes made"] + [f"- {c}" for c in r.fix.changes]
        lines += ["", "## Improved code", "```python", r.fix.improved_code, "```"]
    if r.errors:
        lines += ["", "## Warnings"] + [f"- {e}" for e in r.errors]
    return "\n".join(lines)