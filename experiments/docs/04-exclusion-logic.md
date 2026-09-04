# Task 剔除逻辑（benchmark 定义）

本文描述我们如何从 ProgramBench 的 200 个 task 里剔除"reference binary 自己都跑不过"的 task，
以及剩余 task 上怎么计分。目标是复现 Claude 5 model card §8.11.1 的协议：

> We excluded 34 tasks for which the reference binary itself scored below 0.9 on the hidden test
> suite (indicating test flakiness), leaving 166 tasks. Among those tasks, we score only against
> tests the reference binary passes.

结论先行：**一个 task 被剔除，当且仅当 reference binary 在该 task 的全部 hidden tests 上的通过率 < 0.9。**
剔除的是 task，不是单个测试；单个测试的过滤靠第 4 节的 mask。

## 1. 什么是 "reference binary 的分数"（gold run）

1. **Gold submission**：每个 task 一份 `submission.tar.gz`，里面只有一个 `compile.sh`，内容是把镜像自带的
   reference binary（`/workspace/executable`，由 shim 在容器启动时复制到 `/opt/programbench-reference/`）
   `cp` 成 `./executable`。也就是说被测的二进制**就是** ProgramBench 发布的 reference binary，逐字节一致。
   - 唯一例外 **tinycc**：tcc 运行时需要 `make install` 装进 `/usr/local/lib/tcc` 的头文件和 `libtcc1.a`，
     cleanroom 镜像里没有，光复制二进制无法工作。这个 task 的 gold 改为从上游源码（同一 commit）
     离线构建（`scripts/make_gold_run.py --source-overrides`）。
2. **评测器**：未修改的 `programbench eval` v1.2.4。唯一的差别是 Docker 换成 Apptainer（`scripts/pbdocker`），
   见 `01-environment.md`。
3. **单次测量**：和 model card 一样只测一次（v2 pass）。

## 2. 分母：hidden test suite 的定义（raw，不套 ignore 列表）

每个 task 的分数 = `passed / 全部 test_results`，其中：

- `全部 test_results` = 评测器实际跑出来的每一条测试记录（所有 branch），**不**应用公开仓库
  `tests.json` 里的 `ignored_tests` / `ignored` branch 列表。
- 状态不是 `passed` 的一律算不通过：`failure`、`error`、`skipped`（例如 "requires extension"）、
  `not_run`（整个 branch 收集失败时评测器为该 branch 每个测试补的记录）。这与 `programbench` 自己的
  `EvaluationResult.score`（`n_resolved / len`）一致。

为什么不套 ignore 列表：`tests.json` 的 ignore 列表本身就是 upstream 用 gold 跑出来后剔掉的
（`gold_fail` 31k、`dummy_pass` 36k 条……）。先剔再算，gold 的通过率中位数变成 0.9999，只有 9 个 task
低于 0.9；按原始测试算是 22 个（v1 数据），和 model card 的 34 个在同一量级。model card 的措辞
"on the hidden test suite" 指的也是原始测试集。`kept`（套 ignore 列表后的）比例只作为参考一并输出。

## 3. 剔除规则

```
excluded  = { task | raw_pass_rate(task) < 0.9 }
remaining = 所有 200 个 task − excluded
```

阈值 0.9 直接来自 model card。不做人工例外、不按原因区分——原因分析只用于判断**我们的环境是否引入了
假阴性**（见第 5 节），环境问题修掉之后重跑，而不是手动改名单。

## 4. 剩余 task 上的计分（mask）

对每个 remaining task，记录 reference binary 通过的测试集合
`gold_passing[task] = { branch/test_name | status == passed }`（同样基于 raw 结果）。

给一个 submission 打分：

```
task_score      = |passed(submission) ∩ gold_passing[task]| / |gold_passing[task]|
benchmark_score = mean(task_score over remaining tasks)      # 未提交的 task 记 0
```

实现：`scripts/score_submission.py <run_dir>`。这一步就是 model card 里 "score only against tests the
reference binary passes"。

## 5. 我们剔除的 task 主要是什么原因（不是 time limit）

对 v1 数据里 22 个被剔除 task 的失败测试做分类（`docs/LOG.md` 里有逐 task 明细）：

| 原因 | 例子 | 性质 |
|---|---|---|
| 测试依赖镜像里没有的工具/文件/toolchain | ffmpeg（引用未展开的 `$(PROGSSUF)` 路径）、revive（要 go1.24）、doxygen（缺 xmllint）、pueue、proj | 测试生成时的环境假设与 cleanroom 镜像不符 |
| 大量 `skipped` | php（5334 条 "requires extension"）、skeema、run | skipped 按协议算不通过 |
| 固化的期望输出本身不成立/不确定 | duckdb、sqlite、gomplate、calcurse、lnav；dutree（目录大小随宿主文件系统 XFS/ext4 变化） | LLM 生成 golden 的固有 flakiness |
| 网络 | oranda（GitHub API 限流）、pingu（ICMP） | 部分可由我们环境修正（v2） |
| 上游测试集随时间漂移 | `run.sh` 里 `pip install --upgrade pytest` 装到 9.1 后 libtmux 插件收集失败（dust、dutree 等 9 个 branch） | 任何今天跑的人都会遇到 |
| 超时 | 只有 chamber 一个 task 以超时为主 | 次要原因 |

也就是说 model card 里的 "flakiness" 应理解为"hidden tests 是 LLM 生成的，有一部分在 reference 上就不成立"，
与 agent 推理阶段的 6 小时时限无关。

## 6. 已知的、无法消除的偏差

- **宿主文件系统**：磁盘占用类工具的 golden 编码了 XFS 的目录大小；我们是 ext4。Docker overlay2 同样继承
  宿主 FS，Anthropic 的机器是哪种无从得知。
- **时间**：pytest 9.1 漂移、GitHub 限流、hidden test 快照版本。
- **单次测量的随机性**：flaky 测试落在 0.9 哪一侧有随机性。

因此这份名单不可能与 Anthropic 的 34 个逐一对上；我们能保证的是**口径一致、过程可复现、环境假阴性
已尽量消除**。

## 7. 产物与复现

```
results/v2/gold_scores.json            每个 task 的 raw / kept 通过率、branch 错误、executable hash
results/v2/excluded_tasks.json         剔除名单（阈值 0.9）
results/v2/gold_passing_tests.json.gz  剩余 task 的计分 mask
```

复现（Slurm 上）：

```bash
scripts/make_gold_run.py /scratch/jundahe/pb-runs/gold          # 生成 gold submissions
sbatch --export=ALL,OUT=/scratch/jundahe/pb-runs/gold-eval-v2 scripts/gold_eval_loop.slurm   # 跑 eval
uv run python scripts/score_gold.py /scratch/jundahe/pb-runs/gold-eval-v2/gold results/v2       # 打分+剔除
```

最终结果（2026-09-04）：**20 个 task 被剔除，180 个保留**。11 个需要真实外网的 task 额外用宿主网络模式评了一遍，
每个 task 取两种模式中 raw 通过率较高的一次（`gold_scores.json` 的 `source` 字段记录来源）。

## 8. 稳健版（最终采用）

为回答"重跑一次会不会掉到 0.9 以下"，用同一配置独立跑了两次完整 gold（v2、v3，各含宿主网络补跑），规则改为：
**任一次 raw < 0.9 即剔除；mask 只保留两次都通过的测试**（`scripts/score_gold_robust.py`）。
结果与单次完全一致：**20 剔除 / 180 保留**；161/200 个 task 两次通过率到小数点后三位相同，
34 万条测试里只有 21 条两次结果不同（已从 mask 剔掉）。最终产物在 `results/v2v3-robust/`，
`score_submission.py` 默认使用它。
