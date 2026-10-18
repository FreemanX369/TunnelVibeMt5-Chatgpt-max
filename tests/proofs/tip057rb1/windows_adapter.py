"""Narrow research-only argv adapter over the byte-frozen Q1 boundary.

Only the harmless compiled stub is currently launchable; no real SDK effect runner.
"""
from __future__ import annotations

import ctypes as C
import hashlib
import os
import shutil
import subprocess
import sys
from ctypes import wintypes as W
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tip057rq"))
from windows_boundary import (Boundary, Process, STARTUPINFOEX, PROCESS_INFORMATION,
                              SECURITY_CAPABILITIES, STARTUPINFO, SIZE, P, require)

HERE = Path(__file__).resolve().parent
STUB_SOURCE_SHA256 = "5ba0f5a8267555275e7428d45ca13b9a8d256d2b3e00297e83be25ee6056da45"
_COMPILE_TOKEN = object()


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CompiledHarmlessStub:
    """Research provenance from compiling the fixed source, not caller qualification."""
    def __init__(self, executable, token):
        if token is not _COMPILE_TOKEN:
            raise RuntimeError("FIXED_SOURCE_COMPILATION_REQUIRED")
        self.executable = Path(executable)
        self.sha256 = _sha(executable)
        self.source_sha256 = STUB_SOURCE_SHA256

    def verify(self, executable):
        if (_sha(HERE / "fixture_stub.c") != STUB_SOURCE_SHA256
                or _sha(executable) != self.sha256):
            raise RuntimeError("HARMLESS_STUB_BYTES_CHANGED")

    def stage(self, root):
        self.verify(self.executable)
        target = Path(root) / "stub.exe"
        if target.exists():
            raise RuntimeError("FRESH_HARMLESS_STUB_PATH_REQUIRED")
        shutil.copy2(self.executable, target)
        self.verify(target)


def compile_stub(output):
    """Only fixed harmless C source can mint a fixture artifact in this harness."""
    if os.name != "nt" or _sha(HERE / "fixture_stub.c") != STUB_SOURCE_SHA256:
        raise RuntimeError("PINNED_STUB_REAL_WINDOWS_REQUIRED")
    output = Path(output)
    installer = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
    found = subprocess.check_output([str(installer), "-latest", "-products", "*", "-requires",
        "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], text=True).strip()
    if not found:
        raise RuntimeError("REQUIRED_WINDOWS_C_COMPILER_UNAVAILABLE")
    executable, batch = output / "compiled-stub.exe", output / "compile-stub.cmd"
    vcvars = Path(found) / "VC/Auxiliary/Build/vcvars64.bat"
    batch.write_text(f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\n'
        f'cl /nologo /W4 /WX /MT /O2 /Fe:"{executable}" /Fo:"{output / "stub.obj"}" "{HERE / "fixture_stub.c"}" advapi32.lib\n'
        'exit /b %errorlevel%\n', encoding="utf-8")
    built = subprocess.run(f'cmd.exe /d /s /c ""{batch}""', capture_output=True, text=True, timeout=45)
    (output / "compiler.log").write_text((built.stdout + built.stderr)[-64000:], encoding="utf-8")
    if built.returncode:
        raise RuntimeError("STUB_COMPILATION_FAILED")
    return CompiledHarmlessStub(executable, _COMPILE_TOKEN)


class BoundReadProcess(Process):
    def verify_observation(self, observation, *, require_live=True):
        created, actual = self.identity(), observation.identity()
        if ((require_live and (observation.exited() or self.exited()))
                or actual != {"pid": created["pid"], "creation": str(created["creation_100ns"]),
                              "image": os.path.normcase(os.path.realpath(created["image"]))}):
            raise RuntimeError("CREATED_PROCESS_LIFETIME_MISMATCH")

    def allow_resume(self, authority, expected, observation):
        self.verify_observation(observation)
        actual = observation.identity()
        if (authority.load() != expected or expected["phase"] != "BOUND"
                or actual != expected["worker"]):
            raise RuntimeError("DURABLE_BIND_REQUIRED")
        self._resume_authority, self._resume_expected, self._resume_observation = authority, dict(expected), observation

    def resume(self):
        authority = getattr(self, "_resume_authority", None)
        if authority is None or authority.load() != self._resume_expected:
            raise RuntimeError("DURABLE_BIND_REQUIRED")
        self.verify_observation(self._resume_observation)
        super().resume()


class StubBoundary(Boundary):
    def __init__(self, root, artifact):
        if not isinstance(artifact, CompiledHarmlessStub):
            raise RuntimeError("FIXED_SOURCE_COMPILATION_REQUIRED")
        artifact.stage(root)
        self.artifact = artifact
        super().__init__(root)

    def assert_harmless_artifact(self):
        self.artifact.verify(self.root / "stub.exe")

    def _restriction_observation(self, process):
        kernel = self.windows.kernel
        kernel.GetProcessMitigationPolicy.argtypes = [W.HANDLE, C.c_int, P, SIZE]
        kernel.GetProcessMitigationPolicy.restype = W.BOOL
        flags = W.DWORD()
        require(kernel.GetProcessMitigationPolicy(process.handle, 13, C.byref(flags), C.sizeof(flags)))
        token = self.windows.token_observation(process.handle)
        return {"token": token, "child_policy_flags": flags.value,
                "no_child_creation": bool(flags.value & 1),
                "source": "GetProcessMitigationPolicy_AND_OpenProcessToken_ACTUAL_SUSPENDED_HANDLE"}

    def spawn_stub(self, executable, request, output, seed, *, mode="normal", restricted=True):
        if mode not in {"normal", "hang", "noresult"}:
            raise ValueError("STUB_MODE_INVALID")
        paths = [Path(path).resolve() for path in (executable, request, output, seed)]
        if any(path.parent != self.root for path in paths) or paths[0].name != "stub.exe":
            raise ValueError("OWNED_FLAT_FIXTURE_PATHS_REQUIRED")
        self.assert_harmless_artifact()
        attributes, initialized, process = None, False, None
        startup, size = STARTUPINFOEX(), SIZE()
        startup.startup.cb = C.sizeof(startup) if restricted else C.sizeof(STARTUPINFO)
        capabilities, policy = SECURITY_CAPABILITIES(self.sid, None, 0, 0), W.DWORD(1)
        try:
            if restricted:
                self.windows.kernel.InitializeProcThreadAttributeList(None, 2, 0, C.byref(size))
                attributes = C.create_string_buffer(size.value)
                require(self.windows.kernel.InitializeProcThreadAttributeList(attributes, 2, 0, C.byref(size)))
                initialized = True
                startup.attributes = C.cast(attributes, P)
                require(self.windows.kernel.UpdateProcThreadAttribute(attributes, 0, 0x20009,
                    C.byref(capabilities), C.sizeof(capabilities), None, None))
                require(self.windows.kernel.UpdateProcThreadAttribute(attributes, 0, 0x2000E,
                    C.byref(policy), C.sizeof(policy), None, None))
            command = C.create_unicode_buffer(subprocess.list2cmdline(
                [str(paths[0]), str(paths[1]), str(paths[2]), str(paths[3]), mode]))
            info = PROCESS_INFORMATION()
            # Inherited console matches qualified Q1. No handles inherited, no shell.
            flags = 0x4 | (0x80000 if restricted else 0)
            require(self.windows.kernel.CreateProcessW(str(paths[0]), command, None, None, False,
                flags, None, str(self.root), C.byref(startup), C.byref(info)))
            process = BoundReadProcess(self.windows, info.process, info.thread)
            process.identity()  # Live image captured before any execution/possible exit.
            process.restrictions = self._restriction_observation(process)
            if restricted and (process.restrictions["token"]["appcontainer"] != 1
                               or process.restrictions["token"]["integrity_sid"] != "S-1-16-4096"
                               or not process.restrictions["no_child_creation"]):
                raise RuntimeError("RESTRICTION_READBACK_UNPROVEN")
            return process
        except BaseException:
            if process is not None:
                try:
                    # Creation-returned owned handle is exact even if image readback
                    # failed. Do not fabricate identity, and never kill via a PID lookup.
                    if not process.exited():
                        require(self.windows.kernel.TerminateProcess(process.handle, 92))
                    process.wait(5000)
                finally:
                    process.close()
            raise
        finally:
            if initialized:
                self.windows.kernel.DeleteProcThreadAttributeList(attributes)
