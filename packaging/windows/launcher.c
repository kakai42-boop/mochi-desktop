/* Native GUI entry point. Python/GTK are private runtime details. MIT, see LICENSE. */
#ifndef UNICODE
#define UNICODE
#endif
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>
#include <stdint.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR arguments, int show) {
    (void)instance; (void)previous; (void)show;
    static wchar_t root[32768], python[32768], command[32768], user[32768], mutex_name[128];
    DWORD n = GetModuleFileNameW(NULL, root, 32768);
    if (!n || n >= 32768) return 1;
    wchar_t *slash = wcsrchr(root, L'\\');
    if (!slash) return 1;
    *slash = 0;
    int agent = wcsncmp(arguments, L"--agent-signal", 14) == 0;
    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    int browser = argv && argc >= 2 && wcsncmp(argv[1], L"chrome-extension://", 19) == 0;
    if (argv) LocalFree(argv);
    int stdio = agent || browser;
    HANDLE mutex = NULL;
    if (!stdio) {
        DWORD length = GetEnvironmentVariableW(L"USERPROFILE", user, 32768);
        uint64_t hash = UINT64_C(14695981039346656037);
        for (DWORD i = 0; i < length && i < 32768; ++i) { hash ^= user[i]; hash *= UINT64_C(1099511628211); }
        _snwprintf(mutex_name, 128, L"Local\\MochiDesktop-%016llx", (unsigned long long)hash);
        mutex = CreateMutexW(NULL, TRUE, mutex_name);
        if (!mutex) return 1;
        if (GetLastError() == ERROR_ALREADY_EXISTS) { CloseHandle(mutex); return 0; }
    }
    if (_snwprintf(python, 32768, L"%ls\\runtime\\bin\\%ls", root, browser ? L"python.exe" : L"pythonw.exe") < 0 ||
        _snwprintf(command, 32768, L"\"%ls\" -I \"%ls\\bootstrap.py\" %ls", python, root, arguments) < 0) {
        if (mutex) CloseHandle(mutex);
        return 1;
    }
    STARTUPINFOW startup = {0}; startup.cb = sizeof(startup);
    if (stdio) {
        startup.dwFlags = STARTF_USESTDHANDLES;
        startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
        startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
        startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);
    }
    PROCESS_INFORMATION process = {0};
    BOOL started = CreateProcessW(python, command, NULL, NULL, stdio, CREATE_NO_WINDOW, NULL, root, &startup, &process);
    DWORD result = 1;
    if (started) {
        CloseHandle(process.hThread);
        WaitForSingleObject(process.hProcess, INFINITE);
        GetExitCodeProcess(process.hProcess, &result);
        CloseHandle(process.hProcess);
    } else if (!stdio) {
        MessageBoxW(NULL, L"Mochi ne trouve pas son environnement. Extrayez toute l'archive ou reinstallez l'application.", L"Mochi", MB_OK | MB_ICONERROR);
    }
    if (mutex) { ReleaseMutex(mutex); CloseHandle(mutex); }
    return agent ? 0 : (int)result;
}
