# TIP-054 PowerShell JSON compatibility refinement

Status: implemented, pending actual PowerShell confirmation on the next exact candidate CI. Builder: gateway_tests_review. Methodology: Vibecode Kit v6. Contractor authorized the minimal compatibility refinement after the published source candidate failed.

The failed candidate is `3b955d6121bcc1758740e97989fb69754ae8f51f`, tree `4e4f35675d2d71c5ee5db3573ace3a6c10d93abb`. Linux CI reported 1,091 PASS, 13 SKIP and five watchdog-history failures. The actual PowerShell process returned successfully, but all five cases lost their recent restart entries, incorrectly admitting cooldown/budget. Seven direct timestamp heartbeat cases passed. The failure receipts remain under the Contractor's `fleet-ci-candidate-3b955d6/linux/` archive; their SHA-256 values are retained in `evidence/tip054-pwsh-json-v1/receipt.json`.

## YAGNI-3 and diagnosis

1. The compatibility fix is necessary: default JSON timestamp conversion can discard the original explicit offset before the existing UTC parser sees it.
2. Reuse the existing `Read-VibeJsonSafe` reader and the existing UTC parser, retry policy and watchdog budget/cooldown block. The fixture's direct `ConvertFrom-Json` bypassed the product reader, which had the same default conversion.
3. The smallest correction is to select `DateKind=String` when the installed `ConvertFrom-Json` supports that parameter and to test the real persisted-file reader.

[Microsoft's ConvertFrom-Json documentation](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/convertfrom-json?view=powershell-7.5) documents default timestamp conversion to `DateTime`, timezone conversion for explicit offsets and the `String` option introduced in PowerShell 7.5. This documented behavior explains the observed failures; the local environment has no PowerShell runtime and cannot independently confirm runtime execution. Windows PowerShell 5.1 retains the existing parameter set. No host clock, UTC validation, 45-second heartbeat threshold, cooldown duration, restart budget or atomic retry policy changed.

## Changed source

| File | Refinement |
| --- | --- |
| `ops/windows/VibeMQL5.AtomicFile.ps1` | Capability-detected `DateKind=String` in the existing safe JSON reader |
| `tests/unit/test_tip054_windows_health_guards.py` | All six history cases read actual JSON files through the reader; three new persisted-heartbeat cases check exact string preservation and refuse a missing offset |
| `tests/proofs/fleet_v1/run_source.py` | Include all 21 existing `ops/windows/*.ps1` source files in before/after candidate manifests |

## Verification and limits

Local diagnostic: **15 PASS, 23 SKIP, zero failures**. The 23 skips honestly identify the absent PowerShell runtime; they are not actual PowerShell acceptance. Python compilation passed. A direct manifest assertion confirmed every current Windows PowerShell script is hashed. Owned source bytes remained unchanged during the diagnostic. Raw log, JUnit, source hashes and failed-receipt digests are in `evidence/tip054-pwsh-json-v1/`.

The next exact Linux/Windows candidate CI must execute all 23 PowerShell cases, including bounded sharing-error retries, malformed/missing JSON, explicit-offset heartbeat freshness and all six actual watchdog history-policy cases. No fixture is weakened or skipped by this refinement. Private VM/MT5/SDK qualification remains unperformed. Other Windows CI findings are assigned to their owning Builders and are outside this patch.
