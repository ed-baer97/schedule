import json
from pathlib import Path

root = Path(r"C:\Users\eduar\.cursor\projects\c-Users-eduar-Desktop-schedule\agent-transcripts")
wanted = [
    "classroom_rules.py",
    "classroom_service.py",
    "backend/schemas/classrooms.py",
    "backend/routers/classrooms.py",
    "ClassroomsPage.tsx",
    "api/classrooms.ts",
    "classroomRules.ts",
    "models/classroom.py",
    "models/subject.py",
    "test_classroom_rules.py",
    "12classroom_subjects.py",
]

hits = []
for path in root.rglob("*.jsonl"):
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            try:
                obj = json.loads(line)
            except Exception:
                continue
            msg = obj.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") != "tool_use":
                    continue
                name = part.get("name")
                inp = part.get("input") or {}
                p = str(inp.get("path") or "")
                if name not in ("Write", "StrReplace"):
                    continue
                if any(w.replace("\\", "/") in p.replace("\\", "/") for w in wanted):
                    body = inp.get("contents") or inp.get("new_string") or ""
                    hits.append((path.name, i, name, p, len(body)))

for h in hits:
    print(f"{h[0]} L{h[1]} {h[2]} {h[3]} len={h[4]}")
print("TOTAL", len(hits))
