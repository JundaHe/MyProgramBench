# DeepSeek Harness (dsh) 在 ProgramBench 上的运行设置

目标：在我们定义好的 benchmark（`results/v2/`，180 个 task）上运行 DeepSeek Harness 的
**dynamic workflow** 功能（`workflow` 工具：模型自己写 JavaScript 编排脚本，fan-out 子 agent），
并完整保留每个 task 的实验参数、轨迹和 workflow 生成的 plan。

## 1. dsh 是什么、dynamic workflow 在哪

- 仓库 `deepseek-ai/deepseek-harness`（本地 `/scratch/jundahe/deepseek-harness`，2026-09-03 的 main）。
  TypeScript monorepo，"everything is a plugin"（Cordis）。有 Python SDK（`deepseek-harness-sdk`），
  wheel 自带 Node 运行时（261 MB），不依赖系统 Node。
- dynamic workflow = `packages/workflow/`：`tool-workflow`（模型面对的 `workflow` 工具）+
  `workflow-worker-thread`（在 worker 线程里执行脚本）+ subagent seam。脚本 API 与 Claude Code 的
  dynamic workflows 兼容：`agent()`、`parallel()`、`pipeline()`、`phase()`、`log()`、`args`。
- **没有配置能强制模型用它**：工具自带的指引是"仅当用户明确要求 workflow / 大规模多 agent 编排时使用"
  （`packages/workflow/tool-workflow/src/index.ts:214`）。所以我们在任务 prompt 里明确要求
  （`--workflow required`），并在事后从轨迹里核验用了几次（`tool-workflow/run-start` 记录）。

## 2. 我们的运行方式（为什么把 dsh 装进容器）

mini-swe-agent 的做法是 agent 进程在宿主机、命令通过 `docker exec` 进容器。dsh 的 bash 工具是本地
执行器，要改成远程执行得写一个新的 subprocess provider（TypeScript，代码量不小）。所以反过来：
**把 dsh 整个装进 task 容器里跑**：

```
容器（task 镜像，独立网络命名空间，用户 agent）
  /opt/dsh        ← /scratch/jundahe/dsh-runtime（pip --target 装的 SDK + Node 运行时，只读）
  /opt/pb         ← experiments/configs（profile 补丁）、experiments/scripts（driver）
  /dsh-home       ← <out>/<iid>/dsh-home（profile、session 日志、result.json，宿主可读）
  /run/pbagent/key← API key（episode 结束即删）
  /workspace      ← 任务工作区（reference binary 只在 ./executable，不另外暴露）
  网络：只能到 LLM API 域名（/etc/hosts 把它指到 127.0.0.1，pbproxy tcprelay 经 unix socket 透传
        TLS；代理白名单 PBPROXY_ALLOW=该域名，其他一律 403）
```

所有任务镜像都是 Ubuntu 22.04 / Python 3.10 / glibc 2.35，所以一份运行时目录通用。

## 3. 配置

- profile `sdk`（dsh-base + sdk-app）+ 补丁 `configs/dsh-programbench.patch.yml`：
  禁用 `web_search`/`web_fetch`、遥测；`sandbox-policy`/`approval`/`permission` 显式设为
  `danger-full-access`（容器就是沙箱；bwrap/Landlock 在 rootless apptainer 里不可用）；
  persona = mini-swe-agent `programbench.yaml` 的 ProgramBench 规则原文；session 日志不压缩。
- 任务 prompt（`scripts/dsh_agent.py`）= mini-swe-agent 的 instance_template 去掉其专有的命令格式说明，
  加上 `--workflow required` 时的"必须用 workflow 工具编排"段落。
- 模型：通过 OpenRouter（`--base-url https://openrouter.ai/api/v1`，`--model deepseek/...`），
  dsh 的 `deepseek-official` 适配器 + `DEEPSEEK_BASE_URL` 覆盖即可用；reasoning effort 用 dsh 默认 `high`，
  max_tokens 49152。
- 时间：每个 task **6 小时** wall-time（`request_timeout_seconds`），6.5 小时硬杀（防挂死）。没有 step 上限。
- 并行：用户 CPU 上限 16 核 → 最多 4 worker × 4 核。

## 4. 每个 task 的记录（`<out>/<iid>/`）

| 文件 | 内容 |
|---|---|
| `params.json` | 模型、endpoint、workflow 模式、时限、patch 哈希、dsh 运行时版本、我们代码的 commit、镜像、网络策略 |
| `prompt.txt` | 模型实际收到的任务 prompt |
| `agent.log` | driver 输出 |
| `dsh-home/result.json` | `exit_status`（`finished:<finish_reason>` / 异常名）、最终回复、`workflow_runs` 计数 |
| `dsh-home/notifications.jsonl` | 每条 JSON-RPC 通知（请求错误等，即使 session 日志尾部没落盘也在） |
| `dsh-home/sessions/**/session.jsonl` | 完整轨迹：主 session + 每个 workflow 子 agent 各一个 session |
| `workflows/NN-<name>.js` / `.json` | 每次 `workflow` 调用的脚本（plan）、meta、args、返回值；`records.json` 是 run/agent 生命周期记录 |
| `summary.json` | 事件数、assistant 轮数、各工具调用次数、workflow 次数 |
| `submission.tar.gz` | `/workspace` 快照，直接喂 `programbench eval` |

## 5. 冒烟测试（2026-09-04，cmatrix，`deepseek/deepseek-v4-flash`，45 分钟硬超时）

- 启动问题两处已修（权限预设匹配；复用 dsh-home 会续接旧 session）。
- 45 分钟内：129 轮模型调用、227 次工具调用（bash 195、read 12、editor 12、write 5、todo 2、**workflow 1**）。
  workflow `explore-cmatrix` 用 `parallel()` 起了 5 个子 agent 分头探索 flag/错误/依赖，子 agent 各有自己的
  session 日志。45 分钟到时还在实现阶段（工作区只有 `executable_impl`，未产出 compile.sh）——正式跑用 6 小时。

## 6. 运行

```bash
# 冒烟 / 试点
sbatch -c 4 --mem=16G --export=ALL,FILTER='abishekvashok__cmatrix',MODEL=deepseek/deepseek-v4-flash,\
BASE_URL=https://openrouter.ai/api/v1,OUT=/scratch/jundahe/pb-runs/dsh-smoke,HARD_TIMEOUT=2700 scripts/dsh_run.slurm
# 正式（180 个 task，4 worker，6 h/task）
sbatch -c 16 --mem=64G --export=ALL,MODEL=deepseek/deepseek-v4-pro,BASE_URL=https://openrouter.ai/api/v1,\
OUT=/scratch/jundahe/pb-runs/dsh-pro-required,WORKERS=4 scripts/dsh_run.slurm
# 对照组：WORKFLOW=allowed（不强制）
# 评测
sbatch --export=ALL,... scripts/gold_eval.slurm   # 或直接 programbench eval <out>
python3 scripts/score_submission.py <out>          # 用 results/v2 的 mask 打分
```
