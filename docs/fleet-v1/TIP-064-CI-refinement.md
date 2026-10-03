# TIP-064 loopback HTTPS fixture refinement

Status: test source updated; exact candidate Linux/Windows CI pending. Builder: gateway_tests_review. Methodology: Vibecode Kit v6. This refinement follows Contractor authorization after the published candidate's Windows run.

## YAGNI-3

1. The temporary HTTPS services listen only on IPv4. On Windows, a `localhost` origin can first attempt IPv6, consuming the configured request budget before the matching IPv4 connection succeeds. Actual fixture traffic must name its actual listener.
2. Reuse the same verified HTTPS client, exact audience, existing ephemeral certificate factory and existing timeout policies. The B Builder added `127.0.0.1` to that certificate's subject alternative names.
3. Replace only the nine actual loopback-origin strings in four external HTTPS fixture files with numeric IPv4. No new routing layer or timeout increase is needed.

| Test source | Actual origins changed | SHA-256 after refinement |
| --- | --- | --- |
| `tests/unit/test_tip064_integration.py` | 3 | `7db50a02c9783a7fc84ddd489fdd4b820007d644de2fe44412c6aca0e9bc47f9` |
| `tests/unit/fleet_writer_fixture.py` | 2 | `1c19d59e1c97c8fd66b282d88bbf4829ef83cae8ff6ec982989381e6f1940d5e` |
| `tests/unit/test_tip060c_https_restore.py` | 2 | `c126e415dae9de63d71d598c3dd8b4a35dd133dbf2cb80901c5fe548b623a769` |
| `tests/unit/test_tip064_capacity_https.py` | 2 | `f607707a0335035e09c77ffcf604d6656cdcb5e52e600a239f34e56bec8a125d` |

Pure wire audiences, invalid-origin cases, the no-HTTP startup fixture and B's deliberate IPv6-first deadline rejection case retain their original inputs. Product address-family ordering and request deadlines are unchanged by these fixture edits. Other owned Windows product/fixture findings remain with their owning Builders.

Linux worktree diagnostic: **107 PASS, zero failures/skips, 32.97 seconds** across `test_tip064_integration.py`, `test_tip064_capacity_https.py`, `test_tip060c_https_restore.py`, `test_tip064_writer_resolution_https.py`, `test_tip061b_writers.py` and `test_tip063_worktrees.py`. These are actual temporary verified HTTPS and harmless source fixtures; no MT5/SDK physical qualification is claimed. This diagnostic is not exact candidate acceptance or an unchanged-global-source attestation. The Contractor's next frozen candidate CI supplies full logs, JUnit and manifest qualification.

The earlier TIP-064 v1/v2 receipts remain retained and identify their original source scope. This refinement changes their test-source hashes; it does not rewrite those receipts or reuse their acceptance claim for the new candidate. Owning A/M3/worktree Builders were notified to refresh their shared-fixture manifest references.
