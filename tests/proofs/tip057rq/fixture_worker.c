#define UNICODE
#define _UNICODE
#define _WIN32_WINNT 0x0A00
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

/* Harmless fixture only: no SDK, terminal, account, IPC, shell or broker. */
static int write_json(const wchar_t *root, const wchar_t *name, const char *json) {
    wchar_t path[32768];
    HANDLE file;
    DWORD written = 0;
    size_t length = strlen(json);
    if (swprintf_s(path, 32768, L"%s\\%s", root, name) < 0) return 0;
    file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                       CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    if (!WriteFile(file, json, (DWORD)length, &written, NULL) || written != length) {
        CloseHandle(file); return 0;
    }
    FlushFileBuffers(file);
    CloseHandle(file);
    return 1;
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
    if (!CreateProcessW(executable, command, NULL, NULL, FALSE, flags | CREATE_NO_WINDOW,
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

int wmain(int argc, wchar_t **argv) {
    const wchar_t *root, *mode;
    HANDLE token = NULL, parent = NULL;
    DWORD bytes = 0, appcontainer = 0, policy_ok = 0;
    DWORD create_denial = 0, write_denial = 0, inherited_pid = 0;
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
    sprintf_s(report, sizeof(report), "{\"pid\":%lu,\"entered\":true}\n", GetCurrentProcessId());
    if (!write_json(root, L"entry.json", report)) return 95;
    parent_pid = wcstoul(argv[3], NULL, 10);
    inherited_pid = GetProcessId((HANDLE)(uintptr_t)_wcstoui64(argv[4], NULL, 10));
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
        "\"parent_vm_write_error\":%lu,\"inherited_parent_pid\":%lu,\"before_work\":true}\n",
        GetCurrentProcessId(), appcontainer, policy_ok, (DWORD)policy.NoChildProcessCreation,
        create_denial, write_denial, inherited_pid);
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
