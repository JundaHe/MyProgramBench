#!/usr/bin/env python3
"""Extract the experiment record from one dsh task directory (<out>/<iid>/):

  workflows/NN-<name>.js      the model-authored dynamic-workflow script (the plan) of each `workflow` call
  workflows/NN-<name>.json    its meta, args, the tool result, and the tool-workflow/* run/agent records
  prompt.txt                  the first user prompt as the model received it
  summary.json                counts: model calls, tool calls by name, workflow runs, child agents

Schema-agnostic on purpose: the session log (dsh-home/sessions/**/session.jsonl, one JSON object per
line) is walked recursively for objects that carry a `script` + `meta` pair (a workflow tool call) and
for events whose type starts with `tool-workflow/`. Re-runnable; overwrites its outputs.

    scripts/dsh_extract.py <task_dir>
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path


def walk(o, path=()):
    yield path, o
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, path + (k,))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, path + (i,))


def main() -> None:
    tdir = Path(sys.argv[1])
    lines = []
    for f in sorted(tdir.glob("dsh-home/sessions/**/session.jsonl")):
        for raw in f.read_text(errors="replace").splitlines():
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
    wdir = tdir / "workflows"
    wdir.mkdir(exist_ok=True)
    calls, records, tools, prompt = [], [], Counter(), None
    n_model = 0
    results = {}
    for ev in lines:
        text = json.dumps(ev)
        if '"tool-workflow/' in text:
            records.append(ev)
        d = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        if ev.get("type") == "tool/call" and isinstance(d.get("name"), str):  # dsh: {name, arguments: "<json string>", callId}
            tools[d["name"]] += 1
            if d["name"] == "workflow":
                try:
                    a = json.loads(d.get("arguments") or "{}")
                except json.JSONDecodeError:
                    a = {"script": d.get("arguments"), "meta": {"name": "unparsed"}}
                calls.append({"callId": d.get("callId"), "time": ev.get("time"), "meta": a.get("meta") or {}, "script": a.get("script") or "", "args": a.get("args")})
        if ev.get("type") == "tool/result":
            cid = (d.get("message") or {}).get("source", {}).get("callId")
            if cid:
                results[cid] = json.dumps((d.get("message") or {}).get("content"))[:20000]
        if prompt is None and re.search(r'"role":\s*"user"', text):
            for p, o in walk(ev):
                if isinstance(o, dict) and o.get("role") == "user":
                    c = o.get("content")
                    prompt = c if isinstance(c, str) else json.dumps(c)[:20000]
                    break
        if '"role": "assistant"' in text or '"role":"assistant"' in text:
            n_model += 1
    for i, c in enumerate(calls, 1):
        name = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(c["meta"].get("name", "workflow")))[:40]
        (wdir / f"{i:02d}-{name}.js").write_text(c["script"])
        (wdir / f"{i:02d}-{name}.json").write_text(json.dumps({
            "meta": c["meta"], "args": c["args"], "callId": c["callId"], "time": c["time"], "result": results.get(c["callId"]),
        }, indent=1))
    (wdir / "records.json").write_text(json.dumps(records, indent=1))
    if prompt:
        (tdir / "prompt.txt").write_text(prompt)
    (tdir / "summary.json").write_text(json.dumps({
        "session_events": len(lines), "assistant_turns": n_model, "tool_calls": dict(tools),
        "workflow_calls": len(calls), "workflow_records": len(records),
    }, indent=1))
    print(f"{tdir.name}: {len(lines)} events, {len(calls)} workflow calls, tools={dict(tools)}")


if __name__ == "__main__":
    main()
