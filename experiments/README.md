# ProgramBench experiments

Reproducing the ProgramBench evaluation protocol from the Anthropic Claude 5 model card
(§8.11.1) on the SOAR workstation, and recording every step so the numbers are auditable.

Target protocol (quoted from the model card):

> We excluded 34 tasks for which the reference binary itself scored below 0.9 on the hidden
> test suite (indicating test flakiness), leaving 166 tasks. Among those tasks, we score only
> against tests the reference binary passes. We report the hidden test pass rate using the
> same mini-swe-agent harness that the upstream repo uses, without the six-hour time limit.

## Layout

| Path | What |
|---|---|
| `docs/00-plan.md` | Overall plan and the decisions taken along the way |
| `docs/01-environment.md` | Workstation constraints (no Docker, Slurm, Apptainer) and what was probed |
| `docs/02-gold-run.md` | Step 1: reference-binary ("gold") evaluation → task exclusion list |
| `docs/03-mini-swe-agent.md` | mini-swe-agent harness setup (configured, out of scope) |
| `docs/04-exclusion-logic.md` | 剔除逻辑说明（中文）：gold run、raw 口径、阈值、mask 计分、已知偏差 |
| `docs/LOG.md` | Chronological experiment log (append-only) |
| `scripts/` | Every script used; nothing is run by hand without being recorded here |
| `results/` | Generated artefacts — **`v2v3-robust/` is the official definition** (exclusion list + scoring mask); `v2/`, `v3-repeat/`, `v1-hostnet/` are the single runs |

Companion checkouts (not in this repo):

- `/scratch/jundahe/ProgramBench` — upstream `facebookresearch/programbench` (v1.2.4, commit `963063c`)
