# TIP085 completion contract

Parent: b097bb59a40c15c152214c0d133bd5a78de4761d, tree bbec58a7acb1a513b53b8f3691a1e0c0b154f6c8.

This change repairs premature aging of newly issued native proofs by moving the original gateway clock sample next to signing after prerequisites. The original 1000ms signed lifetime and real post-sign expiry remain enforced. Trusted callbacks revalidate late admission and retain denied/replayed observations through the existing durable clock head. The precise contract and direct journal compatibility are described in TIP-085-native-issuance-time-anchor.md.

The three application payloads are byte-identical to the approved external prototype. Frozen external qualification27 and independent Root qualification27 both passed. The production test module contains26 actual-source regressions, excludes the parent-only counter, and stores optional evidence solely in each test's tmp_path. It requires no external shadow module, staged research file or PROOF_OUTPUT environment.

Builder verification: focused195 cap300, then full1611 cap600, once each with retries0 and no overlap. The external Builder CompletionReport and frozen receipts provide actual results, collection identity/skip preservation, all six payload SHA256/Git blob hashes, source230 inventory and staged tree. Original1585 cases retain identity/order and their original local41, Linux18 and Windows12 skip contracts; workflows/dependencies and original test files are unchanged.

Root independently verifies the staged candidate before publishing once. Fresh source CI must reach eight of eight; these local/external results do not assert CI success or physical ownership qualification. Builder does not commit, push, publish or mutate runtime.

