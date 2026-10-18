#define UNICODE
#define _UNICODE
#define _WIN32_WINNT 0x0A00
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

/* Harmless fixture only: no SDK, terminal, account, IPC, shell or broker. */
static DWORD write_error = 0;
static DWORD write_native_error = 0, write_requested = 0, write_written = 0;
static int write_errno = 0;
static const char *write_error_source = "NONE";
static const char *write_stage = "NOT_ATTEMPTED";
static wchar_t write_path[32768];

static int write_json(const wchar_t *root, const wchar_t *name, const char *json) {
    HANDLE file;
    DWORD written = 0;
    size_t length = strlen(json);
    write_error = write_native_error = write_written = 0;
    write_requested = (DWORD)length;
    write_errno = 0; write_error_source = "NONE";
    write_stage = "PATH_FORMAT";
    if (swprintf_s(write_path, 32768, L"%s\\%s", root, name) < 0) {
        write_errno = errno; write_error_source = "CRT_ERRNO";
        write_error = ERROR_INVALID_NAME; return 0;
    }
    write_stage = "CREATE_FILE";
    file = CreateFileW(write_path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                       CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) {
        write_native_error = GetLastError(); write_error = write_native_error;
        write_error_source = "WIN32"; return 0;
    }
    write_stage = "WRITE_FILE";
    if (!WriteFile(file, json, (DWORD)length, &written, NULL)) {
        write_native_error = GetLastError(); write_error = write_native_error;
        write_error_source = "WIN32"; write_written = written;
        CloseHandle(file); return 0;
    }
    write_written = written;
    if (written != length) {
        write_error = ERROR_WRITE_FAULT; write_error_source = "SHORT_WRITE";
        CloseHandle(file); return 0;
    }
    write_stage = "FLUSH_FILE";
    if (!FlushFileBuffers(file)) {
        write_native_error = GetLastError(); write_error = write_native_error;
        write_error_source = "WIN32"; CloseHandle(file); return 0;
    }
    write_stage = "CLOSE_FILE";
    if (!CloseHandle(file)) {
        write_native_error = GetLastError(); write_error = write_native_error;
        write_error_source = "WIN32"; return 0;
    }
    write_stage = "COMPLETE";
    return 1;
}

static void json_path(char *target, const wchar_t *source) {
    size_t used = 0, index;
    for (index = 0; source[index] && index < 256; ++index) {
        unsigned int value = (unsigned int)source[index];
        if (value == '\\' || value == '"') {
            target[used++] = '\\'; target[used++] = (char)value;
        } else if (value >= 32 && value < 127) {
            target[used++] = (char)value;
        } else {
            sprintf_s(target + used, 1537 - used, "\\u%04x", value);
            used += 6;
        }
    }
    target[used] = 0;
}

static void writer_diagnostic(const wchar_t *root, int success) {
    HANDLE token = NULL, file;
    DWORD app = 0xffffffff, integrity = 0xffffffff, token_error = 0, size = 0, written = 0;
    DWORD root_attributes, root_error = 0;
    PROCESS_MITIGATION_CHILD_PROCESS_POLICY policy = {0};
    DWORD policy_ok;
    union { TOKEN_MANDATORY_LABEL label; BYTE bytes[256]; } information;
    wchar_t cwd[32768] = {0};
    char root_json[1537], path_json[1537], cwd_json[1537], report[8192];
    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) {
        if (!GetTokenInformation(token, TokenIsAppContainer, &app, sizeof(app), &size)) token_error = GetLastError();
        if (GetTokenInformation(token, TokenIntegrityLevel, &information, sizeof(information), &size)) {
            PSID sid = information.label.Label.Sid;
            integrity = *GetSidSubAuthority(sid, (DWORD)(*GetSidSubAuthorityCount(sid) - 1));
        } else token_error = GetLastError();
        CloseHandle(token);
    } else token_error = GetLastError();
    root_attributes = GetFileAttributesW(root);
    if (root_attributes == INVALID_FILE_ATTRIBUTES) root_error = GetLastError();
    GetCurrentDirectoryW(32768, cwd);
    policy_ok = GetProcessMitigationPolicy(GetCurrentProcess(), ProcessChildProcessPolicy, &policy, sizeof(policy));
    json_path(root_json, root); json_path(path_json, write_path); json_path(cwd_json, cwd);
    sprintf_s(report, sizeof(report),
        "{\"pid\":%lu,\"write_success\":%s,\"write_stage\":\"%s\",\"win32_error\":%lu,"
        "\"exit_error\":%lu,\"error_source\":\"%s\",\"crt_errno\":%d,"
        "\"requested_bytes\":%lu,\"written_bytes\":%lu,"
        "\"root\":\"%s\",\"computed_path\":\"%s\",\"cwd\":\"%s\","
        "\"root_attributes\":%lu,\"root_error\":%lu,\"appcontainer\":%lu,"
        "\"integrity_rid\":%lu,\"token_error\":%lu,\"policy_query_ok\":%lu,"
        "\"child_restricted\":%lu,\"path_limit_chars\":256}\n",
        GetCurrentProcessId(), success ? "true" : "false", write_stage, write_native_error,
        write_error, write_error_source, write_errno, write_requested, write_written,
        root_json, path_json, cwd_json, root_attributes, root_error, app, integrity, token_error,
        policy_ok, (DWORD)policy.NoChildProcessCreation);
    /* Relative diagnostic path independently tests formatted path versus root access.
       It is confined to the launcher's unique fixture working directory. */
    file = CreateFileW(L"fixture-diagnostic.json", GENERIC_WRITE, FILE_SHARE_READ, NULL,
                       CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file != INVALID_HANDLE_VALUE) {
        WriteFile(file, report, (DWORD)strlen(report), &written, NULL);
        FlushFileBuffers(file); CloseHandle(file);
    } else {
        /* Standalone control has file-backed stderr; restricted handles are not inherited. */
        fputs(report, stderr); fflush(stderr);
    }
}

static DWORD writer_probe_failure_exit(void) {
    DWORD stage = 0;
    if (strcmp(write_error_source, "WIN32") || write_native_error > 0xffff) return write_error;
    if (!strcmp(write_stage, "CREATE_FILE")) stage = 1;
    else if (!strcmp(write_stage, "WRITE_FILE")) stage = 2;
    else if (!strcmp(write_stage, "FLUSH_FILE")) stage = 3;
    else if (!strcmp(write_stage, "CLOSE_FILE")) stage = 4;
    if (!stage) return write_error;
    /* Application-defined tag E5, protocol version 1, known stage, exact fitting
       Win32 error. This diagnostic-only return is used solely by write_probe.
       Wider native/CRT/short-write errors keep their original DWORD exit. */
    return 0xE5100000u | (stage << 16) | write_native_error;
}

static DWORD attempt_child(const wchar_t *root, const wchar_t *marker, DWORD flags,
                           DWORD *created, DWORD *termination_proven) {
    wchar_t executable[32768], command[32768];
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    DWORD error;
    if (!GetModuleFileNameW(NULL, executable, 32768)) return GetLastError();
    if (swprintf_s(command, 32768, L"\"%s\" \"%s\" child \"%s\"", executable, root, marker) < 0)
        return ERROR_INVALID_PARAMETER;
    startup.cb = sizeof(startup);
    if (!CreateProcessW(executable, command, NULL, NULL, FALSE, flags,
                        NULL, root, &startup, &process)) return GetLastError();
    *created = 1;
    error = WaitForSingleObject(process.hProcess, 2000) == WAIT_OBJECT_0 ? 0 : WAIT_TIMEOUT;
    if (error) {
        TerminateProcess(process.hProcess, 91);
    }
    *termination_proven = WaitForSingleObject(process.hProcess, 2000) == WAIT_OBJECT_0;
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return error;
}

static int injected_exception(void) {
    __try {
        RaiseException(0xE0570001, 0, 0, NULL);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 1;
    }
    return 0;
}

static void probe_borrowed_handle(HANDLE handle, DWORD *pid, DWORD *error,
                                  DWORD *exception, const char **disposition) {
    if (!handle) { *disposition = "NOT_ATTEMPTED_ZERO_ARGUMENT"; return; }
    __try {
        *pid = GetProcessId(handle);
        if (*pid) *disposition = "API_RETURNED_PID";
        else { *error = GetLastError(); *disposition = "API_RETURNED_ZERO"; }
    } __except (GetExceptionCode() == EXCEPTION_INVALID_HANDLE ?
                EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) {
        *exception = GetExceptionCode();
        *disposition = "INVALID_HANDLE_EXCEPTION";
    }
    /* The numeric value is borrowed, never closed or reopened by expected PID.
       Other native exceptions remain unhandled and visibly fail the fixture. */
}

int wmain(int argc, wchar_t **argv) {
    const wchar_t *root, *mode;
    HANDLE token = NULL, parent = NULL;
    DWORD bytes = 0, appcontainer = 0, policy_ok = 0;
    DWORD create_denial = 0, write_denial = 0, inherited_pid = 0;
    DWORD inherited_error = 0, inherited_exception = 0;
    unsigned long long inherited_argument;
    const char *inherited_disposition = "NOT_ATTEMPTED";
    char inherited_pid_json[32] = "null", inherited_error_json[32] = "null";
    char inherited_exception_json[32] = "null", inherited_return_json[32] = "null";
    DWORD direct = 0, breakaway = 0, parent_pid;
    DWORD direct_created = 0, direct_terminated = 0, breakaway_created = 0, breakaway_terminated = 0;
    PROCESS_MITIGATION_CHILD_PROCESS_POLICY policy = {0};
    char report[2048];
    const char *primary = "null", *cleanup = "PROVEN";
    int observed = 0, raised = 0, cleanup_completed = 1;
    if (argc < 3) return 80;
    root = argv[1]; mode = argv[2];
    if (!wcscmp(mode, L"child")) {
        if (argc != 4) return 81;
        return write_json(root, argv[3], "{\"executed\":true}\n") ? 0 : 82;
    }
    if (argc != 5) return 83;
    if (!wcscmp(mode, L"write_probe")) {
        int success;
        sprintf_s(report, sizeof(report), "{\"pid\":%lu,\"positive_marker\":true}\n", GetCurrentProcessId());
        success = write_json(root, L"positive-marker.json", report);
        writer_diagnostic(root, success);
        return success ? 0 : (int)writer_probe_failure_exit();
    }
    sprintf_s(report, sizeof(report), "{\"pid\":%lu,\"entered\":true}\n", GetCurrentProcessId());
    if (!write_json(root, L"entry.json", report)) {
        writer_diagnostic(root, 0);
        return (int)write_error;
    }
    parent_pid = wcstoul(argv[3], NULL, 10);
    inherited_argument = _wcstoui64(argv[4], NULL, 10);
    if (inherited_argument) {
        sprintf_s(report, sizeof(report),
            "{\"pid\":%lu,\"stage\":\"BEFORE_GET_PROCESS_ID\",\"argument\":%llu}\n",
            GetCurrentProcessId(), inherited_argument);
        if (!write_json(root, L"borrowed-handle-probe.json", report)) return 96;
    }
    probe_borrowed_handle((HANDLE)(uintptr_t)inherited_argument, &inherited_pid,
                          &inherited_error, &inherited_exception, &inherited_disposition);
    if (inherited_pid) sprintf_s(inherited_pid_json, sizeof(inherited_pid_json), "%lu", inherited_pid);
    if (!strcmp(inherited_disposition, "API_RETURNED_PID") || !strcmp(inherited_disposition, "API_RETURNED_ZERO"))
        sprintf_s(inherited_return_json, sizeof(inherited_return_json), "%lu", inherited_pid);
    if (!strcmp(inherited_disposition, "API_RETURNED_ZERO"))
        sprintf_s(inherited_error_json, sizeof(inherited_error_json), "%lu", inherited_error);
    if (inherited_exception)
        sprintf_s(inherited_exception_json, sizeof(inherited_exception_json), "%lu", inherited_exception);
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return 84;
    if (!GetTokenInformation(token, TokenIsAppContainer, &appcontainer, sizeof(appcontainer), &bytes)) {
        CloseHandle(token); return 85;
    }
    CloseHandle(token);
    policy_ok = GetProcessMitigationPolicy(GetCurrentProcess(), ProcessChildProcessPolicy,
                                           &policy, sizeof(policy));
    parent = OpenProcess(PROCESS_CREATE_PROCESS, FALSE, parent_pid);
    if (!parent) create_denial = GetLastError(); else CloseHandle(parent);
    parent = OpenProcess(PROCESS_VM_WRITE, FALSE, parent_pid);
    if (!parent) write_denial = GetLastError(); else CloseHandle(parent);
    sprintf_s(report, sizeof(report),
        "{\"pid\":%lu,\"appcontainer\":%lu,\"policy_query_ok\":%lu,"
        "\"child_restricted\":%lu,\"parent_create_error\":%lu,"
        "\"parent_vm_write_error\":%lu,\"inherited_parent_pid\":%s,"
        "\"borrowed_handle_probe\":{\"api\":\"GetProcessId\",\"worker_pid\":%lu,\"attempted\":%s,"
        "\"argument\":%llu,\"disposition\":\"%s\",\"returned_pid\":%s,"
        "\"api_return_value\":%s,\"win32_error\":%s,\"exception_code\":%s},\"before_work\":true}\n",
        GetCurrentProcessId(), appcontainer, policy_ok, (DWORD)policy.NoChildProcessCreation,
        create_denial, write_denial, inherited_pid_json, GetCurrentProcessId(), inherited_argument ? "true" : "false",
        inherited_argument, inherited_disposition, inherited_pid_json, inherited_return_json, inherited_error_json,
        inherited_exception_json);
    if (!write_json(root, L"started.json", report)) return 86;
    if (!write_json(root, L"initialize-attempted.json", "{\"attempted\":true}\n")) return 89;
    if (!wcscmp(mode, L"hang")) Sleep(INFINITE);
    if (!wcscmp(mode, L"launch_race")) {
        wchar_t gate[32768];
        ULONGLONG start = GetTickCount64();
        swprintf_s(gate, 32768, L"%s\\go.txt", root);
        while (GetFileAttributesW(gate) == INVALID_FILE_ATTRIBUTES) {
            if (GetTickCount64() - start > 5000) return 87;
            Sleep(5);
        }
    }
    if (!wcscmp(mode, L"launch") || !wcscmp(mode, L"launch_race")) {
        direct = attempt_child(root, L"direct-child.json", 0, &direct_created, &direct_terminated);
        breakaway = attempt_child(root, L"breakaway-child.json", CREATE_BREAKAWAY_FROM_JOB,
                                   &breakaway_created, &breakaway_terminated);
    } else if (!wcscmp(mode, L"init_false")) {
        primary = "\"LIVE_IPC_INITIALIZE_FAILED\"";
    } else if (!wcscmp(mode, L"init_raise") || !wcscmp(mode, L"init_raise_shutdown_raise")) {
        raised = injected_exception();
        primary = "\"LIVE_IPC_INITIALIZE_FAILED\"";
    } else if (!wcscmp(mode, L"observe_raise")) {
        if (!write_json(root, L"observation-attempted.json", "{\"attempts\":1}\n")) return 94;
        raised = injected_exception();
        primary = "\"LIVE_OBSERVATION_UNAVAILABLE\"";
    } else {
        if (!write_json(root, L"observation-attempted.json", "{\"attempts\":1}\n")) return 94;
        observed = 1;
    }
    if (observed && !write_json(root, L"observation.json", "{\"attempts\":1,\"synthetic\":true}\n")) return 90;
    if (!write_json(root, L"cleanup-attempted.json", "{\"attempted\":true}\n")) return 93;
    if (!wcscmp(mode, L"shutdown_raise") || !wcscmp(mode, L"init_raise_shutdown_raise")) {
        raised += injected_exception(); cleanup = "UNPROVEN"; cleanup_completed = 0;
    }
    sprintf_s(report, sizeof(report),
        "{\"primary_reason_code\":%s,\"cleanup\":\"%s\",\"observed\":%s,"
        "\"account\":null,\"caught_exceptions\":%d,\"cleanup_attempted\":true,"
        "\"cleanup_completed\":%s,\"direct_error\":%lu,\"breakaway_error\":%lu,"
        "\"direct_created\":%lu,\"direct_terminated\":%lu,"
        "\"breakaway_created\":%lu,\"breakaway_terminated\":%lu}\n",
        primary, cleanup, observed ? "true" : "false", raised,
        cleanup_completed ? "true" : "false", direct, breakaway, direct_created,
        direct_terminated, breakaway_created, breakaway_terminated);
    return write_json(root, L"result.json", report) ? 0 : 88;
}
