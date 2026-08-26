import json
from pathlib import Path

src = Path(r"C:\Users\eduar\.cursor\projects\c-Users-eduar-Desktop-schedule\agent-transcripts\80736fc9-edd1-4ec6-8276-0ebc66e19894\80736fc9-edd1-4ec6-8276-0ebc66e19894.jsonl")
out_dir = Path(r"c:\Users\eduar\Desktop\Проект\schedule\_restore_tmp")

with src.open(encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if i != 143:
            continue
        obj = json.loads(line)
        content = obj["message"]["content"]
        print("n parts", len(content))
        for j, part in enumerate(content):
            print("--- part", j, "type", part.get("type"), "name", part.get("name"))
            inp = part.get("input") or {}
            print("input keys", list(inp.keys()))
            for k, v in inp.items():
                if isinstance(v, str):
                    print(f"  {k}: str len={len(v)} preview={v[:120]!r}")
                else:
                    print(f"  {k}: {type(v).__name__} {v if not isinstance(v, dict) else list(v.keys())}")
            if part.get("name") == "Write":
                body = inp.get("contents") or inp.get("new_string") or ""
                path = inp.get("path") or f"unknown_part{j}"
                dest = out_dir / f"80736_L143_p{j}_{Path(str(path)).name or 'none'}.txt"
                dest.write_text(json.dumps(part, ensure_ascii=False, indent=2)[:20000], encoding="utf-8")
                print("saved", dest)
        # also search for classroom_subjects in the raw line
        idx = line.find("classroom_subjects = Table")
        print("raw idx classroom_subjects", idx)
        if idx >= 0:
            snippet = line[max(0, idx-400): idx+200]
            print("SNIPPET:", snippet[:600])
        # find all Write path occurrences
        k = 0
        needle = '"name": "Write"'
        while True:
            k = line.find(needle, k)
            if k < 0:
                break
            print("Write at", k, "context", line[k:k+500][:500])
            k += 1
