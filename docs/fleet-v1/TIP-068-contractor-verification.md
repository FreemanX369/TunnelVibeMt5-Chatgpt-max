# TIP-068 — independent Contractor verification

Reviewed against exact parent806ca44e238cc1384441234d9699cb2dbf3336e8,
tree8ff9579347109eafd214eb98637b0db182490108, 2026-10-06.
Parent remains NOT_ACCEPTED_7_OF8; Windows exit124/600.046s and missing JUnit
are retained. Its last visible release-failure test does not prove the cause.
This report is before candidate publication; current PR/external receipts govern
the eventual exact-head gate. No docs-only successor is needed for this header.

## Result and evidence

Builder final frozen v3:27 PASS,0fail/error/skip,4.56s. Contractor independent
run:29 PASS,0fail/error/skip,7.31s. The Contractor explicitly enabled the real
plugin and exercised the27 focused controls plus both TLS capacity callback
release-failure controls[False/True]. Counts overlap and must not be added.
Frozen four file byte counts/SHA match before and after; all214 source entries
match both Builder and Contractor manifests. Other210 source entries and all89
app entries match the exact parent. No production/dependency/workflow changed.

Contractor parsed all58 flushed outer START/FINISH rows: ordinal1..29, complete,
no truncation, PASSED outcomes, parameter values omitted. Eight real child JUnit
receipts preserve two intentionally failed calls, two fixture errors and two
skips. The interrupted child has exactly one flushed START and the original raw
faulthandler dump, no invented JUnit. Default children emit no observer rows.
Commands, environment, raw logs/JUnit, frozen/manifests and independent receipt
are retained alongside this report. These source controls do not qualify Windows
or MT5/private VM performance.

## Review

The full-unit command adds only -p fleet_source_progress. Original full suite,
all five Windows harness cases/two Linux cases,600s full-unit/120s proof/90s dump,
capture and source manifest invariance remain. Observer uses existing foreground
pytest hooks/terminal reporter, no worker/pool, effects, retries or grants.
It caps4096 ordinary rows then emits one TRUNCATED marker. Bounded literal
relative file/function fields omit parameter data, arbitrary paths and bodies.
FINISH stays UNKNOWN until a passed call report; failure dominates later reports.

Review corrections were implemented before final freeze: UNKNOWN without call,
real setup/teardown error controls; actual flushed START before the child timeout
to separate Windows interpreter scheduling; exact owned child kill/wait; complete
newline readiness parsing without accepting malformed complete JSON. Existing
capacity and long authorization production fixtures/budgets are unchanged.
The initial bounded capture probe retained raw dumps under both fd and tee-sys;
there is no evidence for changing capture. Historical Windows timeout could still
be aggregate exhaustion or a slow/hung test. No cause or repair is claimed.

## Remaining gates

FOCUSED_SOURCE_PASS; new candidate exact-head8/8 plus ZIP/head/tree/manifests/
complete JUnit/nine proofs/required Windows controls PENDING. No same-head rerun
was used. Original TIP066 five ZIPs/three failed runs and TIP067 timeout ZIP/raw
logs are preserved. Fresh22:19ICT server_info/health/runtime_status/diagnose/
tunnel_admin_status(all) all raw MCP-32603. READY/PID/queue/locks/current MT5
session/data-root and old synchronous unit outcome UNKNOWN; async start/get absent
from78 callable tools. No VPS effects, deploy/restart/suite rerun, credentials,
ownership/packages/services activation or UNKNOWN clearing. Mixed legacy TIP065
overlay remains the last deployed slice. Private VM/two-node/real SDK/full Fleet
physical qualification, successful native demo/fresh feed/actual overlap and
production merge remain OPEN/NOT_RUN. Historical owner-grant/storage/scheduling
causes remain UNKNOWN.
