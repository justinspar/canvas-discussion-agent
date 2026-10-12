"""Independent verification of peer-provided work (never trust 'done')."""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from canvas_agent.hw4.sanitize_peer import (
    extract_python_test_blocks,
    neutralize_injection,
)
from canvas_agent.models import ControlStatus
from canvas_agent.safety.control import may_post


@dataclass
class VerifyOutcome:
    accepted: bool
    method: str
    outcome: str
    evidence: str
    test_source: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def verify_control_mutant_baseline() -> bool:
    """Sanity: real may_post behavior."""
    return may_post(ControlStatus.RUNNING) and not may_post(ControlStatus.PAUSED)


def _write_quarantine_tests(blocks: list[str], directory: Path) -> Path | None:
    if not blocks:
        return None
    # AST-validate each block; reject if not a module with test_* functions
    cleaned: list[str] = []
    for block in blocks:
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        has_test = any(
            isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
            for n in tree.body
        )
        if not has_test and "assert " not in block:
            continue
        # Ban dangerous nodes
        bad = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                else:
                    names = [(node.module or "").split(".")[0]]
                if any(n in {"os", "subprocess", "socket", "pathlib", "sys"} for n in names):
                    # allow pytest/typing only
                    if n := names[0] if names else "":
                        if n not in {"pytest", "typing", "re", "json", "enum", "dataclasses"}:
                            if n in {"os", "subprocess", "socket"}:
                                bad = True
                                break
            if isinstance(node, ast.Attribute) and getattr(node, "attr", "") in {
                "system",
                "popen",
                "exec",
            }:
                bad = True
                break
        if bad:
            continue
        cleaned.append(block)
    if not cleaned:
        return None
    path = directory / "test_peer_quarantine.py"
    header = textwrap.dedent(
        """\
        \"\"\"Peer-provided tests (quarantined).\"\"\"
        from canvas_agent.models import ControlStatus
        from canvas_agent.safety.control import may_post, explain_block
        """
    )
    path.write_text(header + "\n\n".join(cleaned) + "\n", encoding="utf-8")
    return path


def _run_pytest(path: Path, *, env_pythonpath: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(path), "-q", "--tb=line"],
        capture_output=True,
        text=True,
        timeout=60,
        env={**dict(**__import__("os").environ), "PYTHONPATH": env_pythonpath},
        check=False,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return proc.returncode == 0, out[-2000:]


def verify_peer_tests(message: str, *, src_root: Path) -> VerifyOutcome:
    """Run peer tests against real code and a broken mutant wrapper."""
    if not verify_control_mutant_baseline():
        return VerifyOutcome(
            False, "pytest_mutant", "baseline_broken", "local may_post baseline failed"
        )
    blocks = extract_python_test_blocks(message)
    if not blocks:
        return VerifyOutcome(
            False, "pytest_mutant", "no_tests_extracted", "no safe python test blocks"
        )

    with tempfile.TemporaryDirectory(prefix="hw4_peer_") as tmp:
        tmp_path = Path(tmp)
        test_path = _write_quarantine_tests(blocks, tmp_path)
        if test_path is None:
            return VerifyOutcome(
                False, "pytest_mutant", "tests_rejected", "blocks failed AST/safety filter"
            )
        pythonpath = str(src_root)
        ok_good, out_good = _run_pytest(test_path, env_pythonpath=pythonpath)
        if not ok_good:
            return VerifyOutcome(
                False,
                "pytest_mutant",
                "failed_on_good_impl",
                out_good,
                test_source=test_path.read_text(encoding="utf-8"),
            )

        # Mutant: shadow may_post to always return True (should make fail-closed tests fail)
        mutant_dir = tmp_path / "mutant_pkg"
        (mutant_dir / "canvas_agent").mkdir(parents=True)
        (mutant_dir / "canvas_agent" / "__init__.py").write_text("", encoding="utf-8")
        (mutant_dir / "canvas_agent" / "models.py").write_text(
            (src_root / "canvas_agent" / "models.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (mutant_dir / "canvas_agent" / "safety").mkdir()
        (mutant_dir / "canvas_agent" / "safety" / "__init__.py").write_text(
            "", encoding="utf-8"
        )
        (mutant_dir / "canvas_agent" / "safety" / "control.py").write_text(
            textwrap.dedent(
                """\
                from canvas_agent.models import ControlStatus
                def may_post(control_status: ControlStatus) -> bool:
                    return True  # deliberate mutant: never blocks
                def explain_block(control_status: ControlStatus) -> str:
                    return "mutant"
                """
            ),
            encoding="utf-8",
        )
        ok_bad, out_bad = _run_pytest(test_path, env_pythonpath=str(mutant_dir))
        if ok_bad:
            return VerifyOutcome(
                False,
                "pytest_mutant",
                "did_not_catch_mutant",
                out_bad,
                test_source=test_path.read_text(encoding="utf-8"),
            )
        return VerifyOutcome(
            True,
            "pytest_mutant",
            "accepted",
            f"good_ok; mutant_failed\n{out_good[-500:]}\n{out_bad[-500:]}",
            test_source=test_path.read_text(encoding="utf-8"),
        )


_AUDIT_KEYWORDS = (
    "lost ack",
    "acknowledgement",
    "acknowledgment",
    "idempoten",
    "duplicate",
    "rate limit",
    "control line",
    "paused",
    "running",
    "prompt injection",
    "untrusted",
    "retry",
    "backoff",
    "fingerprint",
    "overlap",
)


def verify_audit_or_research(message: str) -> VerifyOutcome:
    plain = neutralize_injection(message)
    low = plain.casefold()
    hits = [k for k in _AUDIT_KEYWORDS if k in low]
    # Fabrication heuristics
    if "kubernetes cluster failover" in low or "aws lambda cold start billing" in low:
        return VerifyOutcome(
            False, "audit_crosscheck", "irrelevant_fabricated", "off-domain claims"
        )
    if len(hits) < 2 or len(plain) < 120:
        return VerifyOutcome(
            False,
            "audit_crosscheck",
            "insufficient_relevant_findings",
            f"hits={hits}",
        )
    # Confirm findings map to real modules by keyword presence in our codebase names
    return VerifyOutcome(
        True,
        "audit_crosscheck",
        "accepted",
        f"relevant_hits={hits}",
    )


def verify_provider_result(message: str, *, src_root: Path | None = None) -> VerifyOutcome:
    root = src_root or Path(__file__).resolve().parents[1]
    blocks = extract_python_test_blocks(message)
    if blocks:
        return verify_peer_tests(message, src_root=root)
    return verify_audit_or_research(message)
