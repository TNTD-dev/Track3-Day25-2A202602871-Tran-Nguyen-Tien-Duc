# Lab 25B — Report

**Họ tên / nhóm:** Trần Nguyễn Tiến Đức / 2A202602871  **Commit:** CHƯA COMMIT THEO YÊU CẦU  **Điểm tự động:** 84 / 88 cục bộ; 4 điểm SLO ẩn do giảng viên chấm

> Kết quả chuẩn seed 25; độ ổn định kiểm tra thêm seed 26, 27. Chi tiết tái lập ở `reports/experiments/results.json`, `reports/scoreboard.multiseed.json` và các JSON/CSV cùng tên trong `reports/gameday/`, `reports/cache/`, `reports/slo.json`, `reports/workflows.json`.

## 1. Kết quả Game Day (naive vs của bạn)

| Băng | Client | availability | p95 (s) | amplification | retry_ratio | cost/turn | recovery (s) | PASS? |
|---|---|---:|---:|---:|---:|---:|---:|:---:|
| G1 | naive | 0.7194 | 7.157 | 7.738 | 6.738 | 2.163 | 4 | Không |
| G1 | yours | 1.0000 | 4.776 | 1.062 | 0.002 | 2.101 | 0 | Có |
| G2 | naive | 0.4560 | 15.034 | 9.904 | 8.904 | 4.627 | 155 | Không |
| G2 | yours | 1.0000 | 10.920 | 1.041 | 0.007 | 2.119 | 0 | Có |
| G3 | naive | 1.0000 | 4.768 | 1.164 | 0.164 | 2.328 | 0 | Không |
| G3 | yours | 1.0000 | 4.660 | 1.060 | 0.034 | 2.145 | 0 | Có |
| G4 | naive | 1.0000 | 13.764 | 1.004 | 0.004 | 2.008 | 0 | Không |
| G4 | yours | 1.0000 | 5.562 | 1.015 | 0.002 | 2.072 | 0 | Có |
| G5 | naive | 0.3699 | 5.359 | 17.030 | 16.030 | 2.124 | — | Không |
| G5 | yours | 0.8179 | 5.477 | 1.003 | 0.002 | 2.504 | — | Có |
| G6 | naive | 0.5170 | 4.836 | 12.344 | 11.344 | 2.009 | 0 | Không |
| G6 | yours | 1.0000 | 5.961 | 1.055 | 0.019 | 2.189 | 0 | Có |

Client của tôi có 0 retry lỗi 400, 0 vi phạm `retry-after`, 0 incompatible route. Với G5, client naive retry lỗi client 9.149 lần; client mới không retry lỗi client và availability vượt ngưỡng 0.78. Số liệu lấy từ JSON của `make compare`.

## 2. Cấu hình client và lý do

| Tham số | Giá trị | Vì sao (dựa trên băng nào, số liệu nào) |
|---|---:|---|
| attempt_timeout_s | 8.0 | G6 tránh chờ deployment A treo hết deadline; G4 p95 còn 5.562s. Thí nghiệm timeout 30s làm availability G6 giảm xuống 0.9488. |
| max_attempts_per_provider | 2 | Cho một lần retry transient rồi failover; amplification tối đa quan sát được chỉ 1.062 trên G1. |
| min_time_left_s | 1.0 | Không mở attempt khi deadline còn quá ngắn để xử lý; giới hạn từ simulator. |
| backoff_base_s / cap_s | 0.25 / 4.0 | Full jitter phân tán lượt retry; retry-after luôn được tôn trọng. G1 vi phạm giảm từ 36.027 xuống 0. |
| retry_budget_ratio | 0.1 | Khi breaker bị vô hiệu, G2 retry ratio là 0.058 với budget bật và 0.491 khi tắt. |
| retry_budget_min_per_s / max_tokens | 0.5 / 20 | Cho phép hồi phục retry có giới hạn sau thời gian yên; không để bucket tăng vô hạn. |
| breaker.window_size / min_calls | 20 / 10 | Tránh mở breaker vì vài mẫu ban đầu; phát hiện cả lỗi và call chậm. |
| breaker.failure_rate_threshold | 0.5 | Mở khi ít nhất nửa cửa sổ lỗi; chuyển tải trước khi retry làm đầy queue. |
| breaker.slow_call_s / slow_rate_threshold | 5.0s / 0.6 | Bắt brown-out không phát lỗi. G4 p95 client mới 5.562s so với 13.764s ở naive. |
| breaker.open_duration_s | 10.0 | Cho provider thời gian hồi phục; permit generation và probe hạn chế kiểm soát chuyển trạng thái. |
| breaker.half_open_max_probes / successes | 2 / 2 | Giới hạn lượng tải thăm dò và chỉ đóng sau hai probe thành công. |
| quota_cooldown_s | 300 | Hết quota không thể sửa bằng retry; tránh gửi lại vào deployment A trong băng G5. |

Quyết định `on_error`:

| Loại lỗi | Ghi breaker | Retry cùng provider | Failover | Cooldown |
|---|---|---|---|---|
| 400 / client error | Release permit | Không | Không | Không |
| 429 insufficient quota | Release permit | Không | Có | 300s |
| 429 rate limit | Release permit | Không | Có ngay | Tối thiểu `retry_after` |
| 529 / 503 / 5xx / timeout | Ghi failure | Nếu còn lượt, budget và deadline | Nếu không retry được | Breaker tự mở theo tỷ lệ |
| Thành công chậm | Ghi success chậm | — | — | Breaker mở theo slow rate |

## 3. Ba thí nghiệm (số liệu seed 25)

1. **Retry budget là lớp phòng thủ cuối.** Đặt breaker `min_calls=1.000.000.000` và tối đa 5 lần thử mỗi provider. Ở G2, bật budget cho amplification 1.383, retry ratio 0.058, availability 0.9987; tắt budget tăng các số đó thành 1.672, 0.491 và availability còn 0.9649. G3 có retry ratio 0.068 khi bật budget và 0.162 khi tắt, dù availability đều 1.0. Breaker đang hoạt động vẫn cần budget để giới hạn khuếch đại trong lúc breaker chưa đủ mẫu, cấu hình sai hoặc outage phân tán.

2. **`attempt_timeout_s: 30`.** Trên G6, timeout mặc định cho availability 1.0, p95 6.016s, không GiveUp; đặt 30s làm availability còn 0.9488 với 109 GiveUp vì deadline và 13 vì hết provider. p95 giảm còn 5.306s vì percentile chỉ tính lượt thành công: các lượt treo bị loại khỏi mẫu (survivorship bias). G4 gần như không đổi: availability vẫn 1.0, p95 từ 5.604 lên 5.683s vì provider vẫn phản hồi. Timeout nên dựa vào p99 bình thường, phần deadline còn lại và thời gian cần để failover.

3. **Bỏ lọc tool calling khỏi `ladder()`.** G6 tăng `incompatible_routes` từ 0 lên 258 và availability giảm từ 1.0 xuống 0.8918. Với người dùng sản phẩm, 258 lượt được gửi đến model không có khả năng gọi tool nên không thể hoàn tất luồng refund. Check của G6 yêu cầu route không tương thích bằng 0; đây là bảo đảm chức năng của fallback, không chỉ là tối ưu latency.

## 4. Workflow hoàn tiền

| Executor | completion | crashes | duplicate refunds | duplicate emails | lost refunds | overpaid (cent) | wasted LLM / crash |
|---|---:|---:|---:|---:|---:|---:|---:|
| naive | 1.000 | 81 | 128 | 81 | 0 | 1.496.700 | 1.123 |
| yours | 1.000 | 66 | 0 | 0 | 0 | 0 | 0.303 |

Idempotency key bảo vệ side effect khi response mất và payment đã được thực hiện; checkpoint giúp worker mới resume, không chạy lại các bước trước. Chỉ checkpoint không ngăn payment bị chạy lại nếu worker chết sau khi payment commit nhưng trước khi lưu checkpoint. Nếu checkpoint trước khi gọi payment, crash ở khoảng giữa hai thao tác sẽ khiến workflow tưởng refund đã xong dù chưa có tiền được hoàn.

## 5. Alerting & error budget

| Sự cố | Mong đợi | Naive alerter | Burn-rate alerter | Độ trễ phát hiện burn-rate (phút) |
|---|---|---|---|---:|
| checkout_bug | page | page | page | 27 |
| provider_outage | page | page | page | 4 |
| deploy_blip | none | false page | none | — |
| slow_leak | ticket | không phát hiện | ticket, không page | 1337 |
| degraded_evening | page | page | page | 291 |
| night_spike | none | false page | none | — |
| small_bump | none | false page | none | — |

Burn-rate phát 3 page, 1 ticket và 0 false page; naive phát 7 page, bỏ lỡ ticket chậm và có 3 false page. Trong 30 ngày dữ liệu có 25.901.755 request, budget cho phép 129.508,8 lỗi; đã tiêu 55.618 (42,95%), còn 57,05%, availability 99,7853%. **Không freeze release** theo dữ liệu public này. `small_bump` là 20 phút với 12% lỗi; hai cửa sổ burn-rate không đồng thời đạt 14,4× nên không đánh thức on-call giữa trưa vì một đợt ngắn chưa đe dọa đáng kể ngân sách.

## 6. Postmortem — Băng G2 với client naive (blameless)

**Tóm tắt:** Alpha mất 75% năng lực trong ba phút. Client naive gửi 34.475 attempts cho 3.481 logical calls, đạt amplification 9.904; chỉ 1.077/2.362 lượt user thành công. Sau khi năng lực provider trở lại ở giây 300, hệ thống cần thêm 155 giây để đạt 95% success trong cửa sổ 30 giây.

**Ảnh hưởng:** 1.285 trong 2.362 lượt user thất bại (54,4%); độ trễ p95 của lượt thành công là 15,034s. Tính theo 4 turn/s ổn định trong tháng 30 ngày, tháng có 10.368.000 lượt và ngân sách lỗi 51.840 lượt; sự cố này tiêu khoảng 2,48% ngân sách tháng. Đây là ước tính theo tải cấu hình, không phải SLI production.

**Timeline** — mỗi dòng cho biết trung bình 30 giây kết thúc tại mốc đó; attempts/s gồm mọi provider:

| t (s) | Sự kiện | Attempts/s | Tỷ lệ call thành công trong cửa sổ |
|---:|---|---:|---:|
| 120 | Alpha bắt đầu mất GPU | 7,8 | 100% |
| 150 | Queue bắt đầu phình do timeout và retry | 96,0 | 46,8% |
| 180 | Tải retry lấn át năng lực xử lý | 139,8 | 0% |
| 240 | Provider vẫn suy giảm; tầng retry tiếp tục gửi vào Alpha | 147,6 | 0% |
| 299 | Cuối thời gian suy giảm | 155,8 | 0% |
| 300 | Alpha phục hồi năng lực, nhưng queue request cũ còn tồn tại | 155,4 | 0% |
| 330 | Tải hạ nhưng lượt user vẫn chưa phục hồi | 19,8 | 0% |
| 455 | Thời điểm đạt 95% thành công liên tục trong 30s (recovery=155s) | — | ≥95% |
| 480 | Sau khi backlog thoát, success ratio cửa sổ là 91,2% | 11,2 | 91,2% |

**Trigger và root cause:** Trigger là alpha mất 75% năng lực GPU. Root cause là retry chồng tầng, delay cố định, không retry budget và không breaker. Retry thêm tải lên hàng đợi; timeout chỉ làm client bỏ cuộc, không hủy request phía provider. Vì vậy sau giây 300, provider vẫn xử lý nhiều request cũ mà client không còn chờ, trong khi retry mới tiếp tục đến. Tải vượt năng lực drain của queue và tạo metastable failure.

**Điều giúp và điều làm tệ hơn:** Người dùng có deadline 30 giây, giới hạn được thời gian chờ từng lượt. Ngược lại, 5.931 timeout/overload errors và 26.298 rate limit errors cho thấy lượng công việc phí lớn; retry cố định dẫn tới 28.381 lần vi phạm retry-after. Fallback provider và jitter/budget/breaker sẽ giảm tải lên deployment đã suy giảm.

**Action items:**

| # | Hành động | Loại | Owner | Cách kiểm chứng |
|---|---|---|---|---|
| 1 | Chuẩn hóa retry một tầng, full jitter và token budget trong SDK agent | Prevent | Agent Platform | G2 CI: amplification ≤1,2 trên 3 seed; retry ratio ≤0,10 |
| 2 | Phát page theo multi-window SLO burn rate và dashboard queue/timeout | Detect | SRE | Dữ liệu replay: phát hiện outage trong ≤5 phút; 0 false page trên blip |
| 3 | Bật breaker theo slow/error rate, HALF-OPEN tối đa 2 probe và fallback capability-aware | Mitigate | Inference Platform | G2 recovery ≤30s; G6 incompatible routes =0; traffic primary ≥80% sau phục hồi |

## 7. Một điểm yếu còn lại

G2 availability đạt 100%, nhưng p95 end-to-end vẫn là 10,920s do queue và fallback làm tăng latency. Bước tiếp theo là tách ngân sách deadline giữa tool/chat, đo p99 theo từng deployment và cân nhắc spillover sớm hơn khi queue latency vượt ngưỡng; chỉ thay cấu hình sau khi kiểm tra lại availability, cost và phục hồi trên nhiều seed.

## 8. Cache (Part G)

| Client | availability | faq_availability | cache_hit_ratio | stale_served | wrong_answers | outdated_answers | cost/turn | PASS? |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| resilient (không cache) | 0.8373 | 0.8424 | 0.000 | 0 | 0 | 0 | 1.386 | Không |
| cached (của bạn) | 0.9124 | 0.9645 | 0.592 | 192 | 0 | 2 | 0.955 | Có |

| Tham số `cache:` | Giá trị | Vì sao (số liệu nào) |
|---|---:|---|
| similarity_threshold | 0.95 | 0.80 gây 182 `other_question`; 0.95 giữ 0 wrong với hit ratio 0.592; 0.97 giảm hit còn 0.495 và không đạt ngưỡng 0.5. |
| ttl_s | 30 | 30s có hit 0.592 và 2 outdated; 60s có hit 0.652/3 outdated; 300s có 95 outdated, vượt giới hạn 15. |
| max_stale_s | 350 | Cửa stale đủ phủ outage 120s từ entry được tạo trước outage; đạt FAQ availability 0.9645. Đặt 0 làm FAQ availability còn 0.8529 và hit ratio 0.480. |
| max_entries | 500 | Sau C1 cache giữ 35 entry (35/500), tránh tăng không giới hạn trong khi không cần eviction ở tải FAQ này. |

**Thí nghiệm:** Threshold 0.80 trả nhầm 182 câu hỏi gần nghĩa nhưng khác intent (`other_question`); 0.95 không trả sai; 0.97 quá nghiêm nên hit ratio thấp hơn ngưỡng. TTL 300 làm outdated tăng lên 95 vì thay đổi shipping không có webhook; webhook chỉ xóa tài liệu được thông báo, do đó TTL là giới hạn thời gian cho dữ liệu không được báo đổi. Tắt stale-if-error làm FAQ availability giảm từ 0.9645 xuống 0.8529, vì FAQ trong lúc provider outage không còn câu trả lời dự phòng.

Câu hỏi cá nhân không được cache kể cả theo user vì trạng thái đơn hàng, hoàn tiền và điểm có thể đổi ngay sau khi cache được tạo; scope theo user không bảo đảm freshness và vẫn có nguy cơ lộ thông tin khi ghép nhầm định danh. Khi cache che outage, alert theo tỷ lệ lỗi/timeout từng provider, breaker OPEN, `stale_served` và FAQ miss/fallback; chỉ nhìn availability user sẽ bỏ sót lỗi hạ tầng.
