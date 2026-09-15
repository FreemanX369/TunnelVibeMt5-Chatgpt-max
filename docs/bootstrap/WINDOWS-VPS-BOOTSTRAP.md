# VibeMQL5 Windows VPS bootstrap — TIP-034C

This runbook makes the repository a clean-checkout bootstrap authority without moving machine secrets or MT5 account state into Git.

## 1. Repository authority

Clone the exact approved commit into `C:\VibeMQL5`. Do not bootstrap from an arbitrary working directory or from files copied from an older VPS.

Runtime identity remains `0.2.34 / TIP-033RC1` during TIP-034C. Native execution remains fixed to `MT5-2`; the latest native-observed MT5 build is runtime authority, not stale configured metadata.

## 2. External prerequisites

Provision these outside Git before activation:

- Windows with PowerShell 5.1+ and Python 3.12.
- MetaTrader 5 installations/terminal registration, including fixed alias `MT5-2`.
- `C:\VibeMQL5\tunnel\tunnel-client.exe` from its authorized distribution channel.
- Approved tunnel profile (`vibemql5-vps` for instance A, or the explicitly approved instance profile).
- Machine-bound DPAPI secret at the configured `secretFile` path. The repository contains only the path reference, never secret bytes.
- MT5 account credentials and AutoTrading state remain external and unchanged by this bootstrap.
- A Windows credential is requested by Task Scheduler only when the optional pre-logon background tunnel is explicitly enabled.

## 3. Python environment

From the clean checkout:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c .\requirements-bootstrap.lock -e ".[mcp]"
```

For qualification/test hosts, install the test extra instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -c .\requirements-bootstrap.lock -e ".[test]"
```

`pyproject.toml` is the direct package authority; `requirements-bootstrap.lock` constrains the Windows/Python 3.12 transitive resolver surface.

## 4. Config boundary

`ops\windows\vibemql5.windows.json` is a checked-in sanitized deployment template. `tasks.interactiveUser` must be empty in Git. The installer fills that non-secret machine identity locally at install time. The DPAPI secret path may be present as a reference; secret content must never be read, printed, exported or committed.

## 5. Mutation-free dry-run

Before installing tasks, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\Install-VibeMQL5ScheduledTasks.ps1 -WhatIf
```

Required result includes `TIP034_BOOTSTRAP_DRY_RUN=PASS` and `SECRET_PROVISIONING=EXTERNAL_REQUIRED`. The dry-run parses config and validates required scripts but must not modify config, create/remove scheduled tasks, request credentials or start/stop tunnels.

## 6. Install scheduled tasks

After prerequisites and external secret/profile provisioning are complete, run the same installer without `-WhatIf`. Enable the optional boot tunnel only when explicitly required:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\Install-VibeMQL5ScheduledTasks.ps1
```

or, for the approved pre-logon mode:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\Install-VibeMQL5ScheduledTasks.ps1 -EnableBootTunnel
```

## 7. Qualification boundary

TIP-034C proves repository/bootstrap completeness only. A clean checkout must pass import, 72/71 catalog reconstruction, Python compilation, unit tests, secret/state scan and Windows dry-run in GitHub Actions.

Native/new-VPS qualification is TIP-034D and must be performed only after TIP-034C acceptance. Formal current-build soak is TIP-034E. Final release promotion remains blocked until TIP-034A/B/C/D/E all pass and the Owner separately approves TIP-035.
