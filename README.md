# TunnelVibeMt5-Chatgpt-max

Canonical repository for the TunnelVibeMt5 / ChatGPT integration project.

## Authority

- Owner authority: project owner.
- Canonical execution source: the current TunnelVibemq5 big-update execution plan.
- GitHub repository: `FreemanX369/TunnelVibeMt5-Chatgpt-max`.
- Runtime authority: the **latest MT5/MetaEditor build actually observed on the fixed terminal**. A stale configured build number must never override a newer live build after MT5 restart/update.
- Runtime evidence outranks assumptions and stale documentation.

## Execution order

1. Baseline / authority lock.
2. Runtime and tool capability inventory.
3. Minimal implementation required by the approved plan.
4. Verify against the latest MT5 build.
5. Persist source/config/provenance/evidence to this repository.
6. Reconcile runtime ↔ GitHub ↔ canonical execution requirements.
7. Report PASS / FAIL / BLOCKED from actual evidence only.

## Invariants

- Always target the latest observed MT5 build as the compatibility/build authority.
- Preserve the fixed-terminal identity/path invariant separately from the terminal build version.
- Do not treat configuration inventory and live execution build as the same authority.
- Do not claim acceptance without runtime evidence.
- Do not overwrite or reset valid evidence without a specific reason.
- Prefer existing runtime/code/library capability before adding new implementation.
- Keep implementation minimal; add only what the active requirement needs.

## Repository policy

Project updates are persisted here rather than existing only in chat. Source, configuration, architecture decisions, provenance, verification evidence, and release notes should be committed as they become authoritative.

This repository starts intentionally minimal. Additional files/directories are added only when required by an implemented or verified capability.

## Latest release candidate

See [TIP-040 live MT5-2 observations](docs/releases/TIP-040.md) for the on-demand account, chart, screenshot and log tool contracts and their runtime acceptance gate.
See [TIP-041 default 16:9 chart capture](docs/releases/TIP-041.md) for the new screenshot parameter, 960×540 output, rollback checks and `native` option.
See [TIP-042 chart capture timeout](docs/releases/TIP-042.md) for the bounded render timeout adjustment after a live Business C capture failure.
