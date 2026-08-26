import json
from pathlib import Path

root = Path(r"C:\Users\eduar\.cursor\projects\c-Users-eduar-Desktop-schedule\agent-transcripts")
needles = [
    "room_has_subject",
    "_sync_subjects",
    "_normalize_subject_ids",
    "subject_ids: frozenset",
    "form.subject_ids",
    "classroom-subjects-picker",
    "toggleSubject",
    "roomHasSubject",
    "своих предметов",
    "selectinload(Classroom.subjects)",
    "payload.subject_ids",
]

out_dir = Path(r"c:\Users\eduar\Desktop\Проект\schedule\_restore_tmp")

for path in sorted(root.rglob("*.jsonl")):
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            hits = [n for n in needles if n in line]
            if not hits:
                continue
            rel = str(path.relative_to(root))
            print(f"{rel} L{i} hits={hits} linelen={len(line)}")
            try:
                obj = json.loads(line)
            except Exception:
                continue
            msg = obj.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for j, part in enumerate(content):
                if not isinstance(part, dict) or part.get("type") != "tool_use":
                    continue
                name = part.get("name")
                inp = part.get("input") or {}
                p = str(inp.get("path") or "")
                body = inp.get("contents") or inp.get("new_string") or ""
                if not body:
                    continue
                if any(n in body for n in needles):
                    fname = Path(p).name if p else f"nopath_{i}_{j}"
                    dest = out_dir / f"hit_{path.stem}_L{i}_p{j}_{name}_{fname}"
                    dest.write_text(body, encoding="utf-8")
                    print(f"  saved {dest.name} path={p} nametool={name} len={len(body)}")
