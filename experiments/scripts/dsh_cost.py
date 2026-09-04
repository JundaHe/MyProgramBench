#!/usr/bin/env python3
"""Token usage and cost estimate for dsh runs, from the `usage` chunks in every session log
(parent + workflow children), per task and total.

    scripts/dsh_cost.py <out_dir> [<out_dir2> ...]

Prices are USD per million tokens (OpenRouter, 2026-09-04); cached input is billed at 10% of input
as an assumption — the exact discount depends on the provider route, so treat cost as an estimate.
"""

import json
import sys
from collections import Counter
from pathlib import Path

PRICE = {  # (input, output) per 1M tokens
    "deepseek/deepseek-v4-pro": (1.04, 2.08),
    "deepseek/deepseek-v4-flash": (0.09, 0.18),
    "deepseek-v4-pro": (1.04, 2.08),
    "deepseek-v4-flash": (0.09, 0.18),
}


def task_usage(tdir: Path) -> Counter:
    tot = Counter()
    for f in tdir.glob("dsh-home/sessions/**/session.jsonl"):
        seen = set()
        for raw in f.read_text(errors="replace").splitlines():
            if '"usage"' not in raw:
                continue
            ev = json.loads(raw)
            if ev.get("type") != "assistant/chunk":
                continue
            d = ev["data"]
            key = (d.get("turn"), d.get("step"))
            if key in seen:
                continue
            seen.add(key)
            u = d["chunk"]["usage"]
            for k in ("inputTokens", "outputTokens", "cacheReadTokens", "reasoningTokens"):
                tot[k] += u.get(k, 0)
            tot["requests"] += 1
    return tot


def main() -> None:
    grand = Counter()
    for out in map(Path, sys.argv[1:]):
        print(f"== {out}")
        for tdir in sorted(p for p in out.iterdir() if p.is_dir()):
            u = task_usage(tdir)
            if not u:
                continue
            model = json.loads((tdir / "params.json").read_text())["model"] if (tdir / "params.json").exists() else "?"
            pin, pout = PRICE.get(model, (0, 0))
            fresh = u["inputTokens"] - u["cacheReadTokens"]
            cost = (fresh * pin + u["cacheReadTokens"] * pin * 0.1 + u["outputTokens"] * pout) / 1e6
            u["cost_usd"] = cost
            grand.update(u)
            print(f"  {tdir.name:40s} req={u['requests']:5d} in={u['inputTokens']/1e6:7.2f}M (cached {u['cacheReadTokens']/1e6:6.2f}M) "
                  f"out={u['outputTokens']/1e6:6.2f}M reasoning={u['reasoningTokens']/1e6:5.2f}M  ≈ ${cost:7.2f}")
    print(f"TOTAL requests={grand['requests']} in={grand['inputTokens']/1e6:.2f}M out={grand['outputTokens']/1e6:.2f}M ≈ ${grand['cost_usd']:.2f}")


if __name__ == "__main__":
    main()
