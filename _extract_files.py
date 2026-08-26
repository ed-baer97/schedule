import json
from pathlib import Path

src = Path(r"C:\Users\eduar\.cursor\projects\c-Users-eduar-Desktop-schedule\agent-transcripts\f40306d7-d45b-4f0f-9eb8-44e2c78dbbcb\f40306d7-d45b-4f0f-9eb8-44e2c78dbbcb.jsonl")
out_dir = Path(r"c:\Users\eduar\Desktop\Проект\schedule\_restore_tmp")
out_dir.mkdir(exist_ok=True)

# exact endswith mapping, longest first
mapping = [
    ("app/domain/classroom_rules.py", "classroom_rules.py"),
    ("app/services/classroom_service.py", "classroom_service.py"),
    ("backend/schemas/classrooms.py", "schemas_classrooms.py"),
    ("backend/routers/classrooms.py", "routers_classrooms.py"),
    ("frontend/src/pages/ClassroomsPage.tsx", "ClassroomsPage.tsx"),
    ("frontend/src/api/classrooms.ts", "classrooms.ts"),
    ("frontend/src/domain/classroomRules.ts", "classroomRules.ts"),
    ("tests/test_classroom_rules.py", "test_classroom_rules.py"),
    ("app/models/classroom.py", "classroom_model.py"),
    ("app/models/subject.py", "subject_model.py"),
    ("app/services/dto.py", "dto.py"),
    ("frontend/src/api/schedule.ts", "schedule.ts"),
    ("frontend/src/pages/SchedulePage.tsx", "SchedulePage.tsx"),
]

last = {}
with src.open(encoding="utf-8") as f:
    for line in f:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        msg = obj.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "tool_use":
                continue
            name = part.get("name")
            inp = part.get("input") or {}
            p = str(inp.get("path") or "").replace("\\", "/")
            if name != "Write":
                continue
            body = inp.get("contents")
            if not body:
                continue
            for suf, outname in mapping:
                if p.replace("\\", "/").endswith(suf):
                    last[outname] = body
                    break

for name, body in last.items():
    (out_dir / name).write_text(body, encoding="utf-8")
    print(f"wrote {name} {len(body)} chars")

# dump 80736 writes for classroom model / dto / service
for transcript, tag in [
    (r"C:\Users\eduar\.cursor\projects\c-Users-eduar-Desktop-schedule\agent-transcripts\80736fc9-edd1-4ec6-8276-0ebc66e19894\80736fc9-edd1-4ec6-8276-0ebc66e19894.jsonl", "80736"),
    (r"C:\Users\eduar\.cursor\projects\c-Users-eduar-Desktop-schedule\agent-transcripts\2d7990ad-672a-45ee-bad1-39d6f223ce8c\2d7990ad-672a-45ee-bad1-39d6f223ce8c.jsonl", "2d799"),
]:
    src2 = Path(transcript)
    if not src2.exists():
        continue
    with src2.open(encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            msg = obj.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "tool_use":
                    continue
                name = part.get("name")
                inp = part.get("input") or {}
                p = str(inp.get("path") or "").replace("\\", "/")
                if name != "Write":
                    continue
                body = inp.get("contents") or ""
                if not body:
                    continue
                for suf, outname in mapping + [("migrations/versions/12classroom_subjects.py", "12classroom_subjects.py")]:
                    if p.endswith(suf):
                        dest = out_dir / f"{tag}_{outname}"
                        dest.write_text(body, encoding="utf-8")
                        print(f"wrote {dest.name} {len(body)} chars")
                        break
