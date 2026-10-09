"""Identity, original command budget and exit-status controls for the harness."""
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

import run_research


@pytest.mark.parametrize("mode", ["failure", "timeout", "drift", "wrong_head", "wrong_tree", "wrong_manifest", "wrong_platform"])
def test_harness_preserves_fixed_identity_budget_and_original_failure(monkeypatch, tmp_path, mode):
    expected = json.loads((run_research.Path(run_research.__file__).parent / "source-manifest.json").read_text())
    calls, reads = [], []
    def manifest():
        reads.append(None)
        result = dict(expected)
        if mode == "wrong_manifest" or (mode == "drift" and len(reads) > 1):
            key = next(iter(result)); result[key] = "0" * 64
        return result
    def git(argument):
        if argument == "HEAD": return "0" * 40 if mode == "wrong_head" else run_research.HEAD
        return "0" * 40 if mode == "wrong_tree" else run_research.TREE
    monkeypatch.setattr(run_research, "load_source", lambda source: SimpleNamespace(git_value=git, source_manifest=manifest))
    monkeypatch.setattr(run_research, "os", SimpleNamespace(name="posix" if mode == "wrong_platform" else "nt", path=os.path, pathsep=os.pathsep, environ=dict(os.environ)))
    def execute(command, **kwargs):
        calls.append((command, kwargs))
        if mode == "timeout": raise subprocess.TimeoutExpired(command, 600)
        return SimpleNamespace(returncode=7 if mode == "failure" else 0)
    monkeypatch.setattr(run_research, "subprocess", SimpleNamespace(run=execute, check_output=lambda *args, **kwargs: "RESEARCH_HEAD\n",
                                                                 STDOUT=subprocess.STDOUT, TimeoutExpired=subprocess.TimeoutExpired))
    monkeypatch.setattr(sys, "argv", ["run_research", "--source", str(tmp_path / "source"), "--output", str(tmp_path / "out")])
    result = run_research.main()
    facts = json.loads((tmp_path / "out/summary.json").read_text())
    if mode.startswith("wrong_"):
        assert result == 2 and not calls and facts["status"] == "SOURCE_OR_PLATFORM_MISMATCH"
    else:
        assert result == {"failure": 7, "timeout": 124, "drift": 2}[mode]
        assert len(calls) == 1 and calls[0][1]["timeout"] == 600
        command = calls[0][0]
        assert "tests/unit" not in command and "faulthandler_timeout=90" in command
        assert tuple(value for value in command if value.startswith("tests/unit/")) == run_research.MODULES
        assert command.count("stage_observer") == 1 and command.count("fleet_source_progress") == 1
        assert facts["exit_code"] == (7 if mode == "failure" else 124 if mode == "timeout" else 0)
        assert facts["status"] == "FAIL" and facts["retries"] == 0
