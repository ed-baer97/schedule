import json
from pathlib import Path

src = Path(r"C:\Users\eduar\.cursor\projects\c-Users-eduar-Desktop-schedule\agent-transcripts\80736fc9-edd1-4ec6-8276-0ebc66e19894\80736fc9-edd1-4ec6-8276-0ebc66e19894.jsonl")
out_dir = Path(r"c:\Users\eduar\Desktop\Проект\schedule\_restore_tmp")

needles = ["subject_ids", "Classroom.subjects", "subjects = relationship"]
with src.open(encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        hits = [n for n in needles if n in line]
        if not hits:
            continue
        print(f"L{i} hits={hits} len={len(line)}")
        try:
            obj = json.loads(line)
        except Exception as e:
            print("  parse fail", e)
            continue
        msg = obj.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            print("  content str", content[:300])
            continue
        if not isinstance(content, list):
            print("  content type", type(content), list(msg.keys()))
            # maybe user message
            if "text" in str(msg)[:200]:
                pass
            continue
        for j, part in enumerate(content):
            if not isinstance(part, dict):
                continue
            t = part.get("type")
            name = part.get("name")
            inp = part.get("input") or {}
            p = str(inp.get("path") or "")
            body = ""
            if t == "text":
                body = part.get("text") or ""
            else:
                body = inp.get("contents") or inp.get("new_string") or inp.get("old_string") or ""
            joined = json.dumps(part, ensure_ascii=False)
            if any(n in joined for n in needles):
                print(f"  part{j} type={t} name={name} path={p} bodylen={len(body)}")
                if body and any(n in body for n in needles):
                    dest = out_dir / f"80736_subj_L{i}_p{j}_{name or t}_{Path(p).name or 'none'}.txt"
                    dest.write_text(body, encoding="utf-8")
                    print("    saved", dest.name)

# also dump the classroom.py write from L143
with src.open(encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if i != 143:
            continue
        obj = json.loads(line)
        for part in obj["message"]["content"]:
            if part.get("name") == "Write":
                body = part["input"]["contents"]
                dest = out_dir / "classroom_model_m2m.py"
                dest.write_text(body, encoding="utf-8")
                print("saved classroom_model_m2m.py", len(body))
