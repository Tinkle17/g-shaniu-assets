#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REQ=ROOT/"requests"

def main():
    files=sorted(REQ.glob("*.json")) if REQ.exists() else []
    if not files:
        print('{"status":"no_requests"}')
        return
    done=[]
    for p in files:
        data=json.loads(p.read_text())
        post_id=str(data.get("post_id") or "")
        series=str(data.get("series") or "")
        episode=str(data.get("episode") or "")
        subprocess.run([
            sys.executable,str(ROOT/"scripts/import_from_bridge.py"),
            "--post-id",post_id,"--series",series,"--episode",episode
        ],cwd=ROOT,check=True)
        p.unlink()
        done.append({"request":p.name,"series":series,"episode":episode})
    print(json.dumps({"status":"processed","requests":done},ensure_ascii=False))

if __name__=="__main__":
    main()
