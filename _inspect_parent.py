import json
from pathlib import Path

src = Path(r"C:\Users\eduar\.cursor\projects\c-Users-eduar-Desktop-schedule\agent-transcripts\2d7990ad-672a-45ee-bad1-39d6f223ce8c\2d7990ad-672a-45ee-bad1-39d6f223ce8c.jsonl")
out_dir = Path(r"c:\Users\eduar\Desktop\Проект\schedule\_restore_tmp")
out_dir.mkdir(exist_ok=True)

print("exists", src.exists(), "size", src.stat().st_size)
n = 0
with src.open(encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        n += 1
        try:
            obj = json.loads(line)
        except Exception as e:
            print(f"L{i} parse fail {e} len={len(line)}")
            continue
        role = obj.get("role")
        msg = obj.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            print(f"L{i} {role} str {content[:120]!r}")
            continue
        if not isinstance(content, list):
            print(f"L{i} {role} content={type(content)}")
            continue
        tools = []
        for j, part in enumerate(content):
            if not isinstance(part, dict):
                continue
            t = part.get("type")
            name = part.get("name") or t
            inp = part.get("input") or {}
            p = str(inp.get("path") or "")
            body = inp.get("contents") or inp.get("new_string") or ""
            if t == "text":
                txt = (part.get("text") or "")[:150].replace("\n", " ")
                print(f"L{i} {role} TEXT {txt}")
            elif name in ("Write", "StrReplace"):
                print(f"L{i} p{j} {name} {p} len={len(body)}")
                if body:
                    fname = Path(p).name if p else f"nopath_{i}_{j}"
                    dest = out_dir / f"parent_L{i}_p{j}_{name}_{fname}"
                    dest.write_text(body, encoding="utf-8")
            elif name in ("Task",):
                prompt = (inp.get("prompt") or "")[:200].replace("\n"," ")
                print(f"L{i} p{j} Task desc={inp.get('description')} prompt={prompt}")
            else:
                tools.append(name)
        if tools:
            print(f"L{i} {role} tools={tools[:12]}")
print("total lines", n)
