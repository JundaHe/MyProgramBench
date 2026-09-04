#!/usr/bin/env python3
"""Runs INSIDE a task container (as user `agent`): one DeepSeek Harness (dsh) episode on the workspace.

    PYTHONPATH=/opt/dsh python3 /opt/pb/dsh_agent.py --dsh-home /dsh-home --key-file /run/pbagent/key \
        --model deepseek-v4-flash [--wall-time-seconds N] [--instance-id ID]

Writes <dsh-home>/result.json with the final response / exit status. The task prompt is mini-swe-agent's
ProgramBench instance_template (harness-specific "command execution rules" removed) so both harnesses
get the same task statement; the rules live in the profile persona (configs/dsh-programbench.patch.yml).
"""

import argparse
import json
import os
import platform
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, "/opt/dsh")
from deepseek_harness import DeepSeekHarness  # noqa: E402

TASK = """## Task context

We want to write the source code for a given executable.
The executable is located at `./executable` in the workspace root.

You also have access to the existing documentation.

## Your task

Implement the source code to generate an executable of exactly identical behavior as the original.

No project-specific dependencies are pre-installed.
You do NOT have access to the internet.
**IMPORTANT**: Make sure that the executable(s) and everything else that is an artifact is not committed, i.e., is in your `.gitignore` file.
Finally, commit your changes.

Make sure that you have a `./compile.sh` file that produces an executable `./executable` in the workspace root.
`compile.sh` should be executable and should install any dependencies needed to compile the executable.
If your compile.sh fails to compile on a fresh checkout, your task has failed.

## Important: This is a reverse-engineering benchmark

Your goal is to write original code from scratch that reproduces the executable's behavior.
The only way to learn what the executable does is to run it and read its bundled documentation.

Any attempt to obtain source code — whether successful or not — or to wrap/reuse the
provided binary will be detected by an automated judge, disqualified, and scored as zero.
See the full rules in the system prompt. Key points:

- Do NOT search the internet, clone repos, or download the project from any package registry
- Do NOT wrap, shim, or delegate to the provided `./executable` or any installed version of the same tool
- Do NOT decompile the provided `./executable` or use strace/ltrace on it (analyzing your own binaries is fine)
- You SHOULD extensively test the executable to understand its behavior before writing code.
  If you are dealing with a TUI, tmux/libtmux has been installed to help you test/inspect it.

## Recommended Workflow

1. Explore all documentation files
2. Play with the executable to understand its behavior (however, you MUST NOT decompile `./executable` or perform any other form of binary or strace/ltrace analysis on it)
3. Write the source code to implement the behavior

You have no step limit. Work until `./compile.sh` builds `./executable` from your own sources and its
behavior matches the original as closely as you can verify; then commit and finish with a short summary.
If you stop with known gaps, write them to `AGENT_REPORT.md` first.
{workflow_instruction}
<system_information>
{system} {release} {version} {machine}
</system_information>
"""


WORKFLOW_REQUIRED = """
## Orchestration requirement

You MUST use the `workflow` tool (dynamic workflows) to organize this work as a multi-agent script —
this is an explicit request. Write a workflow script that fans the work out across subagents, for
example: (1) parallel exploration agents that each probe one area of the executable's behavior
(help/usage, each subcommand or flag group, error handling, edge cases) and return structured
findings; (2) implementation agents for independent modules; (3) verification agents that compare
your build against the original on concrete inputs and report mismatches; iterate with further
workflow runs until the behavior matches. Do the bulk of the work through workflow runs; use direct
tool calls only for small glue steps and the final commit.
"""


def used_workflow(dsh_home: Path) -> int:
    n = 0
    for f in dsh_home.glob("sessions/**/*.jsonl"):
        n += sum(1 for line in f.read_text(errors="replace").splitlines() if '"tool-workflow/run-start"' in line)
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsh-home", type=Path, required=True)
    ap.add_argument("--key-file", type=Path, required=True)
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--provider", default="deepseek-official")
    ap.add_argument("--base-url", default="", help="OpenAI-compatible endpoint override (e.g. https://openrouter.ai/api/v1)")
    ap.add_argument("--max-tokens", type=int, default=49_152)
    ap.add_argument("--wall-time-seconds", type=int, default=0, help="0 = unlimited (model-card setting)")
    ap.add_argument("--instance-id", default="task")
    ap.add_argument("--patch", default="/opt/pb/dsh-programbench.patch.yml")
    ap.add_argument("--workflow", choices=["required", "allowed"], default="required",
                    help="required: the prompt explicitly demands the workflow tool (dsh only offers it on explicit request)")
    args = ap.parse_args()
    u = platform.uname()
    prompt = TASK.format(system=u.system, release=u.release, version=u.version, machine=u.machine,
                         workflow_instruction=WORKFLOW_REQUIRED if args.workflow == "required" else "")
    os.environ["DSH_PERMISSION_MODE"] = "danger-full-access"  # the container is the sandbox
    out = {"instance_id": args.instance_id, "model": args.model, "started": time.time()}
    try:
        with DeepSeekHarness(
            provider=args.provider,
            model=args.model,
            max_tokens=args.max_tokens,
            cwd="/workspace",
            dsh_home=str(args.dsh_home),
            profile="sdk",
            patches=(args.patch,),
            api_key=args.key_file.read_text().strip(),
            base_url=args.base_url or None,
            request_timeout_seconds=args.wall_time_seconds or None,
        ) as harness:
            result = harness.run(prompt, session_id=args.instance_id)
        out.update(exit_status="Submitted", final_response=result.final_response)
    except Exception as e:  # recorded, never swallowed: the runner reads exit_status
        out.update(exit_status=type(e).__name__, error=str(e), traceback=traceback.format_exc())
    out["finished"] = time.time()
    out["workflow_runs"] = used_workflow(args.dsh_home)  # from the session log's tool-workflow/run-start records
    (args.dsh_home / "result.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("instance_id", "exit_status", "workflow_runs")}))


if __name__ == "__main__":
    main()
