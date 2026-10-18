"""Research LOAD only: imports the SDK, never calls an SDK operation."""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def main():
    output = Path(sys.argv[1])
    def save(stage, **data):
        value = dict(scope="SDK_IMPORT_ONLY_NO_INITIALIZE_NO_TERMINAL", stage=stage,
                     pid=os.getpid(), monotonic=time.monotonic(), **data)
        # The product IPC ACL intentionally grants no DELETE/rename authority.
        # Publish each progress stage once and create the final result once,
        # matching the product's exclusive write_bounded protocol.
        path = output if stage == 'SDK_IMPORT_LOADED' else output.with_name(output.stem + '-' + stage + '.json')
        with path.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(value, indent=2))
            stream.flush()
            os.fsync(stream.fileno())
    save('PYTHON_STARTED')
    # Observe our actual token/mitigation before importing any SDK code.
    kernel = C.WinDLL('kernel32', use_last_error=True)
    advapi = C.WinDLL('advapi32', use_last_error=True)
    kernel.GetCurrentProcess.restype = W.HANDLE
    advapi.OpenProcessToken.argtypes = [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)]
    advapi.GetTokenInformation.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)]
    token, size, app = W.HANDLE(), W.DWORD(), W.DWORD()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, C.byref(token)):
        raise C.WinError(C.get_last_error())
    try:
        if not advapi.GetTokenInformation(token, 29, C.byref(app), C.sizeof(app), C.byref(size)):
            raise C.WinError(C.get_last_error())
    finally:
        kernel.CloseHandle.argtypes = [W.HANDLE]
        kernel.CloseHandle(token)
    save('SDK_IMPORT_BEGIN', appcontainer=app.value)
    import MetaTrader5 as sdk
    import numpy
    extension = sys.modules.get('MetaTrader5._core')
    native_path = Path(extension.__file__) if extension else None
    save('SDK_IMPORT_LOADED', appcontainer=app.value, sdk_version=sdk.__version__,
         numpy_version=numpy.__version__, sdk_file=sdk.__file__,
         extension_file=str(native_path) if native_path else None,
         extension_sha256=hashlib.sha256(native_path.read_bytes()).hexdigest() if native_path else None)


if __name__ == '__main__':
    main()
