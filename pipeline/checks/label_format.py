"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    lf = cfg["label_format"]
    tol = lf["overflow_tol"]
    min_box_px = lf["min_box_px"]
    max_box_frac = lf["max_box_frac"]
    dup_box_iou = lf["dup_box_iou"]
    n_cls = len(ds.classes)
    issues = []

    for img in ds.image_files():
        stem = img.stem
        rows = ds.read_label_lines(stem)
        if rows is None:
            continue
        size = ds.image_size(stem)
        seen = []  # (cls, cx, cy, w, h) of valid geometry boxes so far

        for line_no, text in rows:
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem,
                                    f"dòng không đúng 5 cột số: {text!r}", line_no))
                continue

            if not (0 <= cls < n_cls):
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem,
                                    f"id lớp {cls} ngoài 0..{n_cls - 1}", line_no))
                continue

            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem,
                                    f"box rỗng w={w} h={h}", line_no))
                continue

            left, right = cx - w / 2, cx + w / 2
            top, bottom = cy - h / 2, cy + h / 2
            overflow = max(0.0 - left, right - 1.0, 0.0 - top, bottom - 1.0, 0.0)
            if overflow > tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                                    f"box tràn ảnh overflow={overflow:.4f}", line_no,
                                    {"overflow": overflow}))

            box = (cx, cy, w, h)
            for prev_cls, *prev_box in seen:
                if prev_cls == cls and iou_xywh(box, tuple(prev_box)) > dup_box_iou:
                    issues.append(Issue("label_format", ERROR, "DUP_BOX", stem,
                                        "box trùng với dòng trước cùng lớp", line_no))
                    break
            seen.append((cls, cx, cy, w, h))

            if w * h > max_box_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem,
                                    f"box quá lớn frac={w * h:.3f}", line_no))

            if size is not None:
                W, H = size
                short_px = min(w * W, h * H)
                if short_px < min_box_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem,
                                        f"cạnh ngắn {short_px:.1f}px < {min_box_px}", line_no))

    return issues
