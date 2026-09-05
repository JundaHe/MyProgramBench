# ProgramBench 任务集剔除报告（完整版）

本文完整记录我们如何从 ProgramBench 的 200 个 task 中剔除 20 个、保留 180 个，以及保留 task 上的计分
mask 是怎么来的。目标是复现 Claude 5 model card §8.11.1 的协议：

> We excluded 34 tasks for which the reference binary itself scored below 0.9 on the hidden test
> suite (indicating test flakiness), leaving 166 tasks. Among those tasks, we score only against
> tests the reference binary passes.

最终产物：`results/v2v3-robust/`（`excluded_tasks.json`、`gold_passing_tests.json.gz`、`gold_scores.json`）。

---

## 0. 一页总结

| 项目 | 值 |
|---|---|
| 原始 task 数 | 200（仓库 `src/programbench/data/tasks/` 有 201 个目录，`testorg__calculator` 是测试夹具，不算） |
| hidden tests 总数（评测器实际跑出的条目） | 344,302 |
| 剔除规则 | reference binary 的 **raw 通过率 < 0.9**（两次独立运行取最小值） |
| 剔除数 / 保留数 | **20 / 180** |
| 保留 task 上的计分 mask | 两次运行 reference **都通过**的测试：230,438 条 |
| 保留 task 的 reference 通过率 | 均值 0.978，中位数 0.989，最低 0.904 |
| 两次运行的一致性 | 161/200 个 task 通过率到小数点后三位相同；只有 21 条测试两次结果不同 |

---

## 1. 输入：task 与 hidden tests

- task 定义来自 upstream `facebookresearch/programbench` v1.2.4（commit `963063c`）。每个 task 是一个开源 CLI
  项目的某个 commit，配一个 Docker 镜像（`programbench/<repo>:task_cleanroom_v6`），镜像里 `/workspace/executable`
  是 **reference binary**（编译好的原程序），源码已删除。
- hidden tests 来自 HuggingFace `programbench/ProgramBench-Tests`（快照 `de0ddfb6`）。每个 task 有若干个
  test branch（tar 包），每个 branch 是一套 LLM 用 fuzz 方式生成的 pytest 测试 + `run.sh`。
- 我们**不使用** upstream `tests.json` 里的 `ignored_tests` / `ignored` branch 列表（原因见第 3 节）。

## 2. Gold run：让 reference binary 自己考一遍

"reference binary 的分数"不是数据里现成的字段，必须把它当作一份提交去跑评测器。

### 2.1 gold submission
每个 task 一份 `submission.tar.gz`，里面只有一个 `compile.sh`：
```sh
#!/bin/sh
set -e
cp /opt/programbench-reference/executable ./executable
chmod +x ./executable
```
评测器会先清空 `/workspace` 再解包提交，所以 reference binary 会被清掉；我们的容器 shim 在容器启动时
把 `/workspace/executable` 复制到 `/opt/programbench-reference/`，`compile.sh` 从那里取。被测二进制与
发布的 reference binary **逐字节一致**（`gold_scores.json` 里记录了 sha256）。

**唯一例外 tinycc**：tcc 运行时依赖 `make install` 装进 `/usr/local/lib/tcc` 的头文件和 `libtcc1.a`，
cleanroom 镜像里根本没有，光复制二进制连 `#include <stdio.h>` 都编不过（通过率 0.718，全是假阴性）。
这个 task 的 gold 改为从上游源码（同一 commit `9b8765d`）离线 `configure && make && make install`
构建（3 秒，无需网络）。`scripts/make_gold_run.py --source-overrides` 负责打包。

### 2.2 评测器与运行环境
- `programbench eval` v1.2.4，**未修改**。本机禁用 Docker，用 `scripts/pbdocker`（Apptainer 后端的
  docker-CLI 兼容 shim）替换，见 `01-environment.md`。
- 容器：独立网络命名空间（复现 Docker 的端口隔离）+ 经 unix socket 的 HTTP 代理出网；`/tmp`、`/var/tmp`
  为 1777 的宿主目录；容器内可用 ICMP（`ping_group_range`）；`$TERM` 不透传；`$HOME` 用镜像自己的。
- 11 个测试需要真实外网（DNS 客户端 dog、gping、oha、curlie、xh 等）的 task 额外用宿主网络模式评一遍，
  每个 task 取两种模式中 raw 通过率高的一次（`gold_scores.json` 的 `sources` 字段记录来源）。
- 每次运行都是**独立的单次测量**，做了两次：v2 和 v3（配置完全相同）。

### 2.3 我们修掉的环境假阴性（这些如果不修，剔除名单就是错的）
| 问题 | 症状 | 修法 |
|---|---|---|
| 宿主 `$TMUX` 泄漏进容器 | 所有 tmux/TUI 测试失败（cmatrix 90） | `apptainer exec --cleanenv` |
| `$HOME` 被空目录遮盖 | `git` dubious ownership，seed_git 失败 | `--no-home` |
| `$TERM` 透传 | ncurses 程序不在 TTY 时不退出，超时 | `env -u TERM` |
| `/tmp` 权限 0775 | apt 的 `_apt` 用户写不了，pandoc 0.048 | `chmod 1777` |
| 共享宿主网络 | 宿主上 sshd/netdata 占着 22/19999 端口，"connection refused"类测试误判；并行容器端口冲突 | 独立 netns + 代理 |
| 无 CAP_NET_RAW | pingu 的 ICMP 权限拒绝 | 独立 netns 内开 `ping_group_range` |
| tinycc 支持文件缺失 | 见 2.1 | 源码构建 gold |
| 沙箱镜像 owner 全被压成当前用户 | agent 用户写不了 `/workspace`（影响 agent 阶段） | `scripts/fix_ownership.py` 从镜像层恢复 uid |

## 3. 分数定义（raw，不套 upstream 的 ignore 列表）

每个 task：`raw_pass_rate = 状态为 passed 的测试条目数 / 全部测试条目数`，其中：

- "全部"= 评测器跑出来的每一条 `test_results`（所有 branch），包括 `failure`、`error`、
  `skipped`（如 "requires extension"）、`not_run`（整个 branch 收集失败时评测器补的记录）。
  这与 programbench 自己的 `EvaluationResult.score = n_resolved / len(test_results)` 一致。
- **不套 `tests.json` 的 ignore 列表**。理由：那些列表本身就是 upstream 用 gold 跑出来后剔掉的
  （`gold_fail` 31k、`dummy_pass` 36k 条……）。先剔再算，gold 通过率中位数变成 0.9999，只有 9 个 task
  低于 0.9；按原始测试算是 20 个，和 model card 的 34 个在同一量级。model card 的措辞
  "on the hidden test suite" 指的也是原始测试集。

## 4. 剔除规则

```
excluded  = { task | min(raw_pass_rate_v2, raw_pass_rate_v3) < 0.9 }
remaining = 200 − excluded
```
- 阈值 0.9 来自 model card。
- 取两次运行的 **min**：一个 task 只要有一次掉到 0.9 以下就剔除。实际结果两次名单完全一致。
- 不做人工例外、不按失败原因区分。原因分析（第 6 节）只用来判断"我们的环境是否引入了假阴性"，
  环境问题修掉后重跑，而不是手改名单。

## 5. 计分 mask 与提交打分

```
gold_passing[task] = { branch/test | 两次运行 reference 都 passed }        # 剔除 flaky 测试
task_score = #条目(passed 且 name ∈ gold_passing) / #条目(name ∈ gold_passing)
benchmark_score = mean(task_score over 180 tasks)                          # 未提交的 task 记 0
```
- 按**条目**计数而不是按测试名去重，是为了与 programbench 一致：评测器开着 `pytest-rerunfailures
  --reruns=2`，一个 flaky 测试的每次失败尝试都会被记一条。
- 实现：`scripts/score_submission.py <run_dir>`（默认用 `results/v2v3-robust/`）。对 gold 自身打分为 1.0。

## 6. 被剔除的 20 个 task 及原因

（raw = 通过率；条目 = 该 task 测试总条目；不通过 = 非 passed 条目；原因取 v2 运行前三类）

| task | raw v2 | raw v3 | 条目 | 不通过 | 主要原因 |
|---|---|---|---|---|---|
| axodotdev__oranda.27d60c7 | 0.754 | 0.754 | 1883 | 463 | 网络 421（GitHub API 限流/404）, 其他断言 28, skipped 11 |
| bootandy__dust.62bf1e1 | 0.882 | 0.880 | 1141 | 135 | 输出不匹配 61, branch收集失败(pytest9.1) 33, 缺工具/文件 22 |
| doxygen__doxygen.966d98e | 0.893 | 0.893 | 317 | 34 | 缺工具（xmllint）29, 输出不匹配 3 |
| duckdb__duckdb.bdb65ec | 0.775 | 0.775 | 12183 | 2747 | 输出不匹配 1418, skipped 1134, 缺依赖 124 |
| esubaalew__run.0fb9dec | 0.890 | 0.890 | 1511 | 166 | skipped 165（语言运行时不可用）, 输出不匹配 1 |
| ffmpeg__ffmpeg.360a402 | 0.709 | 0.709 | 7094 | 2066 | 缺工具/文件 1370（测试引用未展开的 `$(PROGSSUF)` 路径）, skipped 605, 输出不匹配 70 |
| hairyhenderson__gomplate.05eb3aa | 0.887 | 0.887 | 4521 | 513 | 输出不匹配 455, skipped 21 |
| halitechallenge__halite.822cfb6 | 0.879 | 0.879 | 521 | 63 | 其他断言 32, 缺工具/文件 27 |
| lfos__calcurse.49180d5 | 0.846 | 0.846 | 2864 | 441 | 输出不匹配 366, 其他断言 62, 超时 7 |
| mgechev__revive.201451e | 0.831 | 0.832 | 1362 | 230 | 缺 toolchain（需要 go1.24，镜像是 1.21）207 |
| nachoparker__dutree.44e877d | 0.774 | 0.774 | 1693 | 382 | 输出不匹配 336（目录大小随宿主文件系统 XFS/ext4 变化） |
| nikoladucak__caps-log.2cf2d1e | 0.799 | 0.800 | 1966 | 395 | 缺工具/文件 204, 其他断言 98, 输出不匹配 65 |
| nukesor__pueue.8b9d6fe | 0.764 | 0.764 | 2261 | 534 | 缺工具/文件 513 |
| osgeo__proj.75d455c | 0.784 | 0.784 | 8496 | 1834 | skipped 1166, 缺工具/文件 649 |
| php__php-src.c891263 | 0.722 | 0.722 | 22060 | 6136 | skipped 5334（"requires extension"）, 缺工具 562, 输出不匹配 195 |
| segmentio__chamber.5f93f5f | 0.852 | 0.852 | 4384 | 647 | 超时 601 |
| skeema__skeema.6a76243 | 0.850 | 0.850 | 3665 | 548 | skipped 444, 缺工具/文件 50 |
| sqlite__sqlite.839433d | 0.858 | 0.858 | 22377 | 3173 | 输出不匹配 2512, skipped 387, 其他断言 270 |
| tstack__lnav.ee34494 | 0.893 | 0.894 | 1374 | 147 | 输出不匹配 90, skipped 48 |
| zevv__duc.a58fa4e | 0.860 | 0.860 | 1666 | 234 | 缺工具/文件 170, 输出不匹配 36 |

原因归类（"flakiness"在这里的实际含义）：
1. **测试假设了镜像里没有的工具/文件/toolchain**（ffmpeg、revive、doxygen、pueue、proj、duc、caps-log）
   —— LLM 生成测试时的环境和 cleanroom 镜像不一致。
2. **大量 skipped**（php、proj、skeema、run）—— 按协议 skipped 不算通过。
3. **固化的期望输出本身不成立或依赖环境**（duckdb、sqlite、gomplate、calcurse、lnav；dutree 的目录大小）。
4. **网络**（oranda 的 GitHub API 限流）。
5. **上游测试集随时间漂移**：branch 的 `run.sh` 执行 `pip install --upgrade pytest`，今天装到 9.1 后
   libtmux 插件收集失败（dust 等 10 个 branch）。
6. **超时**只在 chamber 一个 task 是主因。

也就是说，被剔除的原因几乎都是**确定性的坏题**，不是随机性：两次运行这 20 个 task 的通过率完全一致。

## 7. 保留 task 中靠近阈值的（供参考，均两次一致）

cppcheck 0.904、zk 0.908、serpl 0.908、dog 0.909、kiro-editor 0.912、parallel-disk-usage 0.912、
wrapcheck 0.920、git-graph 0.920、clog-cli 0.929。它们的 gold 失败同样是确定性的（两次翻转 0 条），
不会因重跑而变动。

## 8. 与 model card 的 34/166 为什么不同

1. **无法逐个对上**：34 个的名单没有公开。
2. **评测机不同**：宿主文件系统（dutree/parallel-disk-usage 的 golden 编码的是 XFS 目录大小）、
   端口占用、能否联网、CPU 速度导致的超时——这些题在不同机器上结果本来就不同。
3. **时间不同**：pytest 9.1 漂移、GitHub 限流、hidden test 快照版本。
4. 他们是单次测量。

我们能保证的是：口径一致（raw、0.9）、过程可复现、环境假阴性已尽量消除、结果在本机可重复
（两次运行名单一致）。

## 9. 已知的、无法消除的偏差

- 宿主文件系统（ext4 vs XFS）影响磁盘占用类工具的 golden；无 root 无法模拟 XFS。
- 需要真实外网的测试依赖 GitHub 等外部服务状态。
- programbench 每个 branch 有 3600 秒硬超时：节点负载高时大 branch（sqlite 2240 秒、skeema）会整体
  `not_run`。因此**评测必须在空闲节点上低并行运行**（v3 第一次跑时因试点作业并行，sqlite 一度掉到
  0.016，在空闲节点重评后恢复 0.858）。

## 10. 复现

```bash
scripts/prep_all_images.slurm                      # 拉 200 个镜像成 apptainer sandbox
scripts/make_gold_run.py /scratch/jundahe/pb-runs/gold          # 生成 gold submissions（含 tinycc 源码构建）
sbatch --export=ALL,OUT=/scratch/jundahe/pb-runs/gold-eval-v2 scripts/gold_eval_loop.slurm   # 隔离网络模式
sbatch --export=ALL,FILTER=<11 个网络 task>,OUT=.../gold-eval-v2-hostnet,PBDOCKER_HOST_NETWORK=1 scripts/gold_eval.slurm
# 同样再跑一遍得到 v3、v3-hostnet
python3 scripts/score_gold_robust.py results/v2v3-robust \
    .../gold-eval-v2/gold,.../gold-eval-v2-hostnet/gold .../gold-eval-v3/gold,.../gold-eval-v3-hostnet/gold
```

产物字段（`results/v2v3-robust/gold_scores.json`，每个 task）：`raw_rates`（两次通过率）、`min_rate`、
`max_rate`、`flipped_tests`（两次结果不同的测试数）、`tests_in_all_runs`、`sources`（各次取自哪个
评测目录）。`excluded_tasks.json`：阈值、规则、名单。`gold_passing_tests.json.gz`：
`{task: [branch/test, ...]}` 的 mask。原始 eval 输出在 `/scratch/jundahe/pb-runs/gold-eval-v2*`、`v3*`。
