/* Harmless leaf protocol stub. No SDK, child, broker, terminal or network API. */
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

#define CAP 32768

static int read_bounded(const wchar_t *path, char *buffer, DWORD *length) {
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    BOOL ok;
    if (file == INVALID_HANDLE_VALUE) return 10;
    ok = ReadFile(file, buffer, CAP + 1, length, NULL);
    CloseHandle(file);
    return !ok || *length > CAP ? 11 : 0;
}

static int write_new(const wchar_t *path, const char *buffer, DWORD length) {
    HANDLE file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    DWORD written = 0;
    BOOL ok;
    if (file == INVALID_HANDLE_VALUE) return 12;
    ok = WriteFile(file, buffer, length, &written, NULL);
    if (ok) ok = FlushFileBuffers(file);
    CloseHandle(file);
    return !ok || written != length ? 13 : 0;
}

int wmain(int argc, wchar_t **argv) {
    char buffer[CAP + 1], marker[256];
    wchar_t marker_path[32768];
    DWORD length = 0, appcontainer = 0, needed = 0;
    HANDLE token = NULL;
    PROCESS_MITIGATION_CHILD_PROCESS_POLICY policy = {0};
    int status, count;
    if (argc != 5) return 20;
    status = read_bounded(argv[1], buffer, &length);
    if (status) return status;
    if (!GetProcessMitigationPolicy(GetCurrentProcess(), ProcessChildProcessPolicy, &policy, sizeof(policy))) return 21;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return 22;
    if (!GetTokenInformation(token, TokenIsAppContainer, &appcontainer, sizeof(appcontainer), &needed)) {
        CloseHandle(token); return 23;
    }
    CloseHandle(token);
    if (swprintf_s(marker_path, 32768, L"%s.entered", argv[2]) < 0) return 24;
    count = sprintf_s(marker, sizeof(marker), "{\"pid\":%lu,\"appcontainer\":%lu,\"child_policy_flags\":%lu}",
                      GetCurrentProcessId(), appcontainer, policy.Flags);
    if (count < 0) return 25;
    status = write_new(marker_path, marker, (DWORD)count);
    if (status) return status;
    if (wcscmp(argv[4], L"hang") == 0) { Sleep(30000); return 26; }
    if (wcscmp(argv[4], L"noresult") == 0) return 0;
    if (wcscmp(argv[4], L"normal") != 0) return 27;
    status = read_bounded(argv[3], buffer, &length);
    return status ? status : write_new(argv[2], buffer, length);
}
