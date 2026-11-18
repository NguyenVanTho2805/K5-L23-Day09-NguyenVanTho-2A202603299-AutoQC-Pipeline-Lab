"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def _is_remove(code: str) -> bool:
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _clip_box(cls, cx, cy, w, h):
    left, right = cx - w / 2, cx + w / 2
    top, bottom = cy - h / 2, cy + h / 2
    left = max(0.0, min(1.0, left))
    right = max(0.0, min(1.0, right))
    top = max(0.0, min(1.0, top))
    bottom = max(0.0, min(1.0, bottom))
    nw, nh = right - left, bottom - top
    if nw <= 0 or nh <= 0:
        return None
    return cls, (left + right) / 2, (top + bottom) / 2, nw, nh


def fix(ds, issues, cfg):
    fixes = []
    errors = [i for i in issues if i.severity == ERROR]

    # 1) remove images first
    removed = set()
    for iss in errors:
        if not _is_remove(iss.code):
            continue
        stem = iss.image
        if stem in removed:
            continue
        ip = ds.image_path(stem)
        before = ip.name if ip else stem
        if ip and ip.exists():
            ip.unlink()
        lp = ds.label_path(stem)
        if lp.exists():
            lp.unlink()
        ds._size_cache.pop(stem, None)
        removed.add(stem)
        fixes.append({
            "image": stem, "line": "", "action": "remove_image",
            "before": before, "after": "(đã xoá)",
        })

    # 2) rename classes in data.yaml
    for iss in errors:
        if iss.code != "BAD_CLASS_NAME":
            continue
        before = ds.yaml_path.read_text(encoding="utf-8") if ds.yaml_path.exists() else ""
        data = {}
        if ds.yaml_path.exists():
            data = yaml.safe_load(before) or {}
        data["names"] = list(cfg["classes"])
        ds.yaml_path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        fixes.append({
            "image": "data.yaml", "line": "", "action": "rename_classes",
            "before": before.strip().replace("\n", " | "),
            "after": str(cfg["classes"]),
        })
        break

    # 3) needs_label (no file created)
    for iss in errors:
        if iss.code != "MISSING_LABEL_FILE":
            continue
        if iss.image in removed:
            continue
        fixes.append({
            "image": iss.image, "line": "", "action": "needs_label",
            "before": "(không có file)", "after": "chuyển người gán",
        })

    # 4) per-file line fixes (drop / clip), one rewrite per file
    by_image = defaultdict(list)
    for iss in errors:
        if iss.image in removed:
            continue
        if iss.code in DROP_CODES or iss.code == "BOX_OUT_OF_IMAGE":
            if iss.line is None:
                continue
            by_image[iss.image].append(iss)

    for stem, stem_issues in by_image.items():
        lp = ds.label_path(stem)
        if not lp.exists():
            continue
        raw_lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()

        drop_lines = set()
        clip_lines = set()
        for iss in stem_issues:
            if iss.code in DROP_CODES:
                drop_lines.add(iss.line)
            elif iss.code == "BOX_OUT_OF_IMAGE":
                clip_lines.add(iss.line)
        # drop wins over clip
        clip_lines -= drop_lines

        new_lines = []
        file_fixes = []
        for idx, text in enumerate(raw_lines, 1):
            if idx in drop_lines:
                file_fixes.append({
                    "image": stem, "line": idx, "action": "drop_line",
                    "before": text, "after": "(xoá)",
                })
                continue
            if idx in clip_lines and text.strip():
                try:
                    cls, cx, cy, w, h = parse_yolo_line(text)
                except ValueError:
                    file_fixes.append({
                        "image": stem, "line": idx, "action": "drop_line",
                        "before": text, "after": "(xoá)",
                    })
                    continue
                clipped = _clip_box(cls, cx, cy, w, h)
                if clipped is None:
                    file_fixes.append({
                        "image": stem, "line": idx, "action": "drop_line",
                        "before": text, "after": "(xoá)",
                    })
                    continue
                c2, x2, y2, w2, h2 = clipped
                after = f"{c2} {x2:g} {y2:g} {w2:g} {h2:g}"
                # keep a stable readable form close to test expectation
                after = f"{c2} {x2} {y2} {w2} {h2}"
                file_fixes.append({
                    "image": stem, "line": idx, "action": "clip_box",
                    "before": text, "after": after,
                })
                new_lines.append(after)
                continue
            new_lines.append(text)

        lp.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
        fixes.extend(file_fixes)

    return fixes
