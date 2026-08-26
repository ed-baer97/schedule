import json
from pathlib import Path

src = Path(r"C:\Users\eduar\.cursor\projects\c-Users-eduar-Desktop-schedule\agent-transcripts\80736fc9-edd1-4ec6-8276-0ebc66e19894\80736fc9-edd1-4ec6-8276-0ebc66e19894.jsonl")
out_dir = Path(r"c:\Users\eduar\Desktop\Проект\schedule\_restore_tmp")
out_dir.mkdir(exist_ok=True)

n_lines = 0
n_writes = 0
write_paths = []
with src.open(encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        n_lines += 1
        try:
            obj = json.loads(line)
        except Exception as e:
            print(f"parse fail L{i}: {e} len={len(line)}")
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
            if name in ("Write", "StrReplace"):
                if "classroom" in p.lower() or "subject" in p.lower() or "dto" in p.lower() or "Classrooms" in p:
                    body = inp.get("contents") or inp.get("new_string") or ""
                    write_paths.append((i, name, p, len(body), (body[:80].replace("\n"," ") if body else "")))
            if name == "Write":
                n_writes += 1
                body = inp.get("contents") or ""
                fname = Path(p).name if p else f"unknown_{i}"
                # save all writes
                dest = out_dir / f"80736_L{i}_{fname}"
                dest.write_text(body, encoding="utf-8")
                print(f"WRITE L{i} {p} -> {dest.name} {len(body)}")

print("lines", n_lines, "writes", n_writes)
print("--- classroom-related ---")
for row in write_paths:
    print(row[0], row[1], row[2], "len", row[3], "|", row[4])
