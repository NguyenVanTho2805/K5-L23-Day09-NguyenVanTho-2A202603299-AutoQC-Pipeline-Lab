# Báo cáo Day 09 — Nguyễn Văn Thọ, 2A202603299

## 1. Kết luận trước

Pipeline kết luận **Hold** (mã thoát 10; `08_summary.json`).

- Đầu vào: **224** ảnh raw → intake giữ **203**, loại **21** (BAD_SIZE 3, CORRUPT_IMAGE 2, DUP_IMAGE_EXACT 8, DUP_IMAGE_NEAR 3, LEAK_TEST 5 — `01_intake.txt`).
- Sau autofix + người duyệt mô phỏng (80/80 ngân sách): **0 ERROR**, còn **38/203** ảnh cảnh báo (**warn_ratio = 18.72% ≥ 10%**) → Hold.
- Dataset nháp xuất `submission/export/clean_v1/` (**203** ảnh, `manifest.json`); Hold nên **chưa** được phát hành.

Lý do chính: không còn lỗi bắt buộc, nhưng hàng đợi cảnh báo lớn hơn ngân sách duyệt nên tỉ lệ ảnh còn WARN vượt cổng Hold.

## 2. Lỗi và phân việc

Nguồn: `02_error_list_v1.csv` — **210** issue trên **148** ảnh (sau intake). Kết luận trước, chi tiết sau.

| Mã lỗi | Số | Ai sửa | Vì sao |
|---|---:|---|---|
| BAD_FORMAT | 3 | máy | thiếu/thừa cột, nan → `drop_line` |
| BAD_CLASS_ID | 6 | máy | id ∉ 0..3 → `drop_line` |
| BOX_ZERO | 4 | máy | w/h ≤ 0 → `drop_line` |
| DUP_BOX | 7 | máy | IoU cao cùng lớp → `drop_line` |
| BOX_OUT_OF_IMAGE | 8 | máy | `clip_box` về [0,1]; hết diện tích thì drop |
| BAD_CLASS_NAME | 2 | máy | ghi lại `names` = `cfg["classes"]` |
| MISSING_LABEL_FILE | 6 ảnh | người | máy không bịa nhãn (`needs_label`) |
| BAD_SIZE / CORRUPT / DUP_* / LEAK_TEST | 21 ảnh | máy | loại ngay ở intake |
| POSSIBLE_MISSING | 53 | người | model thấy vật, nhãn thiếu |
| POSSIBLE_LOOSE_BOX | 28 | người | cùng lớp, box lỏng |
| POSSIBLE_WRONG_CLASS | 18 | người | khác lớp chồng vật |
| POSSIBLE_FALSE_POS | 29 | người | box nhãn không khớp pred |
| BOX_TINY / BOX_HUGE / EMPTY_LABEL / CLASS_RARE | 6 / 3 / 12 / 4 | người | quy tắc mềm / thống kê |

`03_fixes.csv`: **35** thay đổi = drop_line 20 + clip_box 8 + needs_label 6 + rename_classes 1. Sau sửa (`04_*`): còn **6 ERROR** (đều `MISSING_LABEL_FILE`) và **148 WARN**.

Hàng đợi `05_review_queue.csv`: **125** ảnh. Đầu hàng: `img_0020` (priority 11.524: FIXED_DROP_LINE + MISSING + WRONG_CLASS), rồi các `NEEDS_LABEL` (priority 10) — khớp `review.weights` (NEEDS_LABEL=10, WRONG_CLASS=3, MISSING=2). Ngân sách **80/125** (~64% hàng đợi): ưu tiên ảnh thiếu nhãn và nghi ngữ nghĩa; **45** ảnh còn lại chưa xem vẫn tính vào warn_ratio → giữ Hold.

Sau duyệt (`07_*`): **71** WARN / **0** ERROR; còn nhiều `POSSIBLE_FALSE_POS` (21) và `LOOSE_BOX` (20) trên ảnh ngoài ngân sách.

## 3. Calibration (2 ngưỡng)

Từ `submission/calibration/calibration_report.md`:

| Tham số | Khởi đầu | Đã chọn | P / R trước → sau | Lý do đánh đổi |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **8** | NEAR 1.00/0.50 → **1.00/0.67**; EXACT giữ 1.00/1.00 | FP khi xoá ảnh rất đắt → ưu tiên P=1.0. Giá trị 8 nằm cao nguyên 4–14 (R=0.67); không lấy 16 dù F1 NEAR cao hơn (0.91) vì calib nhỏ, dễ khớp nhầm trên raw |
| `second_opinion.conf` | 0.25 | **0.6** | WRONG 0.56/0.83 → **0.62/0.83**; MISSING 0.50/1.00 → **0.57/1.00** | Tăng conf giảm FP vào hàng đợi người; vẫn giữ recall MISSING = 1.0 trên calib. Từ 0.7 trở đi MISSING recall tụt (0.88 → 0.75) |

**Chỗ calibration đánh lừa:** tại `phash_dist=20`, EXACT recall rơi còn **0.33** trong khi bảng NEAR vẫn “trông được” — bộ calib chỉ 39 ảnh, một bước ngưỡng làm metric nhảy mạnh. Trên raw với ngưỡng 8, intake chỉ bắt **3 DUP_NEAR** (phash 0, 0, 6): số lượng hợp lý, không xoá ồ ạt. Nếu chọn 16 chỉ vì F1 max trên calib có thể loại ảnh khác nhau trên raw.

## 4. Cửa chặn và điểm mù

**(a) Gate chặn đúng.** Chạy:

`python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`

→ kết luận **Rework**, mã thoát **20**, log “KHÔNG xuất: còn lỗi bắt buộc” (6 `MISSING_LABEL_FILE` không ai gán). Thư mục `work/exp_nb` **không** được tạo. ERROR không bị ẩn bởi `reviewed`.

**(b) ≥ 2 điểm mù** (pipeline không / khó bắt):

1. **Trùng gần đúng biến đổi mạnh:** trên calib, `DUP_IMAGE_NEAR` recall chỉ 0.67 ở `phash_dist=8` — ảnh thu nhỏ/nén khác phash > 8 vẫn lọt.
2. **Box lỏng nhẹ / model cũng lệch:** `POSSIBLE_LOOSE_BOX` F1 ≈ 0.20 ở conf=0.6 — IoU nằm vùng mơ hồ hoặc checker sai thì không cờ / cờ giả.
3. **Nhầm lớp mà yolo26l cũng nhầm:** không sinh `POSSIBLE_WRONG_CLASS` → người không được nhắc.

## 5. Train: raw vs clean (tùy chọn)

Đã chạy trên Colab (yolo26n, 20 epoch, batch 16, imgsz 640, seed 0 & 1). Bảng từ `submission/results/comparison.md`:

| biến thể | #ảnh train | map50 (TB ± σ) | map50_95 | precision | recall |
|---|---:|---|---|---|---|
| raw | 224 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 203 | 0.699 ± 0.025 | 0.486 ± 0.013 | 0.796 ± 0.050 | 0.596 ± 0.049 |

Chênh mAP50 (clean − raw) = **−0.027**. Độ lệch giữa 2 seed của clean là **±0.025** → mức chênh **nằm trong nhiễu seed**, **chưa kết luận được** clean tốt hơn raw (thậm chí TB clean hơi thấp hơn).

Giả thuyết giải thích / cách kiểm:
1. **Ít ảnh train hơn** (203 vs 224 vì intake loại trùng/rò rỉ/hỏng) — kiểm: so AP theo lớp; truck clean seed0 chỉ 0.48 vs raw 0.66.
2. **Raw có thể hưởng lợi từ rò rỉ test** (5 LEAK_TEST đã loại) — kiểm: đối chiếu stem bị LEAK với `data/test`.
3. **Clean vẫn là bản Hold** (38 ảnh còn WARN chưa duyệt) — nhãn ngữ nghĩa chưa sạch hết có thể kéo recall xuống (0.596 vs 0.649).

Việc tiếp theo: tăng ngân sách duyệt rồi train lại clean; hoặc báo cáo Hold trung thực thay vì tối ưu mAP bằng cách nới QC.

## 6. Quyết định và ghi chú AI

**(a) Quyết định cuối: Hold.** Khớp số liệu v3 (**0 ERROR**, **38/203** ảnh còn WARN). Sáu ảnh `MISSING_LABEL_FILE` đã nằm đầu hàng đợi và được ngân sách 80 xử lý (v3 không còn ERROR). Để thành Release cần đưa warn_ratio < 10% (≤ **20** ảnh cảnh báo trên 203): tăng ngân sách duyệt thêm ~45 ảnh còn lại, hoặc siết ngưỡng `second_opinion` rồi chạy lại — không được “xóa tay” WARN để ép Release.

**(b) Dùng AI hỗ trợ viết 4 module.**

- Prompt chính: implement đúng docstring + bảng mã lỗi; ngưỡng lấy từ `cfg`, không hard-code.
- Cách kiểm: `pytest` từng module → full **79** tests; `pipeline.calibrate` + `pipeline.run`; đối chiếu `02/03/07/08`.
- Một lần AI/logic dễ sai: xoá từng dòng theo issue làm lệch số dòng khi file có dòng trống — sửa bằng cách đọc `splitlines()` theo số dòng gốc, gom drop/clip, ghi lại **một lần** mỗi file.
