def retained_file_metadata(fd):
    """Stable identity/size/times from the retained file, not host stat aliases."""
    if os.name != "nt":
        record = os.fstat(fd)
        if not stat.S_ISREG(record.st_mode): raise OSError()
        return (record.st_dev, record.st_ino, record.st_size, record.st_mtime_ns, record.st_ctime_ns)
    import ctypes as C
    from ctypes import wintypes as W
    import msvcrt
    class FileId(C.Structure):
        _fields_ = [("volume", C.c_ulonglong), ("identifier", C.c_ubyte * 16)]
    class Basic(C.Structure):
        _fields_ = [("creation", C.c_longlong), ("access", C.c_longlong), ("write", C.c_longlong),
                    ("change", C.c_longlong), ("attributes", W.DWORD)]
    class Standard(C.Structure):
        _fields_ = [("allocation", C.c_longlong), ("size", C.c_longlong), ("links", W.DWORD),
                    ("delete_pending", C.c_ubyte), ("directory", C.c_ubyte)]
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.GetFileInformationByHandleEx.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD]
    kernel.GetFileInformationByHandleEx.restype = W.BOOL
    handle = msvcrt.get_osfhandle(fd)
    identity, basic, standard = FileId(), Basic(), Standard()
    for kind, record in ((18, identity), (0, basic), (1, standard)):
        if not kernel.GetFileInformationByHandleEx(handle, kind, C.byref(record), C.sizeof(record)):
            raise C.WinError(C.get_last_error())
    if basic.attributes & (0x10 | 0x400) or standard.directory or standard.delete_pending or standard.size < 0:
        raise OSError()
    return (identity.volume, bytes(identity.identifier), standard.size, basic.write, basic.change, basic.creation, basic.attributes)
