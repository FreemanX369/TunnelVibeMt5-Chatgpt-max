# TunnelVibemq5 Fleet Plan — Review tính khả thi và điều kiện bắt đầu build

Ngày review: 01/10/2026. Methodology: Vibecode Kit v6, vai trò Contractor. Đây là review và đề xuất Blueprint thu gọn; không phải quyết định phê duyệt hoặc Completion Report.

## 1. Quyết định đề xuất

**Nên tiếp tục hướng nâng cấp này. Chưa nên giao Builder triển khai toàn bộ TIP-055 → TIP-064 theo bản hiện tại.** Có thể tiến tới build gói đầu rất nhỏ sau khi chốt contract của gói đó; không cần giải quyết toàn bộ roadmap trước khi bắt đầu.

Plan đã có Vision tốt và Task Graph sơ bộ. Nó chưa là Blueprint thực thi: các quyết định D-01 → D-12 còn mở; một số dependency đặt ngược với mức rủi ro; acceptance chưa xử lý đầy đủ crash windows, migration và authority. Phụ lục A đã nhận diện đúng nhiều vấn đề, nhưng câu hỏi được liệt kê chưa phải câu trả lời mà Builder có thể implement và QA có thể xác nhận.

Không thấy trở ngại khiến kiến trúc một gateway + outbound VibeNode + core MT5 hiện có trở thành bất khả thi. Những giới hạn thật nằm ở bảo đảm thực thi sau crash, môi trường Windows/MT5, tác động tới live terminal và phạm vi trust.

## 2. Căn cứ và giới hạn của review

Đã đọc plan đính kèm, kiểm tra lại các luồng liên quan trong source đã khóa ở audit trước, xác nhận HEAD GitHub và đọc lại server_info/health hiện tại. Không chạy job MT5, không đổi account, không restart hoặc triển khai fleet.

| Bằng chứng | Quan sát trong review này |
|---|---|
| Tunnel GitHub main | `64a62906b4e62274732f0cbc375bfb3687af9e42`, không đổi so với audit trước |
| RemoteMCP GitHub main | `ec40f4e6dd56e391a19f635dd5cc975b8ed64373`, không đổi so với audit trước |
| Tunnel runtime | TIP-053 / 0.2.42, 85 catalog tools, fixed MT5-2, native parallelism 1 |
| Runtime health | READY, queue 0, 5 terminal registrations hợp lệ; RAM tổng khoảng 2 GB, RAM trống mẫu khoảng 1.46 GB |
| Tool registry của chat | 78 exposed tools; server kỳ vọng 84 model tools. Thiếu 6 model tools, ngoài tool import chỉ dành cho app |
| Caller identity | Runtime công bố `authenticated_client_identity=false` |

Năm terminal được đăng ký không chứng minh năm terminal đang chạy, có data root độc lập hoặc đủ tài nguyên để chạy năm tester. Số RAM trống là mẫu quan sát, không phải benchmark capacity. Read-only review này không chứng nhận headless execution, multi-terminal concurrency hoặc fleet recovery trên Windows thật.

Sáu tool thiếu trong registry hiện tại: `get_symbol_snapshot`, `copy_rates`, `copy_ticks`, `describe_capabilities`, `backend_start_test_run`, `backend_get_test_run`. Đây là vấn đề contract giữa runtime và connector cần xử lý trong migration; không phải bằng chứng core không có các chức năng đó.

## 3. Những quyết định trong plan nên giữ

| Quyết định | Vì sao phù hợp |
|---|---|
| Reuse ToolFacade, compiler/tester, provenance, checkpoint/CAS | Giữ phần đã có giá trị domain; giảm khối lượng viết lại và regression |
| Một MCP catalog cho nhiều VPS | Tránh nhân 85 tool theo số máy; domain API ổn định hơn |
| Outbound node | Không cần mở endpoint inbound riêng trên từng VPS; vẫn phải chốt endpoint gateway và authentication |
| Stable IDs tách alias/build | Alias có thể đổi; build update không phải thay thiết bị |
| Target đã pin thì không fallback | Giữ ý nghĩa của job, baseline và evidence |
| Read partial, mutation fail closed | Một node offline không làm mất dữ liệu các node còn lại; side effects cần target chính xác |
| Giữ Project Session, Iteration, Continuity | RemoteMCP primitives bổ sung coordination; không thay semantic history của EA |
| Một gateway, SQLite WAL trước | Hợp lý cho pilot nhỏ; chưa có nhu cầu đã chứng minh cho cluster/broker |
| Multi-agent/worktree sau fleet | Không ghép hai bài toán khó vào lần nâng cấp đầu |
| Không chuyển một native process đang chạy sang VPS khác | Tránh tạo continuation giả với môi trường khác |

RemoteMCP là nguồn ý tưởng tốt cho device identity, immutable placement, durable command/job journal và isolation. Audit trước đã tái hiện lỗi search qua symlink và CAS recovery dùng epoch cũ; physical recovery gates của repo cũng chưa hoàn tất. Vì HEAD không đổi, không nên copy những implementation đó rồi coi là đã được chứng nhận. Học contract và thêm regression tương ứng sẽ an toàn hơn port nguyên subsystem.

## 4. Các điểm cần sửa trước giai đoạn tương ứng

### F-01 — Fixed MT5-2 là authority trải rộng, không chỉ một resolver

Plan §13 nhận định Fleet chủ yếu thay `_fixed_terminal()` bằng `resolve_execution_target()`. Source cho thấy phạm vi lớn hơn:

- MCP adapter đặt MT5-2; `ToolFacade.compile_ea()` lấy fixed target dù nhận tham số terminal.
- Worker bắt buộc policy fixed MT5-2 trước native execution.
- Baseline hiện từ chối terminal khác MT5-2.
- Runtime capture có `EXPECTED_TERMINAL_ID = "MT5-2"`, signed authority record và binding tới tester roots/process.
- Live reads, chart delivery và một số metadata cũng giả định fixed target.

**Sửa plan:** tách TIP-055A thành thêm identity/target contract mà vẫn giữ FIXED policy. Việc mở native routing nằm ở gói tiếp theo, sau khi target đã đi xuyên request → reservation → worker → process binding → result → baseline/capture. Không bỏ guard trước khi có guard mới tương đương.

Runtime capture có thể giữ legacy-only ở pilot, nhưng routed jobs phải trả capability rõ ràng; không được dùng record mang MT5-2 để chứng thực MT5-3.

### F-02 — Terminal lock riêng chưa đủ cho IPC và tài nguyên dùng chung

`LiveTerminal` import cùng module `MetaTrader5`, gọi `initialize(path)`, đọc dữ liệu rồi `shutdown()`. Hiện `_observe_live()` được bảo vệ bởi native lease toàn cục. Nếu chuyển sang locks theo terminal rồi fan-out bằng các thread trong một interpreter, protection này không còn bảo vệ chung vòng đời IPC.

MetaQuotes mô tả API initialize/shutdown theo kết nối terminal; tài liệu đã đọc không đưa ra contract an toàn cho nhiều kết nối terminal đồng thời trong cùng module. Do đó đây là **rủi ro thiết kế cần qualification**, không phải kết luận rằng MT5 không thể chạy nhiều installation.

**MVP:** giữ một IPC gate cho toàn node, serialize toàn bộ initialize/read/shutdown; vẫn có thể fan-out giữa các VPS. Khi cần throughput trong một VPS, thử helper process riêng cho terminal và qualify binding trước khi mở parallel reads.

Locks còn phải theo tài nguyên thực: executable installation, data root, compiler deployment, tester agent/cache và GUI thao tác. Hai alias trỏ cùng installation/data root không được coi là hai executor độc lập. Tài liệu MT5 xác nhận không chạy hai bản platform từ cùng thư mục installation.

Giữ lock order nhất quán và lập bảng operation conflicts. Ví dụ compile trên terminal A không được ghi đè binary/includes mà tester B đang sử dụng qua root dùng chung. ResourceGuard không tự thay thế cơ chế reserve capacity: hai job cùng thấy RAM còn đủ vẫn có thể cùng khởi động.

### F-03 — Outbound/headless node không đồng nghĩa native MT5 headless

`TesterDriver.run()` hiện trả `MT5_INTERACTIVE_SESSION_REQUIRED` nếu Windows process chạy trong Session 0. Chart capture còn phụ thuộc cửa sổ và desktop có khả năng render. Hành vi node RemoteMCP chạy nền không chứng minh những điều kiện này cho MT5.

**Sửa plan:** công bố capability theo môi trường: control daemon, interactive native worker, chart capture. Gateway có thể chạy nền; worker cần mô hình Windows session đã được core hỗ trợ và qualification sau reboot/RDP disconnect. Chưa có session phù hợp thì báo unavailable/block job, không tự coi terminal là executor sẵn sàng. Nếu muốn MT5 native chạy hoàn toàn headless, đó là scope nghiên cứu riêng.

### F-04 — Tester trên live installation có tác động thật

`exclusive_live_terminal_handoff()` hiện đóng đúng installation rồi khởi động lại normal terminal sau test. Target pinning không làm thao tác đó mất ảnh hưởng tới live EA/connection.

**Sửa plan:** terminal phải có role/capabilities. Ưu tiên installation chuyên tester trong pilot. Live terminal mặc định chỉ đọc; handoff phải là policy được chọn rõ và có recovery gate. Không coi tester và live trading trên cùng installation là hai workload độc lập.

### F-05 — Idempotency cần contract crash recovery, không chỉ operation_id

Tunnel đã có `JobStore.reserve()` với operation ID và request hash, cùng flow reserve/dispatch của iteration. Đây là primitive nên reuse. Tuy nhiên routing hai tầng tạo cửa sổ mới: native process đã start nhưng node chưa commit ACK/result, gateway timeout, rồi retry.

**Sửa acceptance TIP-060:** cùng operation ID và canonical request, bao gồm frozen target/generations/input identity, phải trả cùng global/node job. Cùng ID khác payload hoặc target phải conflict. Gateway/node lưu durable mapping trước dispatch; node lưu intent trước side effect; khi recovery không chứng minh được outcome thì báo `UNKNOWN/RECOVERY_REQUIRED` và reconcile.

Không cam kết vừa tự retry vô điều kiện sau mọi timeout vừa luôn không duplicate external native execution. Để ưu tiên an toàn, outcome chưa rõ phải có thể dừng tiến trình orchestration chờ xác minh. ACK mất không chứng minh job chưa chạy.

Revocation cũng cần ranh giới rõ: chặn authorization/start mới; không tự suy ra native process đã chạy sẽ dừng tức thì khi node offline. Cancel là command riêng, kiểm tra PID + creation time + executable/job ownership. Historical result nhận muộn có thể lưu thành evidence quarantine, không tự authorize source commit mới.

### F-06 — Project/iteration contract phải có trước khi mở managed remote jobs

TIP-061 hiện phụ thuộc TIP-060 nhưng lại cung cấp iteration pinning, target-aware baseline và resume semantics. Đây là dependency cần chỉnh nếu TIP-060 mở jobs thuộc project/guarded iteration. Có thể pilot jobs độc lập trước, nhưng phải giới hạn API đó rõ ràng.

**Đề xuất:** đưa phần tối thiểu của TIP-061 lên trước TIP-060. Project default target chỉ dùng để tạo iteration/job mới; iteration/job hiện hữu giữ frozen target. Explicit target trái với frozen target phải bị từ chối. Legacy fallback local MT5-2 chỉ dùng khi request chưa có managed binding, không ghi đè project binding.

Continuity/project session cần một writer authority cho từng project. MVP giữ authority tại project owner node và để gateway lưu routes/read model; chưa tạo central writable replica. Evidence node nào chạy phải quay về authority này với operation ID/CAS. Nếu lựa chọn gateway authority thay thế, cần migration riêng, không để cả hai cùng ghi.

### F-07 — Repo A → execution B chưa có input transport

Plan thừa nhận gap này trong §11 và A5. Source SHA của file EA không đủ chứng minh cùng build inputs: Include, set/preset/config, binary, compiler/environment và dữ liệu tester có thể khác.

**MVP:** repo/workspace và executor cùng node; workspace phải được đăng ký và hiện hữu tại node đó. Cross-device execution trả `UNSUPPORTED_PLACEMENT` trước side effects.

**Giai đoạn sau:** content-addressed immutable bundle, manifest hash, transfer giới hạn dung lượng, verify tại node trước compile, deployment riêng cho job và artifact receipt bind target/job/hash. Không sync working directories ngầm hoặc dùng basename/workspace name làm identity. File/widget receipts cũng phải giữ nguyên semantics qua gateway; node đường dẫn Windows không thể trở thành file link trực tiếp cho client.

### F-08 — Node identity không xác thực agent/caller

Runtime hiện không xác thực được danh tính account ChatGPT. Signed node request chỉ chứng minh node giữ key; không chứng minh agent ID do caller truyền vào có quyền claim task, pair/revoke device hoặc sửa project.

**MVP:** một owner tin cậy; pairing/revoke chỉ qua admin surface. Khi mở multi-agent/client, dùng principal/token do gateway xác thực hoặc cấp, rồi bind task ownership vào principal đó. Nếu agent ID chỉ là attribution trong môi trường tin cậy, ghi rõ; không gọi đó là security boundary.

`backend_run_powershell` hiện có quyền rộng. Generic Repo Worker được hoãn không đồng nghĩa fleet đã không có generic shell. Node dispatch phải có capability allowlist; không route tự động backend admin/PowerShell qua mọi target. Worktree/lease không ngăn client bypass bằng shell có quyền OS.

### F-09 — Aggregation đúng không chỉ là trả PARTIAL

`LiveTerminal.state()` trả login masked. Login masked + server không đủ làm account dedup key chắc chắn. Cùng account mở ở ba terminal không tạo ba khoản equity độc lập.

**MVP:** per-target rows, observed_at, age, LIVE/CACHED/STALE, coverage requested/succeeded/failed và scoped errors; không cộng tổng equity. Nếu cần totals, thêm opaque account identity dùng cho dedup và nhóm theo currency. Không cộng USD/EUR vào cùng tổng; không tự thêm FX conversion.

Offline/busy/disconnected trả unknown/unavailable, không phải số 0. Giới hạn fan-out, timeout toàn request và payload chart/rates/ticks. Snapshot là tập quan sát có thời điểm khác nhau, không phải snapshot giao dịch nguyên tử toàn fleet.

### F-10 — Migration, backup và qualification cần trở thành acceptance

Schema target/generation còn mở; source history/revisions đang hash-bound. Không sửa bytes của revision/result cũ để thêm target rồi giữ SHA cũ. Tạo revision/schema mới và đánh dấu provenance legacy khi chưa thể chứng minh stable physical identity. Baseline thiếu evidence cần requalify, không tự suy ra identity lịch sử từ alias hiện tại.

Legacy và routed paths phải dùng cùng lock/ownership authority cho cùng tài nguyên; hai namespace độc lập có thể cho hai job chiếm cùng MT5-2. Rollback version phải xử lý schema mới/queued command mà không làm epoch hoặc idempotency lùi.

SQLite WAL phù hợp pilot, nhưng backup phải nhất quán bằng cơ chế SQLite hỗ trợ; sao chép riêng DB đang hoạt động không phải contract restore đủ. Restore gateway/node từ backup cũ cần reconcile journal trước khi enable dispatch. Gateway trên VPS đang chạy tester tạo chung failure domain và single point of failure; có thể chấp nhận trong pilot với availability giới hạn, không hứa HA.

TIP-064 là release gate cuối, không thay gate sớm. Chèn fault cases vào từng TIP. Soak 60 phút chỉ có nghĩa khi nêu workload, concurrency, latency/resource limits và mức phục hồi được yêu cầu.

## 5. Các giới hạn không được hứa vượt quá

| Kỳ vọng | Đánh giá |
|---|---|
| Chuyển process MT5 đang chạy sang VPS khác và giữ nguyên identity/evidence | Không được kiến trúc đề xuất hỗ trợ; plan đã xử lý đúng |
| Retry mọi timeout mà luôn không duplicate native side effect | Không thể cam kết với journal/observation còn không chắc chắn; cần UNKNOWN và reconcile |
| Node Windows Service Session 0 reuse tester hiện tại mà mọi job vẫn chạy | Không tương thích guard hiện tại; cần interactive worker hoặc thay execution model được qualify |
| Nhiều terminal ID nghĩa là workload độc lập | Sai nếu chung installation/data root/agent resources |
| Build 5233/5464/6230 có sẵn đúng như bảng minh họa | Chưa có bằng chứng. Inventory phải báo observed availability/build drift; không chọn build không tồn tại |
| Lease/worktree hoặc executable allowlist tạo OS sandbox | Không. Isolation của source và quyền hệ điều hành là hai lớp khác nhau |
| Snapshot toàn fleet cho tổng equity chính xác mặc định | Không nếu thiếu dedup, currency và freshness |

Build không thuộc stable terminal ID là quyết định đúng. Nhưng requested build policy nên có trong immutable request; observed build được ghi lúc execution. Auto-update trước start có thể làm job bị block do build drift. Candidate/baseline cùng terminal vẫn có thể không tương đương nếu build, broker, history/model/config khác; SAME_BUILD cũng không tự chứng minh equivalence.

## 6. Roadmap tôi sẽ dùng

Các tên A/B dưới đây là đề xuất chia scope, chưa phải TIP đã duyệt.

| Milestone | Nội dung | Giới hạn chủ động | Gate trước bước kế |
|---|---|---|---|
| M0 — Contract + TIP-055A | Persist stable device/terminal IDs; generation schema; target envelope; capability map; additive provenance | FIXED MT5-2 giữ nguyên; chưa mở native routing | Reboot/build update/alias rename semantics; duplicate binding/clone handling; legacy regression |
| M1 — Read Fleet | TIP-057 phần reads + 058 + 059 + snapshot tối thiểu của 062 | Hai node pilot; reads IPC serialize mỗi node; chưa remote native/mutation | Dữ liệu đúng device/root; offline partial; replay/revoke; gateway/node restart; bounded freshness |
| M2 — Native pinning | TIP-057 phần native + phần tối thiểu TIP-061 | Local routed native còn serialized; tester installations được chọn rõ; repo và executor cùng node | Exact physical target, baseline/resume, process ownership, rollback và artifact integrity |
| M3 — Remote Jobs | TIP-060; global routes + node-local reservation/journal | max_native_jobs=1 mỗi node; cross-device input transfer chưa mở | Duplicate/restart/crash windows; unknown outcome; exact cancel; gateway restore |
| M4 — Capacity | TIP-056 scoped concurrency | Chỉ installations/resources đã chứng minh độc lập | Capacity reservations; lock ordering; shared-resource conflicts; loaded soak |
| M5 — Multi-agent | TIP-063, Git worktree + authenticated ownership | Non-Git path lease chỉ thêm nếu có use case thật; Generic Repo Worker để sau | Stale epoch/session cannot mutate; recovery không replay mutation mất authority |
| Release | TIP-064 theo scope release | Không gọi fleet rộng hơn pilot đã qualify là production-ready | Fault matrix + workload/thresholds + migration/restore evidence |

Một job trên VPS-A và một job trên VPS-B có thể chạy đồng thời dù mỗi node capacity=1. Vì vậy local concurrency không phải điều kiện cần để chứng minh giá trị multi-VPS.

M1 đủ tạo giá trị quản lý toàn hệ thống và kiểm chứng protocol. Không cần worktree, path lease, transfer repo A→B hoặc generic runtime để giao M1. Qualification cuối vẫn có thể giữ ba VPS nếu mục tiêu release thật sự yêu cầu quy mô đó; pilot hai node được đánh giá trong phạm vi hai node.

## 7. Contract tối thiểu được đề xuất

### Identity và target

- Persist opaque IDs; alias/hostname là labels. Canonical installation/data-root là binding được kiểm tra, không phải ID suy lại tùy thời điểm.
- Một `route_generation` do gateway kiểm soát; một `terminal_generation` cho binding terminal. Chưa cần thêm `device_generation/target_generation` đồng nghĩa nếu không có use case riêng.
- Key rotation, identity replacement, re-pair và clone enrollment có semantics riêng. Không bake private key đã paired vào image VPS dùng để clone.
- Stable IDs giữ qua reboot; build update giữ terminal ID nhưng cập nhật observed build; đổi binding tăng terminal generation.
- Native request đóng băng target + generations + input manifest + build policy. Không thay target của job hiện hữu khi sửa project default.

### Authentication và lifecycle

- Node xác thực gateway qua TLS/service identity phù hợp threat model; gateway xác thực node. Ed25519 node request không tự giải quyết chiều gateway → node. Không nhất thiết thêm cả mTLS và command signatures nếu contract TLS đã đáp ứng yêu cầu.
- Canonical signed request, nonce/timestamp window, replay persistence và pairing expiry phải có acceptance. Pair/revoke là admin actions.
- Command có thể được delivery nhiều lần; execution phải dựa trên durable operation binding tại node. Tách transport ACK khỏi native-start evidence và result commit.
- Hết heartbeat của agent, mất node connection, worker death và terminal death là các sự kiện khác nhau. Không kill job vì agent mất lease.
- UNKNOWN outcome giữ nguyên operation/job identity, chặn auto redispatch mới tới khi reconcile.

### Baseline và Continuity

MVP chỉ mở một policy STRICT với target/generations và environment fingerprint; không phải implement ngay bốn policy. Fingerprint cần các trường có ảnh hưởng thật: terminal/compiler build, broker/server, tester model, effective period/config, input manifests và dữ liệu/history evidence theo mức có thể thu thập. Source candidate khác baseline là điều bình thường; đó không phải environment equivalence failure.

Cross-target comparison là phân tích compatibility, không tự nâng job thành baseline mới. Khi không thu được history identity đầy đủ, báo mức tương đương chưa xác minh thay vì tuyên bố reproducibility tuyệt đối.

## 8. Build gate cho gói đầu — không phải gate toàn roadmap

Trước TIP-055A chỉ cần chốt: scope additive identity, authority/persistence, schema ID/generation, legacy compatibility và testable AC. D-05 concurrency, D-06 transfer và D-10 multi-agent chưa cần chốt để build gói này.

Acceptance đề xuất:

1. Hai terminal bindings vật lý khác nhau nhận ID khác nhau; alias trùng giữa hai node không gây nhầm target.
2. Reboot và build update giữ ID; alias rename giữ ID; binding đổi tuân theo generation contract.
3. Hai registration trỏ cùng tài nguyên native bị phát hiện; không qualify như executors song song.
4. FIXED policy và native/source locks hiện tại vẫn có hiệu lực; target khác chưa được mở trả lỗi explicit trước side effect.
5. Job/result/session legacy còn đọc được; không sửa hash-bound historical bytes; provenance mới ghi rõ identity resolution source.
6. Catalog/schema có version và snapshot test phù hợp; connector thực tế nhìn thấy tools/fields của scope đã giao.

Completion Report cần mapping từng AC → kết quả và evidence, ghi rõ DONE/PARTIAL/BLOCKED, deviations và phần chưa qualify trên Windows. Tests Linux/mocks xác minh contract nhưng không chứng nhận native concurrency, GUI capture hoặc reboot recovery.

Trước M1 chốt thêm auth/enrollment, freshness/payload bounds, persistence recovery tối thiểu và pilot node readiness. Trước M3 chốt state machine/idempotency, project authority/baseline và input placement. Đây là việc chốt theo milestone, không phải kéo dài brainstorm tới khi mọi chi tiết tương lai đều hoàn hảo.

## 9. Tiêu chí qualification đề xuất

Đây là tiêu chí thiết kế để duyệt, chưa phải kết quả PASS:

- Zero wrong-device/terminal execution hoặc evidence attribution trong test matrix.
- Zero duplicate native starts cho cùng operation trong các crash/replay scenarios được định nghĩa; outcome chưa chứng minh phải UNKNOWN, không tự giả PASS.
- Zero source writes từ stale session/epoch; recovery path cũng phải validate original fencing authority trước phát sinh ghi mới.
- Zero cross-job process termination và artifact substitution; kiểm tra PID reuse và hash mismatch.
- Offline node không kéo toàn snapshot vượt deadline; coverage/errors/freshness explicit.
- Restart/restore không làm generations hoặc idempotency index rollback rồi redispatch âm thầm.
- Soak ghi workload, số jobs, concurrent reads/jobs, peak RAM/CPU/disk, queue waits, p95 latency, recovery intervals và thresholds chọn từ baseline trên máy thật.

Không đặt số latency/capacity tùy ý từ RAM trống một lần hoặc mặc định fleet có năm terminal nên chạy năm tester.

## 10. YAGNI-3 và kết luận theo Vibecode v6

1. **Cần tồn tại không?** Fleet identity/routing/read model có nhu cầu trực tiếp. Generic Repo Worker, pool scheduler và non-Git path lease chưa cần cho MVP.
2. **Có thể reuse gì?** Inventory, ToolFacade, job reserve/request hash, native process ownership, checkpoint/CAS, artifact manifests, Project Session/Iteration/Continuity. Không reuse bằng cách gỡ guard rồi tin tham số terminal sẽ đi đúng.
3. **Cách ngắn nhất là gì?** Hai node read fleet trước; giữ serialization; native jobs đồng node với repo; một project writer; thêm remote job proxy sau khi target lifecycle đã rõ.

**Vision: GO. Full implementation theo Task Graph hiện tại: NO-GO. TIP-055A thu gọn: conditional GO sau Blueprint nhỏ và AC cụ thể.** Tôi sẽ chuyển bản brainstorm thành Blueprint M0/M1 và TIP-055A trước, rồi giao build gói đầu; chưa mở concurrency, remote source mutation hoặc multi-agent chỉ vì chúng xuất hiện trong roadmap.

## Nguồn đối chiếu

- Plan gốc: `TunnelVibemq5-Fleet-Plan-Astra-Brainstorm.md`, đặc biệt §§3–4, 7–14, 24–29, 38–44 và A1–A8/B.
- Audit trước: `RemoteMCP-vs-TunnelVibemq5-Deep-Audit-2026-10-01.md`; findings RemoteMCP vẫn áp dụng ở HEAD đã xác nhận không đổi.
- [Tunnel facade: fixed target, live lease, compile/job calls](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/blob/64a62906b4e62274732f0cbc375bfb3687af9e42/app/vibemql5/core/facade.py)
- [Tunnel worker: fixed policy và lock order](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/blob/64a62906b4e62274732f0cbc375bfb3687af9e42/app/vibemql5/worker.py)
- [LiveTerminal: MetaTrader5 IPC và account fields](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/blob/64a62906b4e62274732f0cbc375bfb3687af9e42/app/vibemql5/core/live_terminal.py)
- [TesterDriver: Windows execution context/Session 0 guard](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/blob/64a62906b4e62274732f0cbc375bfb3687af9e42/app/vibemql5/core/tester.py)
- [Live terminal handoff](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/blob/64a62906b4e62274732f0cbc375bfb3687af9e42/app/vibemql5/core/terminal_handoff.py)
- [Job operation reservation](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/blob/64a62906b4e62274732f0cbc375bfb3687af9e42/app/vibemql5/core/jobs.py)
- [Baseline authority](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/blob/64a62906b4e62274732f0cbc375bfb3687af9e42/app/vibemql5/core/baseline.py)
- [Runtime capture authority](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/blob/64a62906b4e62274732f0cbc375bfb3687af9e42/app/vibemql5/runtime_forensics/authority.py)
- [MetaQuotes initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py) và [shutdown](https://www.mql5.com/en/docs/python_metatrader5/mt5shutdown_py): connection lifecycle; initialize có thể khởi động terminal. Khuyến nghị serialize IPC là suy luận thiết kế từ API và source, chưa phải phép thử concurrent Windows.
- [MetaTrader 5 platform start](https://www.metatrader5.com/en/terminal/help/start_advanced/start): nhiều platform cần installation directories khác nhau; data root còn phụ thuộc Windows account/mode.
- [SQLite Online Backup API](https://www.sqlite.org/backup.html): backup nhất quán cho database đang hoạt động.
- Vibecode Kit v6.0: SCAN → RRI → VISION → BLUEPRINT → TASK GRAPH → BUILD → VERIFY → REFINE; task đầu được thu gọn, verify theo output/AC.
