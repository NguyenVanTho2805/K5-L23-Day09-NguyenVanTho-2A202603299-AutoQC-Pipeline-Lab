"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems = set(image_stems)
    reviewed = set(reviewed)
    n_images = len(image_stems)

    errors = [i for i in issues if i.severity == ERROR]
    n_errors = len(errors)

    warn_images = set()
    for i in issues:
        if i.severity != WARN:
            continue
        if i.image not in stems:
            continue
        if i.image in reviewed:
            continue
        warn_images.add(i.image)
    n_warn_images = len(warn_images)
    warn_ratio = round(n_warn_images / n_images, 4) if n_images else 0.0

    reasons = []
    if n_errors:
        decision = "Rework"
        reasons.append(f"còn {n_errors} lỗi bắt buộc (ERROR) → Rework")
    else:
        thr = cfg["gate"]["warn_ratio_hold"]
        if warn_ratio >= thr:
            decision = "Hold"
            reasons.append(
                f"{n_warn_images}/{n_images} ảnh còn cảnh báo ({warn_ratio:.2%} ≥ {thr:.0%}) → Hold"
            )
        else:
            decision = "Release"
            reasons.append(
                f"0 lỗi bắt buộc; {n_warn_images}/{n_images} ảnh cảnh báo ({warn_ratio:.2%} < {thr:.0%}) → Release"
            )

    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": n_warn_images,
        "n_images": n_images,
        "warn_ratio": warn_ratio,
        "reasons": reasons,
    }
