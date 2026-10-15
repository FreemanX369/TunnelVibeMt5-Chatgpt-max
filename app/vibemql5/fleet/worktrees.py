"""Registered Git source worktrees under the existing verified node writer.

Git commits remain isolated source references. They never update the main checkout,
authoritative project session, terminal source or native qualification.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from functools import wraps

from ..core.concurrency import ConcurrencyManager

from ..core.jobs import _atomic_write_json, _exclusive_file_lock
from ..core.revisions import _atomic_write_bytes
from .job_journal import canonical, digest
from .project_targets import read_blob
from .wire import decode_body
from .writers import NodeCommand, NodePrincipalRuntime
from .principals import command_body, verify_envelope, COMMAND_DOMAIN

PATHS = {"/fleet/v1/worktrees/prepare": "worktree_create",
         "/fleet/v1/worktrees/commit": "worktree_commit",
         "/fleet/v1/worktrees/retire": "worktree_retire"}
OWNER_FIELDS = ("principal_id", "principal_epoch", "principal_session_id", "assignment_epoch", "writer_epoch", "target")


class WorktreeError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _finite(method):
    @wraps(method)
    def call(*args, **kwargs):
        try: return method(*args, **kwargs)
        except WorktreeError: raise
        except Exception: raise WorktreeError("WORKTREE_STATE_UNPROVEN") from None
    return call


def _identifier(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value) is None:
        raise WorktreeError("WORKTREE_INPUT_INVALID")
    return value


def _sha(value, *, git=False):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{" + ("40" if git else "64") + r"}", value) is None:
        raise WorktreeError("WORKTREE_INPUT_INVALID")
    return value


def _relative(value):
    if (type(value) is not str or not 1 <= len(value) <= 512 or "\\" in value or ":" in value
            or value.startswith("/") or any(ord(c) < 32 for c in value)
            or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise WorktreeError("WORKTREE_PATH_INVALID")
    reserved = {".git", ".gitmodules", ".gitattributes", ".gitconfig", ".env", "config", "state", "credentials", "secrets"}
    if any(p.casefold() in reserved or p.casefold().startswith(".git") for p in value.split("/")) or Path(value).suffix.casefold() in {".key", ".pem", ".pfx", ".p12"}:
        raise WorktreeError("WORKTREE_PATH_INVALID")
    return value


def _path(value, *, must_exist=True):
    path = Path(value)
    if not path.is_absolute(): raise WorktreeError("WORKTREE_PATH_INVALID")
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.stat(), "st_file_attributes", 0) & 0x400):
            raise WorktreeError("WORKTREE_PATH_INVALID")
    try: resolved = path.resolve(strict=must_exist)
    except OSError: raise WorktreeError("WORKTREE_PATH_INVALID") from None
    if os.path.normcase(str(path)) != os.path.normcase(str(resolved)):
        raise WorktreeError("WORKTREE_PATH_INVALID")
    return resolved


@dataclass(frozen=True)
class WorktreePolicy:
    max_worktrees: int
    max_operations: int
    max_changes: int
    max_change_bytes: int
    max_payload_bytes: int
    max_git_output_bytes: int
    git_timeout_ms: int
    wait_ms: int

    def __post_init__(self):
        bounds = {"max_worktrees": 4096, "max_operations": 65536, "max_changes": 128,
                  "max_change_bytes": 1048576, "max_payload_bytes": 4194304,
                  "max_git_output_bytes": 1048576, "git_timeout_ms": 60000, "wait_ms": 60000}
        if any(type(getattr(self, k)) is not int or not 1 <= getattr(self, k) <= maximum for k, maximum in bounds.items()):
            raise WorktreeError("WORKTREE_POLICY_INVALID")


class NodeWorktrees:
    def __init__(self, root, *, principals, repositories, worktree_root, git_executable,
                 policy, initialize=False, fault=None):
        if type(principals) is not NodePrincipalRuntime or type(policy) is not WorktreePolicy or type(initialize) is not bool:
            raise WorktreeError("WORKTREE_AUTHORITY_INVALID")
        policy.__post_init__()
        self.root, self.principals, self.policy, self.fault = _path(root), principals, policy, fault
        if self.root != principals.root: raise WorktreeError("WORKTREE_AUTHORITY_INVALID")
        self.git = _path(git_executable)
        if not self.git.is_file(): raise WorktreeError("WORKTREE_PATH_INVALID")
        self.worktree_root = _path(worktree_root, must_exist=False)
        control = self.root / "state"
        if (self.worktree_root == self.root or self.worktree_root in self.root.parents
                or self.worktree_root == control or control in self.worktree_root.parents
                or self.git == self.worktree_root or self.worktree_root in self.git.parents):
            raise WorktreeError("WORKTREE_CONFIG_INVALID")
        if type(repositories) is not dict or not 1 <= len(repositories) <= policy.max_worktrees:
            raise WorktreeError("WORKTREE_CONFIG_INVALID")
        self.repositories = {}
        for project, row in repositories.items():
            _identifier(project)
            if type(row) is not dict or set(row) != {"repository", "base_commit", "source_paths"}:
                raise WorktreeError("WORKTREE_CONFIG_INVALID")
            repo, baseline = _path(row["repository"]), _sha(row["base_commit"], git=True)
            if (repo == self.worktree_root or repo in self.worktree_root.parents or self.worktree_root in repo.parents
                    or repo == self.root or self.root in repo.parents and "state" in repo.relative_to(self.root).parts):
                raise WorktreeError("WORKTREE_CONFIG_INVALID")
            if repo == self.git or repo in self.git.parents: raise WorktreeError("WORKTREE_CONFIG_INVALID")
            sources = row["source_paths"]
            if type(sources) not in (list, tuple) or not 1 <= len(sources) <= policy.max_changes:
                raise WorktreeError("WORKTREE_CONFIG_INVALID")
            sources = [_relative(p) for p in sources]
            if len({p.casefold() for p in sources}) != len(sources): raise WorktreeError("WORKTREE_CONFIG_INVALID")
            self.repositories[project] = {"repository": str(repo), "base_commit": baseline, "source_paths": sources}
        self.path = self.root / "state" / "fleet" / "worktrees.json"
        self.hooks = self.path.parent / "disabled-git-hooks"
        _path(self.path.parent, must_exist=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.hooks.mkdir(exist_ok=True)
        self.worktree_root.mkdir(parents=True, exist_ok=True)
        _path(self.hooks); _path(self.worktree_root)
        self.config = {"repositories": self.repositories, "worktree_root": str(self.worktree_root), "git": str(self.git),
            "device_id": principals.device_id, "route_generation": principals.route_generation,
            "session_id": principals.session_id, "gateway_public_key": principals.key.hex()}
        self._mutex = threading.RLock()
        self._lock = _exclusive_file_lock(self.path.with_suffix(".owner.lock"), timeout_seconds=policy.wait_ms / 1000)
        self._lock.__enter__()
        try:
            for project, registered in self.repositories.items(): self._repository(registered)
            if initialize:
                if self.path.exists(): raise WorktreeError("WORKTREE_STORE_EXISTS")
                self.state = {"schema": "fleet.worktrees/1", "policy": asdict(policy), "config": self.config,
                              "worktrees": {}, "operations": {}}
                self._publish("initialize")
            else:
                self.state = self._read(); self._validate()
        except BaseException:
            self.close(); raise

    def close(self):
        with self._mutex:
            if self._lock is not None:
                self._lock.__exit__(None, None, None); self._lock = None

    def _guard(self):
        if self._lock is None: raise WorktreeError("WORKTREE_CLOSED")

    def _hooks_disabled(self):
        _path(self.hooks)
        if not self.hooks.is_dir() or any(self.hooks.iterdir()):
            raise WorktreeError("GIT_HOOKS_UNSUPPORTED")

    def _argv(self, directory, arguments):
        return [str(self.git), "--no-pager", "-c", "core.hooksPath=" + str(self.hooks), "-c", "core.fsmonitor=false",
                "-c", "commit.gpgsign=false", "-c", "gc.auto=0", "-c", "maintenance.auto=false",
                "-c", "core.attributesFile=" + os.devnull, "-c", "core.autocrlf=false", "-c", "core.safecrlf=false",
                "-c", "user.name=Fleet Node", "-c", "user.email=fleet@localhost", "-C", str(directory), *arguments]

    @staticmethod
    def _purpose_arguments(purpose, body, request, row):
        if purpose == "create": return ["worktree", "add", "--detach", row["path"], row["base_commit"]]
        if purpose == "retire": return ["worktree", "remove", row["path"]]
        if purpose == "stage": return ["add", "--", *[change["path"] for change in request["changes"]]]
        if purpose == "write_tree": return ["write-tree"]
        message = request["message"] + "\n\nFleet-Intent: " + body["intent_sha256"] + "\nFleet-Owner: " + digest({k: body[k] for k in OWNER_FIELDS})
        return ["commit", "-m", message]

    def _git(self, directory, *arguments, allowed=(0,), retain_completion=False):
        """Fixed structured argv, capped output and exact retained process teardown."""
        _path(directory); self._hooks_disabled()
        environment = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=os.devnull,
            GIT_ATTR_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0", GIT_PAGER="cat", GIT_NO_REPLACE_OBJECTS="1")
        argv = self._argv(directory, arguments)
        process, output, overflow, reader_error = None, bytearray(), threading.Event(), []
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, env=environment, shell=False, bufsize=0)
            def read():
                try:
                    while True:
                        part = process.stdout.read(65536)
                        if not part: break
                        if len(output) + len(part) > self.policy.max_git_output_bytes:
                            overflow.set(); process.kill(); break
                        output.extend(part)
                except Exception: reader_error.append(True)
            reader = threading.Thread(target=read, daemon=True); reader.start()
            try: code = process.wait(self.policy.git_timeout_ms / 1000)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
                raise WorktreeError("GIT_EXECUTION_UNPROVEN") from None
            reader.join(timeout=5)
            if reader.is_alive() or overflow.is_set() or reader_error: raise WorktreeError("GIT_OUTPUT_UNPROVEN")
            if code not in allowed: raise WorktreeError("GIT_OPERATION_FAILED")
            completed = (bytes(output), code, {"pid": process.pid, "argv_sha256": digest(argv), "returncode": code})
        except (OSError, subprocess.SubprocessError):
            raise WorktreeError("GIT_EXECUTION_UNPROVEN") from None
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=5)
                if process.stdout is not None: process.stdout.close()
        return completed if retain_completion else completed[:2]

    def _mutating_git(self, command, operation, directory, purpose, *arguments):
        """A missing durable owned-process closure can never be inferred from Git state."""
        body = command.body
        step = {"schema": "fleet.git-completion/1", "purpose": purpose, "operation_id": body["operation_id"],
                "intent_sha256": body["intent_sha256"], "phase": operation["phase"],
                "arguments_sha256": digest(list(arguments)), "status": "ATTEMPTED",
                "pid": None, "argv_sha256": None, "returncode": None, "head": None, "tree": None}
        operation["git_steps"].append(step); self._publish("git_attempt")
        raw, code, observed = self._git(directory, *arguments, retain_completion=True)
        row = self.state["worktrees"][command.request["worktree_id"]]
        if purpose != "retire":
            target = Path(row["path"]); head = self._head(target)
            tree = _sha(raw.decode("ascii").strip(), git=True) if purpose == "write_tree" else _sha(self._text(target, "rev-parse", "HEAD^{tree}"), git=True)
        else: head, tree = None, None
        step.update(status="CLOSED", head=head, tree=tree, **observed)
        self._publish("git_closed")
        return raw, code

    def _text(self, directory, *arguments):
        raw, _ = self._git(directory, *arguments)
        try: return raw.decode("utf-8").strip()
        except UnicodeError: raise WorktreeError("GIT_OUTPUT_UNPROVEN") from None

    def _repository(self, registered):
        repo = _path(registered["repository"])
        if self._text(repo, "rev-parse", "--is-bare-repository") != "false" or _path(self._text(repo, "rev-parse", "--show-toplevel")) != repo:
            raise WorktreeError("WORKTREE_REPOSITORY_INVALID")
        _path(repo / ".git")
        if not (repo / ".git").is_dir(): raise WorktreeError("WORKTREE_REPOSITORY_INVALID")
        raw, _ = self._git(repo, "config", "--local", "--no-includes", "--get-regexp",
            r"^(include\.path|includeif\..*\.path|extensions\.worktreeconfig)$", allowed=(0, 1))
        if raw: raise WorktreeError("GIT_CONFIG_UNSUPPORTED")
        raw, _ = self._git(repo, "config", "--local", "--includes", "--get-regexp", r"^filter\..*\.(clean|smudge|process|required)$", allowed=(0, 1))
        if raw: raise WorktreeError("GIT_FILTER_UNSUPPORTED")
        if any((repo / ".git" / relative).exists() for relative in ("info/grafts", "info/attributes", "objects/info/alternates", "config.worktree")):
            raise WorktreeError("GIT_CONFIG_UNSUPPORTED")
        if self._text(repo, "cat-file", "-t", registered["base_commit"]) != "commit":
            raise WorktreeError("WORKTREE_BASE_INVALID")
        tree = self._text(repo, "ls-tree", "-r", registered["base_commit"])
        if any(row.startswith("160000 ") or row.split("\t", 1)[-1].split("/")[-1] == ".gitmodules" for row in tree.splitlines()):
            raise WorktreeError("GIT_SUBMODULE_UNSUPPORTED")
        if any(row.startswith("120000 ") or row.split("\t", 1)[-1].split("/")[-1] == ".gitattributes" for row in tree.splitlines()):
            raise WorktreeError("GIT_ATTRIBUTES_UNSUPPORTED")
        for relative in registered["source_paths"]:
            row = self._text(repo, "ls-tree", registered["base_commit"], "--", relative)
            if not re.fullmatch(r"100(?:644|755) blob [a-f0-9]{40}\t" + re.escape(relative), row):
                raise WorktreeError("WORKTREE_SOURCE_UNREGISTERED")
        return repo

    def _read(self):
        try:
            value = decode_body(read_blob(self.path, self.policy.max_payload_bytes), self.policy.max_payload_bytes)
            if value.pop("record_sha256") != digest(value): raise ValueError()
            return value
        except Exception: raise WorktreeError("WORKTREE_STORE_INVALID") from None

    @_finite
    def _validate(self):
        value = self.state
        if (type(value) is not dict or set(value) != {"schema", "policy", "config", "worktrees", "operations"}
                or value["schema"] != "fleet.worktrees/1" or canonical(value["policy"]) != canonical(asdict(self.policy)) or canonical(value["config"]) != canonical(self.config)
                or type(value["worktrees"]) is not dict or len(value["worktrees"]) > self.policy.max_worktrees
                or type(value["operations"]) is not dict or len(value["operations"]) > self.policy.max_operations):
            raise WorktreeError("WORKTREE_STORE_INVALID")
        for identifier, row in value["worktrees"].items():
            if (type(row) is not dict or set(row) != {"project_id", "worktree_id", "path", "base_commit", "head", "owner", "state"}
                    or row["worktree_id"] != identifier or row["project_id"] not in self.repositories
                    or row["state"] not in {"PREPARING", "ACTIVE", "RETIRED", "UNKNOWN"}):
                raise WorktreeError("WORKTREE_STORE_INVALID")
            _identifier(identifier); _sha(row["base_commit"], git=True); _sha(row["head"], git=True)
            if (row["path"] != str(self.worktree_root / row["project_id"] / identifier) or type(row["owner"]) is not dict or set(row["owner"]) != set(OWNER_FIELDS)
                    or row["base_commit"] != self.repositories[row["project_id"]]["base_commit"]):
                raise WorktreeError("WORKTREE_STORE_INVALID")
        for intent, row in value["operations"].items():
            _sha(intent)
            if (type(row) is not dict or set(row) != {"command", "body", "request", "phase", "state", "before_head", "tree", "receipt", "git_steps"}
                    or type(row["body"]) is not dict or type(row["request"]) is not dict
                    or row["body"].get("intent_sha256") != intent or row["phase"] not in PATHS.values()
                    or row["state"] not in {"INTENT", "FILES_WRITTEN", "COMMIT_READY", "EFFECT_DONE", "COMMITTED", "UNKNOWN"}
                    or row["request"].get("worktree_id") not in value["worktrees"]):
                raise WorktreeError("WORKTREE_STORE_INVALID")
            body = command_body(verify_envelope(row["command"], self.principals.key, COMMAND_DOMAIN))
            wrapper = {"schema": "fleet.domain-request/1", "node": {"device_id": self.principals.device_id, "route_generation": self.principals.route_generation},
                       "operation_id": body["operation_id"], "payload": row["request"]}
            worktree = value["worktrees"][row["request"]["worktree_id"]]
            if (body != row["body"] or body["path"] not in PATHS or PATHS[body["path"]] != row["phase"]
                    or body["audience"] != self.principals.audience or body["payload_sha256"] != digest({"path": body["path"], "payload": wrapper})
                    or body["project_id"] != worktree["project_id"] or row["request"].get("project_id") != body["project_id"]
                    or canonical(worktree["owner"]) != canonical({k: body[k] for k in OWNER_FIELDS})):
                raise WorktreeError("WORKTREE_STORE_INVALID")
            _sha(row["before_head"], git=True)
            if row["tree"] is not None: _sha(row["tree"], git=True)
            if (row["state"] in {"EFFECT_DONE", "COMMITTED"}) != (type(row["receipt"]) is dict):
                raise WorktreeError("WORKTREE_STORE_INVALID")
            if type(row["git_steps"]) is not list or len(row["git_steps"]) > 3:
                raise WorktreeError("WORKTREE_STORE_INVALID")
            purposes = {"worktree_create": ["create"], "worktree_retire": ["retire"], "worktree_commit": ["stage", "write_tree", "commit"]}[row["phase"]]
            for index, step in enumerate(row["git_steps"]):
                if (type(step) is not dict or set(step) != {"schema", "purpose", "operation_id", "intent_sha256", "phase", "arguments_sha256", "status", "pid", "argv_sha256", "returncode", "head", "tree"}
                        or step["schema"] != "fleet.git-completion/1" or index >= len(purposes) or step["purpose"] != purposes[index]
                        or any(step[k] != body[k] for k in ("operation_id", "intent_sha256")) or step["phase"] != row["phase"]
                        or step["status"] not in {"ATTEMPTED", "CLOSED"}):
                    raise WorktreeError("WORKTREE_STORE_INVALID")
                arguments = self._purpose_arguments(step["purpose"], body, row["request"], worktree)
                if step["arguments_sha256"] != digest(arguments): raise WorktreeError("WORKTREE_STORE_INVALID")
                if step["status"] == "ATTEMPTED":
                    if index != len(row["git_steps"]) - 1 or any(step[k] is not None for k in ("pid", "argv_sha256", "returncode", "head", "tree")):
                        raise WorktreeError("WORKTREE_STORE_INVALID")
                else:
                    if type(step["pid"]) is not int or step["pid"] <= 0 or type(step["returncode"]) is not int or step["returncode"] != 0:
                        raise WorktreeError("WORKTREE_STORE_INVALID")
                    directory = self.repositories[body["project_id"]]["repository"] if step["purpose"] in {"create", "retire"} else worktree["path"]
                    if step["argv_sha256"] != digest(self._argv(directory, arguments)): raise WorktreeError("WORKTREE_STORE_INVALID")
                    if step["purpose"] == "retire":
                        if step["head"] is not None or step["tree"] is not None: raise WorktreeError("WORKTREE_STORE_INVALID")
                    else: _sha(step["head"], git=True); _sha(step["tree"], git=True)
            if row["state"] in {"EFFECT_DONE", "COMMITTED"} and (len(row["git_steps"]) != len(purposes) or any(step["status"] != "CLOSED" for step in row["git_steps"])):
                raise WorktreeError("WORKTREE_STORE_INVALID")
            authority_phase = self.principals.state["phases"].get(digest({"intent_sha256": intent, "phase": row["phase"]}))
            if row["state"] == "COMMITTED" and (authority_phase is None or authority_phase["state"] != "COMMITTED"):
                raise WorktreeError("WORKTREE_STORE_INVALID")
            if authority_phase is not None and authority_phase["state"] == "COMMITTED" and canonical(authority_phase["receipt"]) != canonical(row["receipt"]):
                raise WorktreeError("WORKTREE_STORE_INVALID")
            if row["receipt"] is not None:
                receipt = row["receipt"]
                fields = {"schema", "project_id", "worktree_id", "operation_id", "intent_sha256", "principal_id", "writer_epoch", "base_commit", "head", "tree", "state", "source_ref", "result_ref", "result_reference_status"}
                if (set(receipt) != fields or receipt["schema"] != "fleet.worktree.receipt/1"
                        or any(canonical(receipt[k]) != canonical(body[k]) for k in ("project_id", "operation_id", "intent_sha256", "principal_id", "writer_epoch"))
                        or receipt["worktree_id"] != worktree["worktree_id"] or receipt["base_commit"] != worktree["base_commit"]
                        or receipt["state"] != ("RETIRED" if row["phase"] == "worktree_retire" else "ACTIVE")
                        or receipt["source_ref"] != row["request"].get("source_ref") or receipt["result_ref"] != row["request"].get("result_ref")
                        or receipt["result_reference_status"] != ("UNVERIFIED_REFERENCE_ONLY" if receipt["result_ref"] is not None else None)):
                    raise WorktreeError("WORKTREE_STORE_INVALID")
                _sha(receipt["head"], git=True)
                if receipt["tree"] is not None: _sha(receipt["tree"], git=True)
        for identifier, worktree in value["worktrees"].items():
            related = [op for op in value["operations"].values() if op["request"]["worktree_id"] == identifier]
            if sum(op["phase"] == "worktree_create" for op in related) != 1:
                raise WorktreeError("WORKTREE_STORE_INVALID")

    def _publish(self, point):
        try:
            self._validate()
            if len(canonical(self.state)) > self.policy.max_payload_bytes: raise WorktreeError("WORKTREE_CAPACITY")
            if self.fault: self.fault(point + ":before_commit")
            _atomic_write_json(self.path, {**self.state, "record_sha256": digest(self.state)})
            if self.fault: self.fault(point + ":after_commit")
        except BaseException:
            if self.path.exists(): self.state = self._read()
            raise

    def _clean(self, directory):
        if self._text(directory, "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching"):
            raise WorktreeError("WORKTREE_DIRTY")

    def _head(self, directory): return _sha(self._text(directory, "rev-parse", "--verify", "HEAD"), git=True)

    @staticmethod
    def _listed_worktree_paths(raw):
        """Git's NUL porcelain is unquoted; native canonical paths handle Windows slashes/case."""
        try:
            if type(raw) is not bytes or not raw.endswith(b"\0\0"): raise ValueError()
            paths = []
            for record in raw[:-2].split(b"\0\0"):
                fields = record.split(b"\0")
                if not fields[0].startswith(b"worktree "): raise ValueError()
                paths.append(_path(fields[0][9:].decode("utf-8"), must_exist=False))
                seen = set()
                for field in fields[1:]:
                    key = field.split(b" ", 1)[0]
                    if key in seen or key not in {b"HEAD", b"branch", b"detached", b"bare", b"locked", b"prunable"}: raise ValueError()
                    seen.add(key)
                    if key == b"HEAD": _sha(field[5:].decode("ascii"), git=True)
                    elif key in {b"detached", b"bare"} and field != key: raise ValueError()
                if b"HEAD" not in seen and b"bare" not in seen: raise ValueError()
            return paths
        except (UnicodeError, TypeError, ValueError, WorktreeError): raise WorktreeError("GIT_OUTPUT_UNPROVEN") from None

    def _worktree_list(self, repo):
        raw, _ = self._git(repo, "worktree", "list", "--porcelain", "-z")
        return self._listed_worktree_paths(raw)

    def _registered_path(self, row):
        expected = self.worktree_root / row["project_id"] / row["worktree_id"]
        path = _path(expected)
        if str(path) != row["path"] or _path(self._text(path, "rev-parse", "--show-toplevel")) != path:
            raise WorktreeError("WORKTREE_PATH_INVALID")
        common = _path(self._text(path, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        if common != Path(self.repositories[row["project_id"]]["repository"]) / ".git":
            raise WorktreeError("WORKTREE_REPOSITORY_INVALID")
        return path

    def _session_ref(self, project_id, supplied):
        project = self.principals.projects.get(project_id)
        current = self.principals.projects._session(project_id, project["session"]["revision_id"], project["session"]["revision_sha256"])
        if supplied != current: raise WorktreeError("WORKTREE_SOURCE_REF_MISMATCH")
        return current

    def _receipt(self, command, row, head, tree=None):
        body, request = command.body, command.request
        return {"schema": "fleet.worktree.receipt/1", "project_id": body["project_id"], "worktree_id": row["worktree_id"],
            "operation_id": body["operation_id"], "intent_sha256": body["intent_sha256"], "principal_id": body["principal_id"], "writer_epoch": body["writer_epoch"],
            "base_commit": row["base_commit"], "head": head, "tree": tree, "state": row["state"],
            "source_ref": request.get("source_ref"), "result_ref": request.get("result_ref"),
            "result_reference_status": "UNVERIFIED_REFERENCE_ONLY" if request.get("result_ref") is not None else None}

    def apply_command(self, path, command, *, operation_id):
        with self.principals._mutex, self._mutex:
            self._guard()
            if (type(command) is not NodeCommand or command._runtime is not self.principals
                    or path not in PATHS or command.body["path"] != path or command.body["operation_id"] != operation_id):
                raise WorktreeError("WORKTREE_AUTHORITY_INVALID")
            self.principals._command(command)
            body, request = command.body, command.request
            verified = command_body(verify_envelope(json.loads(command._body), self.principals.key, COMMAND_DOMAIN))
            wrapper = {"schema": "fleet.domain-request/1", "node": {"device_id": self.principals.device_id, "route_generation": self.principals.route_generation},
                       "operation_id": operation_id, "payload": request}
            if (canonical(verified) != canonical(body) or type(request) is not dict
                    or body["audience"] != self.principals.audience or body["payload_sha256"] != digest({"path": path, "payload": wrapper})):
                raise WorktreeError("WORKTREE_AUTHORITY_INVALID")
            _identifier(request.get("project_id")); identifier = _identifier(request.get("worktree_id"))
            if request["project_id"] != body["project_id"] or body["project_id"] not in self.repositories:
                raise WorktreeError("WORKTREE_PROJECT_UNREGISTERED")
            registered = self.repositories[body["project_id"]]
            repo = self._repository(registered)
            owner = {k: body[k] for k in OWNER_FIELDS}
            intent, phase = body["intent_sha256"], PATHS[path]
            old = self.state["operations"].get(intent)
            if old is not None:
                if old["body"] != body or old["request"] != request: raise WorktreeError("WORKTREE_OPERATION_CONFLICT")
                if old["state"] == "COMMITTED":
                    return {**old["receipt"], "writer_acks": self.principals.writer_acks(command), "idempotent_recovered": True}
                return self._recover(command, old)
            if any(row["body"]["project_id"] == body["project_id"] and row["state"] != "COMMITTED" for row in self.state["operations"].values()):
                raise WorktreeError("WORKTREE_RECONCILIATION_REQUIRED")
            if len(self.state["operations"]) >= self.policy.max_operations: raise WorktreeError("WORKTREE_CAPACITY")
            row = self.state["worktrees"].get(identifier)
            if path.endswith("prepare"):
                if set(request) != {"project_id", "worktree_id", "base_commit"} or request["base_commit"] != registered["base_commit"]:
                    raise WorktreeError("WORKTREE_BASE_MISMATCH")
                if row is not None or len(self.state["worktrees"]) >= self.policy.max_worktrees: raise WorktreeError("WORKTREE_REFERENCE_EXISTS")
                if self._head(repo) != request["base_commit"]: raise WorktreeError("WORKTREE_HEAD_DRIFT")
                self._clean(repo)
                target = self.worktree_root / body["project_id"] / identifier
                _path(target, must_exist=False)
                if target.exists(): raise WorktreeError("WORKTREE_PATH_EXISTS")
                row = {"project_id": body["project_id"], "worktree_id": identifier, "path": str(target),
                    "base_commit": request["base_commit"], "head": request["base_commit"], "owner": owner, "state": "PREPARING"}
                self.state["worktrees"][identifier] = row
            else:
                if row is None or row["project_id"] != body["project_id"] or row["owner"] != owner or row["state"] != "ACTIVE":
                    raise WorktreeError("WORKTREE_OWNER_MISMATCH")
                target = self._registered_path(row)
                if request.get("expected_head") != row["head"] or self._head(target) != row["head"]:
                    raise WorktreeError("WORKTREE_HEAD_DRIFT")
                self._clean(target)
                if path.endswith("retire"):
                    if set(request) != {"project_id", "worktree_id", "expected_head"}: raise WorktreeError("WORKTREE_INPUT_INVALID")
                else:
                    self._commit_input(command, registered, target)
            operation = {"command": json.loads(command._body), "body": body, "request": request, "phase": phase, "state": "INTENT",
                         "before_head": row["head"], "tree": None, "receipt": None, "git_steps": []}
            self.state["operations"][intent] = operation
            self._publish("operation_intent")
            try:
                with self.principals.phase_guard(command, phase, intent) as fence:
                    self.principals.recheck_phase(fence)
                    if path.endswith("prepare"):
                        self._clean(repo)
                        if self._head(repo) != row["base_commit"]: raise WorktreeError("WORKTREE_HEAD_DRIFT")
                        project = self.principals.projects.get(body["project_id"])
                        session = self._session_ref(body["project_id"], project["session"])
                        if session["ea"] not in registered["source_paths"]:
                            raise WorktreeError("WORKTREE_SOURCE_UNREGISTERED")
                        baseline, _ = self._git(repo, "show", row["base_commit"] + ":" + session["ea"])
                        if hashlib.sha256(baseline).hexdigest() != session["source_sha256"] or len(baseline) != session["source_bytes"]:
                            raise WorktreeError("WORKTREE_BASE_MISMATCH")
                        self.principals.recheck_phase(fence)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if self.fault: self.fault("create:before_effect")
                        self._mutating_git(command, operation, repo, "create", "worktree", "add", "--detach", str(target), row["base_commit"])
                        if self.fault: self.fault("create:after_effect")
                        target = self._registered_path(row); self._clean(target)
                        if self._head(target) != row["head"]: raise WorktreeError("WORKTREE_HEAD_DRIFT")
                        row["state"] = "ACTIVE"
                        receipt = self._receipt(command, row, row["head"])
                    elif path.endswith("retire"):
                        if self.fault: self.fault("retire:before_effect")
                        self._mutating_git(command, operation, repo, "retire", "worktree", "remove", str(target))
                        if self.fault: self.fault("retire:after_effect")
                        row["state"] = "RETIRED"
                        receipt = self._receipt(command, row, row["head"])
                    else:
                        receipt = self._commit(command, row, operation, registered, target, fence)
                    operation.update(state="EFFECT_DONE", receipt=receipt)
                    self._publish("effect_done")
                    self.principals.complete_phase(fence, receipt)
                operation["state"] = "COMMITTED"
                self._publish("operation_committed")
                return {**receipt, "writer_acks": self.principals.writer_acks(command), "idempotent_recovered": False}
            except BaseException:
                operation = self.state["operations"].get(intent)
                if operation is not None and operation["state"] != "COMMITTED":
                    if operation["receipt"] is None: operation["state"] = "UNKNOWN"
                    self._publish("operation_unknown")
                raise

    def _commit_input(self, command, registered, target):
        request = command.request
        if set(request) != {"project_id", "worktree_id", "expected_head", "changes", "message", "source_ref", "result_ref"}:
            raise WorktreeError("WORKTREE_INPUT_INVALID")
        message = request["message"]
        if type(message) is not str or not 1 <= len(message.encode("utf-8")) <= 512 or message != message.strip() or any(ord(c) < 32 for c in message):
            raise WorktreeError("WORKTREE_INPUT_INVALID")
        self._session_ref(command.body["project_id"], request["source_ref"])
        reference = request["result_ref"]
        if reference is not None:
            if type(reference) is not dict or set(reference) != {"reference", "sha256"}: raise WorktreeError("WORKTREE_INPUT_INVALID")
            _identifier(reference["reference"]); _sha(reference["sha256"])
        changes = request["changes"]
        if type(changes) is not list or not 1 <= len(changes) <= self.policy.max_changes: raise WorktreeError("WORKTREE_INPUT_INVALID")
        seen, total, changed = set(), 0, False
        for change in changes:
            if type(change) is not dict or set(change) != {"path", "expected_sha256", "sha256", "source_base64"}:
                raise WorktreeError("WORKTREE_INPUT_INVALID")
            relative = _relative(change["path"])
            if relative not in registered["source_paths"] or relative.casefold() in seen: raise WorktreeError("WORKTREE_SOURCE_UNREGISTERED")
            seen.add(relative.casefold())
            location = _path(target / relative, must_exist=False)
            before = hashlib.sha256(read_blob(location, self.policy.max_change_bytes)).hexdigest() if location.exists() else None
            if before != change["expected_sha256"]: raise WorktreeError("WORKTREE_SOURCE_CHANGED")
            if change["expected_sha256"] is not None: _sha(change["expected_sha256"])
            if change["source_base64"] is None:
                if change["sha256"] is not None or before is None: raise WorktreeError("WORKTREE_INPUT_INVALID")
                changed = True
            else:
                _sha(change["sha256"])
                if type(change["source_base64"]) is not str or len(change["source_base64"]) > 4 * ((self.policy.max_change_bytes + 2) // 3):
                    raise WorktreeError("WORKTREE_CAPACITY")
                try: data = base64.b64decode(change["source_base64"], validate=True)
                except Exception: raise WorktreeError("WORKTREE_INPUT_INVALID") from None
                total += len(data)
                if total > self.policy.max_change_bytes or hashlib.sha256(data).hexdigest() != change["sha256"]:
                    raise WorktreeError("WORKTREE_INPUT_INVALID")
                changed |= before != change["sha256"]
        if not changed: raise WorktreeError("WORKTREE_NO_CHANGES")

    def _message(self, command):
        body = command.body
        return command.request["message"] + "\n\nFleet-Intent: " + body["intent_sha256"] + "\nFleet-Owner: " + digest({k: body[k] for k in OWNER_FIELDS})

    def _commit(self, command, row, operation, registered, target, fence):
        self._clean(target)
        if self._head(target) != operation["before_head"]: raise WorktreeError("WORKTREE_HEAD_DRIFT")
        self._commit_input(command, registered, target)
        for change in command.request["changes"]:
            self.principals.recheck_phase(fence)
            location = _path(target / change["path"], must_exist=False)
            if self.fault: self.fault("source:before_effect")
            if change["source_base64"] is None: location.unlink()
            else:
                data = base64.b64decode(change["source_base64"], validate=True)
                mode = location.stat().st_mode & 0o777 if location.exists() else 0o644
                _atomic_write_bytes(location, data); location.chmod(mode)
            if self.fault: self.fault("source:after_effect")
        operation["state"] = "FILES_WRITTEN"; self._publish("files_written")
        self.principals.recheck_phase(fence)
        self._mutating_git(command, operation, target, "stage", "add", "--", *[c["path"] for c in command.request["changes"]])
        self.principals.recheck_phase(fence)
        raw_tree, _ = self._mutating_git(command, operation, target, "write_tree", "write-tree")
        tree = _sha(raw_tree.decode("ascii").strip(), git=True)
        names, _ = self._git(target, "diff-tree", "-z", "--no-commit-id", "--name-only", "-r", operation["before_head"], tree)
        try: changed_paths = {name.decode("utf-8") for name in names.split(b"\0") if name}
        except UnicodeError: raise WorktreeError("WORKTREE_SOURCE_CHANGED") from None
        if not changed_paths or not changed_paths <= {change["path"] for change in command.request["changes"]}:
            raise WorktreeError("WORKTREE_SOURCE_CHANGED")
        for change in command.request["changes"]:
            if change["source_base64"] is None:
                if self._text(target, "ls-tree", tree, "--", change["path"]): raise WorktreeError("WORKTREE_SOURCE_CHANGED")
            else:
                staged, _ = self._git(target, "show", tree + ":" + change["path"])
                if hashlib.sha256(staged).hexdigest() != change["sha256"]: raise WorktreeError("WORKTREE_SOURCE_CHANGED")
        operation.update(state="COMMIT_READY", tree=tree); self._publish("commit_ready")
        self.principals.recheck_phase(fence)
        self._session_ref(command.body["project_id"], command.request["source_ref"])
        if self._head(target) != operation["before_head"]: raise WorktreeError("WORKTREE_HEAD_DRIFT")
        if self.fault: self.fault("commit:before_effect")
        self._mutating_git(command, operation, target, "commit", "commit", "-m", self._message(command))
        if self.fault: self.fault("commit:after_effect")
        head = self._head(target)
        if self._text(target, "show", "-s", "--format=%P", head) != operation["before_head"] or self._text(target, "show", "-s", "--format=%T", head) != tree:
            raise WorktreeError("WORKTREE_COMMIT_UNPROVEN")
        self._clean(target); row["head"] = head
        return self._receipt(command, row, head, tree)

    def _recover(self, command, operation):
        project = self.principals.projects.get(command.body["project_id"])
        resource = project["session"]["workspace"] + ":" + project["session"]["ea"]
        with ConcurrencyManager(self.root).mutation("fleet_source_guard", resource=resource, wait_seconds=0):
            return self._recover_locked(command, operation)

    def _recover_locked(self, command, operation):
        row = self.state["worktrees"][command.request["worktree_id"]]
        if row["owner"] != {k: command.body[k] for k in OWNER_FIELDS}: raise WorktreeError("WORKTREE_OWNER_MISMATCH")
        phase = operation["phase"]
        purposes = {"worktree_create": ["create"], "worktree_retire": ["retire"], "worktree_commit": ["stage", "write_tree", "commit"]}[phase]
        steps = operation["git_steps"]
        if len(steps) != len(purposes) or any(step["status"] != "CLOSED" for step in steps):
            raise WorktreeError("WORKTREE_GIT_CLOSURE_UNPROVEN")
        final = steps[-1]
        repo = Path(self.repositories[row["project_id"]]["repository"])
        if phase == "worktree_create":
            target = self._registered_path(row)
            self._clean(target)
            if self._head(target) != operation["before_head"] or final["head"] != operation["before_head"]:
                raise WorktreeError("WORKTREE_RECONCILIATION_REQUIRED")
            row["state"] = "ACTIVE"; receipt = self._receipt(command, row, operation["before_head"])
        elif phase == "worktree_retire":
            if Path(row["path"]).exists(): raise WorktreeError("WORKTREE_RECONCILIATION_REQUIRED")
            if _path(row["path"], must_exist=False) in self._worktree_list(repo):
                raise WorktreeError("WORKTREE_RECONCILIATION_REQUIRED")
            row["state"] = "RETIRED"; receipt = self._receipt(command, row, operation["before_head"])
        else:
            target = self._registered_path(row); self._clean(target)
            head = self._head(target)
            if (operation["tree"] is None or head == operation["before_head"] or final["head"] != head or final["tree"] != operation["tree"]
                    or self._text(target, "show", "-s", "--format=%P", head) != operation["before_head"]
                    or self._text(target, "show", "-s", "--format=%T", head) != operation["tree"]
                    or self._text(target, "show", "-s", "--format=%B", head) != self._message(command)):
                raise WorktreeError("WORKTREE_RECONCILIATION_REQUIRED")
            row["head"] = head; receipt = self._receipt(command, row, head, operation["tree"])
        if operation["receipt"] is not None and operation["receipt"] != receipt: raise WorktreeError("WORKTREE_RECONCILIATION_REQUIRED")
        self.principals.recover_phase(command, phase, receipt)
        operation.update(state="COMMITTED", receipt=receipt); self._publish("operation_recovered")
        return {**receipt, "writer_acks": self.principals.writer_acks(command), "idempotent_recovered": True}

    def local_path(self, worktree_id):
        """Trusted owner-side inspection only; never selects an HTTP filesystem path."""
        with self._mutex:
            self._guard(); row = self.state["worktrees"].get(_identifier(worktree_id))
            if row is None or row["state"] != "ACTIVE": raise WorktreeError("WORKTREE_REFERENCE_UNKNOWN")
            return self._registered_path(row)


    @_finite
    def recovery_head(self):
        """Read-only quiescent head for the existing joint authority checkpoint."""
        with self.principals._mutex, self._mutex:
            self._guard(); self.principals._guard(); self._validate()
            if canonical(self._read()) != canonical(self.state): raise WorktreeError("WORKTREE_STORE_INVALID")
            operations, worktrees = [], []
            for intent, operation in sorted(self.state["operations"].items()):
                if operation["state"] != "COMMITTED" or any(step["status"] != "CLOSED" for step in operation["git_steps"]):
                    raise WorktreeError("WORKTREE_RECONCILIATION_REQUIRED")
                body = operation["body"]
                operations.append({"intent_sha256": intent, "operation_id": body["operation_id"],
                    "phase": operation["phase"], "worktree_id": operation["request"]["worktree_id"],
                    "command_sha256": digest(operation["command"]), "request_sha256": body["payload_sha256"],
                    "owner_sha256": digest({k: body[k] for k in OWNER_FIELDS}), "receipt_sha256": digest(operation["receipt"]),
                    "git_steps": operation["git_steps"]})
            for project, registered in sorted(self.repositories.items()):
                repo = self._repository(registered)
                if self._head(repo) != registered["base_commit"]: raise WorktreeError("WORKTREE_HEAD_DRIFT")
                self._clean(repo)
            for identifier, row in sorted(self.state["worktrees"].items()):
                related = [operation for operation in self.state["operations"].values() if operation["request"]["worktree_id"] == identifier]
                creates = [operation for operation in related if operation["phase"] == "worktree_create"]
                if len(creates) != 1 or creates[0]["receipt"]["head"] != row["base_commit"]: raise WorktreeError("WORKTREE_STORE_INVALID")
                head, remaining = row["base_commit"], [operation for operation in related if operation["phase"] == "worktree_commit"]
                while remaining:
                    successors = [operation for operation in remaining if operation["before_head"] == head]
                    if len(successors) != 1: raise WorktreeError("WORKTREE_STORE_INVALID")
                    operation = successors[0]; remaining.remove(operation); head = operation["receipt"]["head"]
                retires = [operation for operation in related if operation["phase"] == "worktree_retire"]
                if head != row["head"] or len(retires) > 1 or row["state"] != ("RETIRED" if retires else "ACTIVE"):
                    raise WorktreeError("WORKTREE_STORE_INVALID")
                if retires:
                    if retires[0]["before_head"] != head or Path(row["path"]).exists(): raise WorktreeError("WORKTREE_RECONCILIATION_REQUIRED")
                    repo = Path(self.repositories[row["project_id"]]["repository"])
                    if _path(row["path"], must_exist=False) in self._worktree_list(repo):
                        raise WorktreeError("WORKTREE_RECONCILIATION_REQUIRED")
                else:
                    path = self._registered_path(row); self._clean(path)
                    if self._head(path) != head: raise WorktreeError("WORKTREE_HEAD_DRIFT")
                worktrees.append({k: row[k] for k in ("project_id", "worktree_id", "base_commit", "head", "state")})
                worktrees[-1]["owner_sha256"] = digest(row["owner"])
            result = {"schema": "fleet.node-worktree-head/1", "sha256": digest(self.state),
                      "operations": operations, "worktrees": worktrees}
            if len(canonical(result)) > self.policy.max_payload_bytes: raise WorktreeError("WORKTREE_CAPACITY")
            return json.loads(canonical(result))
