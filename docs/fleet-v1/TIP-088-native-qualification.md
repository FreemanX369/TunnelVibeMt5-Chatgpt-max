# TIP-088 — Real SDK qualification continuation

Input source: b34d28fd9f6c71eb8c6870039aec77a75284e469. The existing FIX4R2 A/B/C
control deployment stays active. Owner approved continuing the native fix plan
on 2026-10-18. Do not change the current MT5-2 account, credentials or AutoTrading.

## YAGNI-3

The missing physical evidence is necessary for qualification. Reuse product
Win32 token/process/handle mechanics and the existing signed approval loaders.
First run the smallest causal experiment: matched unrestricted and restricted
Python/MetaTrader5 import, with no initialize or terminal API. No new service,
boolean bypass, synthetic REAL_Q2 record or production trust installer is added.

## Acceptance and dependencies

- AC1: Real SDK import on a disposable Windows runner using Python3.12.10,
  SDK5.0.6147 and NumPy2.5.2, matching the observed VPS versions. Record actual
  OS build and source/runtime hashes; a different OS never qualifies the VPS.
- AC2: Restricted suspended handle reports AppContainer1, low integrity and
  no-child creation before resume; worker observes its actual AppContainer bit.
- AC3: Read/execute ACLs affect only the fresh cloned runtime; write access is
  limited to disposable IPC. Original runtime/source/terminal ACLs are unchanged.
- AC4: Retained exact worker exits and research profile deletion are observed.
- AC5: LOAD-only PASS must retain UNQUALIFIED. Full Q2 requires two selected clean
  disposable bindings and stopped/race/escape/crash/cleanup controls; native
  compile/test and capacity have their own physical acceptance matrices.

## Job discipline

One finite workflow, timeout8minutes, each worker wait15seconds and exact
termination wait5seconds. Preserve failed attempts, semantic progress and source
hashes. Do not retry unchanged incompatibility to obtain green output. No
faulthandler watchdog is installed in the live pilot.

## Current boundary

Live node has no SDK approvals, native trust, native runtime/ownership approval
or capacity trust. Existing source procedures deferred physical testing. The
current VPS has2GB RAM and no observed Hyper-V module. A disposable CI Windows
runner can test LOAD safely. Full binding qualification still needs an exact
disposable terminal environment and later evidence matching the installed node.
