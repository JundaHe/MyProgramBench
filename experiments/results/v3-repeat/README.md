# v3 — exact repeat of the v2 isolated-netns pass (diagnostic, NOT the official definition)

Purpose: measure run-to-run variance of the gold scores. Result: the benchmark is essentially
deterministic — 178 of 200 tasks have identical raw pass rates to 3 decimals, and outside the
cases below only a handful of tests flip. The differences are infrastructure, not test flakiness:

- sqlite (0.858 → 0.016) and skeema (0.850 → 0.552): one big branch each exceeded programbench's
  3600 s per-branch `run_tests` timeout (sqlite's took 2240 s in v2) because the node was loaded
  (the dsh pilot ran concurrently) → branch `not_run`. Evaluations must run on a lightly loaded node.
- dog / oha / gping: v3 had no host-network re-run (v2 did), so their isolated-netns scores show.

`results/v2/` stays the official definition. See `scripts/score_gold_robust.py` for the min-over-runs
/ intersection-mask rule; to apply it fairly, v3 needs the host-network re-runs and a re-run of
sqlite/skeema on an idle node (TODO after the dsh pilot frees the CPU quota).
