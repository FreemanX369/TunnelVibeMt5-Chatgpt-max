"""Real Windows SDK LOAD compatibility; never installs product qualification.

Reuse the product Win32 handle/token machinery. Only a fresh disposable lab tree
gets ACL changes. No SDK initialize/terminal API, trust file, or account is used.
"""
from __future__ import annotations
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(root, name, value):
    path = root / name
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def fresh_lab(path):
    path = Path(path).absolute()
    if path.exists() or path.is_symlink():
        raise RuntimeError('FRESH_LAB_REQUIRED')
    if any(p.is_symlink() for p in path.parents):
        raise RuntimeError('LAB_REPARSE_PARENT_DENIED')
    path.mkdir(parents=True, exist_ok=False)
    return path.resolve()


def copy_tree(source, target):
    source = Path(source)
    for parent, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            if (Path(parent) / name).is_symlink():
                raise RuntimeError('RUNTIME_LINK_DENIED')
    shutil.copytree(source, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', 'site-packages', 'test', 'tests'))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, default=HERE.parents[2])
    args = parser.parse_args(argv)
    if os.name != 'nt' or sys.version_info[:3] != (3, 12, 10):
        raise RuntimeError('EXACT_WINDOWS_PYTHON_3_12_10_REQUIRED')
    if metadata.version('MetaTrader5') != '5.0.6147' or metadata.version('numpy') != '2.5.2':
        raise RuntimeError('EXACT_VPS_SDK_NUMPY_VERSIONS_REQUIRED')
    out = fresh_lab(args.output)
    summary = dict(scope='REAL_SDK_LOAD_ONLY_NOT_Q2_OR_PRODUCTION_QUALIFICATION',
                   activation='UNCHANGED_UNQUALIFIED', python=sys.version,
                   windows_build=str(sys.getwindowsversion().build), cases=[])
    source = args.source_root.resolve() / 'app/vibemql5/core/isolated_sdk.py'
    summary['source'] = {str(source): sha(source)}
    spec = importlib.util.spec_from_file_location('_q2_product_win32', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    windows = module.Windows()
    profile = 'vibemql5.q2load.' + uuid.uuid4().hex
    sid = C.c_void_p()
    result = windows.userenv.CreateAppContainerProfile(profile, profile,
        'Disposable SDK import research, no terminal calls', None, 0, C.byref(sid))
    if result < 0:
        raise RuntimeError('APP_CONTAINER_CREATE_FAILED')
    summary['profile'] = profile
    summary['profile_sid'] = windows.sid_string(sid)
    try:
        user, app = windows.user_sid(), windows.sid_string(sid)
        def acl(path, rights, *, low=False):
            path = Path(path).resolve()
            if path != out and out not in path.parents:
                raise RuntimeError('ACL_OUTSIDE_FRESH_LAB_DENIED')
            sddl = f'D:P(A;OICI;FA;;;{user})(A;OICI;FA;;;SY)(A;OICI;{rights};;;{app})'
            if low:
                sddl += 'S:(ML;;NW;;;LW)'
            descriptor = C.c_void_p()
            module.require(windows.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl, 1, C.byref(descriptor), None))
            try:
                dacl, sacl, present, defaulted = C.c_void_p(), C.c_void_p(), W.BOOL(), W.BOOL()
                module.require(windows.advapi.GetSecurityDescriptorDacl(descriptor,
                    C.byref(present), C.byref(dacl), C.byref(defaulted)))
                if low:
                    module.require(windows.advapi.GetSecurityDescriptorSacl(descriptor,
                        C.byref(present), C.byref(sacl), C.byref(defaulted)))
                code = windows.advapi.SetNamedSecurityInfoW(str(path), 1,
                    0x80000004 | (0x10 if low else 0), None, None, dacl, sacl)
                if code:
                    raise C.WinError(code)
            finally:
                windows.kernel.LocalFree(descriptor)
        acl(out, '0x1200a9')
        runtime, ipc = out / 'runtime', out / 'ipc'
        runtime.mkdir(); ipc.mkdir()
        acl(runtime, '0x1200a9')
        acl(ipc, '0x1201bf', low=True)
        save(out, 'progress.json', dict(stage='STAGE_RUNTIME'))
        base = Path(sys.base_prefix)
        for pattern in ('python.exe', 'python3.dll', 'python312.dll', 'vcruntime*.dll'):
            for file in base.glob(pattern):
                shutil.copy2(file, runtime / file.name)
        copy_tree(base / 'DLLs', runtime / 'DLLs')
        copy_tree(base / 'Lib', runtime / 'Lib')
        packages = runtime / 'Lib/site-packages'
        packages.mkdir(exist_ok=True)
        for name in ('MetaTrader5', 'numpy'):
            directory = Path(metadata.distribution(name).locate_file(name)).resolve()
            copy_tree(directory, packages / name)
            libraries = directory.parent / (name + '.libs')
            if libraries.is_dir():
                copy_tree(libraries, packages / libraries.name)
        (runtime / 'python312._pth').write_text('DLLs\nLib\nLib/site-packages\nimport site\n')
        shutil.copy2(HERE / 'worker.py', runtime / 'worker.py')
        summary['runtime_sha256'] = {str(p.relative_to(out)): sha(p)
                                    for p in runtime.rglob('*') if p.is_file()}
        summary['resource_acl'] = {str(p.relative_to(out)): windows.security_observation(p)
                                   for p in (runtime, ipc, runtime / 'python.exe', runtime / 'worker.py')}
        save(out, 'progress.json', dict(stage='MATCHED_LOAD_CONTROLS'))
        for restricted in (False, True):
            label = 'restricted' if restricted else 'unrestricted'
            process, initialized = None, False
            before = time.monotonic()
            row = dict(case=label, status='FAIL')
            try:
                startup, size = module.STARTUPINFOEX(), module.SIZE()
                startup.startup.cb = C.sizeof(startup) if restricted else C.sizeof(module.STARTUPINFO)
                if restricted:
                    windows.kernel.InitializeProcThreadAttributeList(None, 2, 0, C.byref(size))
                    attributes = C.create_string_buffer(size.value)
                    module.require(windows.kernel.InitializeProcThreadAttributeList(attributes, 2, 0, C.byref(size)))
                    initialized = True
                    startup.attributes = C.cast(attributes, C.c_void_p)
                    capabilities = module.SECURITY_CAPABILITIES(sid, None, 0, 0)
                    policy = W.DWORD(1)
                    module.require(windows.kernel.UpdateProcThreadAttribute(attributes, 0, 0x20009,
                        C.byref(capabilities), C.sizeof(capabilities), None, None))
                    module.require(windows.kernel.UpdateProcThreadAttribute(attributes, 0, 0x2000E,
                        C.byref(policy), C.sizeof(policy), None, None))
                answer = ipc / (label + '.json')
                command = C.create_unicode_buffer(subprocess.list2cmdline([
                    str(runtime / 'python.exe'), '-I', '-B', str(runtime / 'worker.py'), str(answer)]))
                info = module.PROCESS_INFORMATION()
                module.require(windows.kernel.CreateProcessW(str(runtime / 'python.exe'), command,
                    None, None, False, 0x4 | (0x80000 if restricted else 0), None,
                    str(ipc), C.byref(startup), C.byref(info)))
                process = module.Process(windows, info.process, info.thread)
                identity = process.identity()
                row['identity'] = identity
                row['token'] = windows.token_observation(process.handle)
                if restricted:
                    windows.kernel.GetProcessMitigationPolicy.argtypes = [W.HANDLE, C.c_int, C.c_void_p, module.SIZE]
                    windows.kernel.GetProcessMitigationPolicy.restype = W.BOOL
                    flags = W.DWORD()
                    module.require(windows.kernel.GetProcessMitigationPolicy(process.handle, 13,
                        C.byref(flags), C.sizeof(flags)))
                    row['child_policy_flags'] = flags.value
                    if row['token']['appcontainer'] != 1 or row['token']['integrity_sid'] != 'S-1-16-4096' or not flags.value & 1:
                        raise RuntimeError('ACTUAL_RESTRICTIONS_MISMATCH')
                process.resume()
                row['exit_code'] = process.wait(15000)
                if answer.is_file():
                    row['worker'] = json.loads(answer.read_text(encoding='utf-8'))
                if row['exit_code'] == 0 and row.get('worker', {}).get('stage') == 'SDK_IMPORT_LOADED':
                    if row['worker']['appcontainer'] != int(restricted):
                        raise RuntimeError('WORKER_TOKEN_MISMATCH')
                    row['status'] = 'PASS'
            except Exception as error:
                row['error_type'] = type(error).__name__
                row['error'] = str(error)[:300]
            finally:
                if process is not None:
                    try:
                        if not process.exited():
                            process.terminate_exact(process.identity())
                        row['exact_worker_exited'] = process.exited()
                    finally:
                        process.close()
                if initialized:
                    windows.kernel.DeleteProcThreadAttributeList(attributes)
                row['seconds'] = time.monotonic() - before
                summary['cases'].append(row)
                save(out, label + '-controller.json', row)
        summary['status'] = 'PASS_LOAD_ONLY' if all(x['status'] == 'PASS' for x in summary['cases']) else 'COMPATIBILITY_FAILED'
    except Exception as error:
        summary.update(status='SETUP_FAILED', error_type=type(error).__name__, error=str(error)[:500])
    finally:
        code = windows.userenv.DeleteAppContainerProfile(profile)
        windows.advapi.FreeSid(sid)
        summary['profile_deleted'] = code >= 0
        if code < 0:
            summary['status'] = 'CLEANUP_FAILED'
        save(out, 'summary.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k != 'runtime_sha256'}, indent=2))
    return 0 if summary['status'] == 'PASS_LOAD_ONLY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
