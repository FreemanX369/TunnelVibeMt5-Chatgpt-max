# TunnelVibemq5 — Báo cáo fix và deploy ngày 17/10/2026

Trạng thái: **DONE trong phạm vi fix lỗi đã tái hiện và pilot control: A/B/C đã deploy, E2E và soak đạt**. Giờ trong báo cáo dùng Asia/Saigon (UTC+7). Phạm vi nghiệm thu là các lỗi đã tái hiện và pilot control trên một Windows VPS 2 GB RAM.

## Bản đang chạy

| Thành phần | Giá trị đã đối chiếu |
|---|---|
| Repository | FreemanX369/TunnelVibeMt5-Chatgpt-max |
| Source | `b34d28fd9f6c71eb8c6870039aec77a75284e469` |
| Variant | `LEGACY85_FLEET31_20261017_FIX4R2` |
| Entry SHA256 | `f82eb555e8444e78facb68cc58ac2916e6dae8eb07a60630e45acd150fc20d2e` |
| Manifest 95 file | `261d7a320526a584d78946e5863067c19e08a51b5a6dace423971606c5b9edf5` |
| Bootstrap ổn định | `operator-run-pilot-stable-entry.py`, SHA256 `b1538dd976b35dd982f396c6d7288017638aa23e4a78ecda340ff45aa78b853c` |
| Runner | SHA256 `6af2f0891738bb5ca84422435d19f76beac53971cf103697e323cc2784c41d63` |
| Catalog | 116 = 85 legacy + 31 Fleet; 115 model-visible, 1 app-only |
| Gateway | PID 5300; started 19:32:41; task priority 6; resume giữ journal |
| A MCP | PID 3756; đã gọi trực tiếp qua connector của chat hiện tại |
| Main | `70e2112da9fe8eaa6262f2ba896b55bf3e078260`, không merge |

Số build legacy vẫn có thể hiện TIP-053 / 0.2.42. Dùng `deployment_variant` và `integration_provenance` để đối chiếu bản ghép mới. Các file APP89 gốc giữ baseline `ae3125ef9bc6031163b47363a9799c4e6cbdd2e25c5b76760019f23e2e3749b1`; hai runtime override được khai báo rõ là safe error codes và Win32 process observation.

## Lỗi và thay đổi

| ID | Lỗi có bằng chứng | Cách sửa |
|---|---|---|
| D01 | Full journal validation làm proof hết freshness trước gửi | Validate/acquire transaction trước khi ký; deadline đã hết không tạo intent mới |
| D02 | Exception ở node làm đóng gateway chung | Retry có giới hạn, hết lượt thì fence; giữ gateway và journal, không tự reset |
| D03 | Quét toàn lịch sử mỗi lần làm vượt budget | Cache chỉ tại đúng SQLite/file/policy stamp; cold/tamper vẫn validate đầy đủ; digest hỗ trợ hơn 10k dòng |
| D04 | MCP che lỗi native busy hoặc lộ exception tùy ý | Mã lỗi cố định, retryability rõ; không trả raw exception/credentials |
| D05 | Read trả muộn làm dừng heartbeat | Giữ failed deadline/pending witness, tiếp tục control; không ACK giả |
| D06 | localhost thử address family không lắng nghe | Pin operator tới 127.0.0.1, giữ nguyên TLS hostname/SNI/CA và signed origin |
| D07 | WMI timeout bị hiểu nhầm là terminal không chạy | Dùng Win32 read-only; quan sát lỗi trả unavailable thay vì kết luận terminal đã dừng |
| D08 | Peer TLS hoặc HTTP chậm chiếm luồng authority | 8 I/O worker có giới hạn và queue có giới hạn; xác thực/ký/SQLite vẫn ở luồng owner cũ |
| O01 | Poll quá dày, task BelowNormal ảnh hưởng tiến độ | Pace theo heartbeat tối thiểu 1 giây; priority 6; giữ nguyên request deadline |
| O02 | Timer chụp stack sau startup trùng native crash | Bỏ timer diagnostic khỏi bootstrap production; giữ hash pin và receipt của runner |

D08 giữ semantics transaction đã được nhận: hoàn tất đúng một lần sau client timeout, không replay effect; response quá deadline vẫn bị bỏ. Ba assertion hồi quy durable-timeout không bị nới lỏng.

O02: Windows Application Error xác nhận python312.dll, exception `c0000005`, PID 3540, lúc 10:20:18; trace chụp stack bị cắt giữa chừng sau timer 20 giây. Đây là tương quan trực tiếp của lần crash; chưa khẳng định đã phân tích toàn bộ lỗi nội bộ CPython. Bản cùng source chạy lại bằng bootstrap không timer được kiểm qua E2E và soak. Không nâng Python/dependency.

## Kết quả VERIFY

| Bộ kiểm | PASS | SKIP | FAIL / ERROR |
|---|---:|---:|---:|
| 8 official workflow, đúng source SHA | 8 workflow | 0 | 0 |
| Linux full unit (1.663 case) | 1.644 | 19 | 0 |
| Windows full unit (1.663 case) | 1.650 | 13 | 0 |
| Windows VPS focused (52 case) | 51 | 1 | 0 |
| Predeploy recovery E2E | 51 | 0 | 0 |
| Postdeploy recovery E2E | 51 | 0 | 0 |
| Soak 600,6 giây / 60 mẫu | 60 | 0 | 0 |

Một SKIP của VPS focused: hệ điều hành không cho thay file khi SQLite đang mở; các ca tamper khác vẫn chạy. Không tính SKIP thành PASS.

Soak chạy 19:33:17–19:43:18: 60/60 PASS, PID5300 giữ nguyên, inventory p95 0,50 giây, tuổi LIVE lớn nhất 6,93 giây (giới hạn 20 giây). Cửa sổ bao gồm chuyển A/B/C và tải E2E hậu kiểm.

Predeploy chạy 19:33:18–19:33:58; hậu kiểm 19:38:43–19:39:17. Mỗi lượt kiểm full protocol schema legacy85/Fleet31, malformed typed input cho các Fleet tool, dữ liệu MT5, native serialization 3 client, 60 mixed calls, idempotent operation, native unqualified fail-closed và guard sạch.

| Mixed load | Thành công | p50 | p95 | Max |
|---|---:|---:|---:|---:|
| Trước chuyển profile, gateway mới | 60/60 | 0,072 s | 0,805 s | 0,817 s |
| Sau deploy cả A/B/C | 60/60 | 0,069 s | 0,763 s | 0,978 s |

Benchmark journal tổng hợp giữ đủ pending 1k/10k/50k: cold validation tương ứng 0,055 / 0,470 / 2,396 giây; warm p95 khoảng 0,0003 giây. Journal thật được mở kiểm read-only trước resume: 15.839 request, 25 pending, control revision 15.828; kiểm tra không ghi/ACK/reset. Cold validation thực tế 18,5 giây diễn ra trước khi ký request; không đánh đồng với warm benchmark.

CI: [run 38997804892](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/38997804892). JUnit artifact Linux 12088230799, Windows 12087699055; exact head và source unchanged được kiểm. Đây là kiểm CI trên runner riêng và kiểm runtime bằng tool; không có reviewer độc lập thứ hai.

## A/B/C

| Instance | Port | Tunnel PID | Healthz / Readyz | Profile sau deploy SHA256 |
|---|---:|---:|---|---|
| A | 8080 | 2892 | 200 / 200 | `bd26566eb9f7140addc58395ba3b17e7fd3b65e75e827158af810adb1fde844e` |
| B | 8081 | 5268 | 200 / 200 | `d953357d18fb7f6acd4b3eabd9a493fab38eafd02478ef1b03eff0f010e42412` |
| C | 8082 | 4820 | 200 / 200 | `c45bb3667d77297d54bcdf33d4cc43b957f20395e431927a1715f960564bb512` |

Mỗi tunnel có đúng một process. Poll diagnostics giữ lại 0 failure/0 episode. A đã kiểm trực tiếp entry/source và quote XAUUSDm qua MT5-2 build6230. E2E kiểm hash profile và ba process stdio thật theo từng profile. Không coi các process đó là ba tài khoản ChatGPT đã xác thực: backend stdio không cung cấp account identity đáng tin cậy.

MT5-2 PID6012 vẫn bắt đầu từ 15/10, không restart trong đợt deploy. Không đổi account, credentials hay AutoTrading; không đặt lệnh giao dịch. Năm terminal được đăng ký không đồng nghĩa năm terminal đang chạy.

## Các lượt bị loại

Giữ nguyên receipt FAIL; không ghi đè để biến thành đạt:

- FIX3: các soak trước có HTTPS_UNAVAILABLE/CONTROL_RETRY; riêng paced soak có 3 lỗi/60 mẫu.
- FIX4 candidate đầu: CI phát hiện 3 durable-timeout regressions; đã sửa trước source b34d28f.
- FIX4R2 predeploy với gateway FIX3: 49 PASS, 2 FAIL.
- FIX4R2 bootstrap có timer: 47 PASS, 4 FAIL; soak 0/60 vì LIVE stale sau native crash.
- Recovery: receipt mới ở `qa/predeploy-recovery`, `qa/postdeploy-recovery`, `qa/soak-recovery`; assertion và giới hạn freshness/deadline giữ nguyên.

## Phạm vi đạt và phần chưa chứng minh

Đạt kiểm catalog/schema 116 tool và các lời gọi nằm trong ma trận E2E. Không có tuyên bố đã gọi hợp lệ mọi chức năng mutation/native của cả 116 tool.

Pilot là **READY_CONTROL_ONLY**. Fleet SDK vẫn **UNQUALIFIED**, native capacity **NOT_QUALIFIED**, writer/worktree policy chưa bật. Ca `LIVE_ATTACH_ONLY_UNPROVEN` được kỳ vọng fail-closed; không tạo qualification giả để làm test xanh. Các thao tác Fleet native/writer đầy đủ còn cần qualification riêng. Trạng thái này không phải lỗi được che bằng retry.

Soak 10 phút chỉ chứng minh cửa sổ có ghi nhận, không chứng minh độ ổn định 24 giờ. A/B/C dùng chung một VPS. Nghiệm thu UI/session ChatGPT riêng trên B/C là lượt test cuối của chủ việc.

## Test cuối và rollback

Trên B/C, gọi `server_info`, `health`, `fleet_inventory`, `get_symbol_snapshot(symbol="XAUUSDm")`. Kiểm variant FIX4R2, source b34d28f, 116 tool, READY_CONTROL_ONLY và MT5-2. Tick quote có thể thuộc phiên trước vì thị trường đóng; observed_at là thời điểm đọc.

Nếu cần rollback profile, script `bind-integrated-profile.py --instance X --mode rollback` yêu cầu đúng hash đã apply, khôi phục byte backup bảo vệ của FIX3 rồi restart tunnel tương ứng. Rollback gateway chỉ sau khi chứng minh process hiện tại đã dừng; khôi phục task action từ XML backup và giữ nguyên SQLite/keys/pending. FIX3 từng lỗi soak nên rollback không tự được xem là nghiệm thu thành công.

Source PR [#69](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/69); deploy/evidence PR [#71](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/71), đều draft. Không direct-commit main.
