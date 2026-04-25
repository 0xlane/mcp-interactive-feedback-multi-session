---
name: interactive-feedback-loop
description: "Top-level agent ONLY (subagents MUST NOT use this). Collect user feedback via mcp-interactive-feedback after completing each task, then iterate based on feedback. Use proactively at the end of every task, code change, or multi-step workflow. Applies to all agent interactions—never skip unless the user explicitly says to stop."
---

# Interactive Feedback Loop

## Scope — CRITICAL

> **STOP. Before reading further, determine if you are a subagent.**
>
> You are a **subagent** if you were launched via the `Task` tool (any `subagent_type`), or if your system prompt says you are a subagent/subtask. If so: **DO NOT call `interactive_feedback`. DO NOT read the rest of this skill. Just finish your task and return your result.** Calling this tool from a subagent will cause the subagent to hang indefinitely and block the parent agent.

This skill applies **ONLY** to the **top-level agent** — the one that directly receives messages from the user in the chat window. All subagents (generalPurpose, explore, shell, best-of-n-runner, etc.) **MUST ignore this skill entirely**.

## Core Rule

**After completing any user task, always call the `interactive_feedback` MCP tool to collect feedback before ending your turn.** Repeat until the user explicitly signals completion.

## Workflow

1. Complete the user's requested task as normal.
2. Call the MCP tool with a concise summary of what you did:

```
MCP server: user-mcp-interactive-feedback
Tool: interactive_feedback
Arguments:
  project_directory: <current project root or ".">
  summary: <markdown-formatted summary of completed work>
  feedback_session_id: <if you received one from a previous call, pass it here>
```

3. Read the user's feedback response. **Extract the `feedback_session_id`** from the response (it appears as `[feedback_session_id=...]`). Save it for subsequent calls.
4. **If feedback contains new requests or corrections** → address them, then call the tool again with an updated summary **and the same `feedback_session_id`**. This reuses the existing UI session instead of creating a new one.
5. **If feedback is empty, or the user says things like "done", "no more", "looks good", "stop", "ok", "没问题", "可以了", "结束"** → end the loop. The task is complete.

## When Creating Subagents via the Task Tool

When you (the top-level agent) create a subagent using the `Task` tool, you **MUST** explicitly include the following instruction at the beginning or end of the `prompt` parameter:

> **You are a subagent created by a parent agent via the Task tool. Do NOT call the `interactive_feedback` MCP tool. Complete your task and return your result directly — do not attempt to collect user feedback.**

This is necessary because subagents inherit the parent agent's skills and rules (including this skill and the `interactive-feedback.mdc` rule), but they cannot automatically determine that they are subagents. Without this explicit instruction, a subagent may call `interactive_feedback`, causing the session to hang indefinitely and block the parent agent.

## Key Rules

- **Always call the tool** — even if you believe the task is trivially done. The user decides when to stop, not you.
- **Summarize clearly with Markdown** — the summary supports Markdown rendering. Use headings, lists, code blocks, bold, etc. to make the summary structured and easy to review.
- **Only summarize the current step** — do NOT re-summarize tasks the user already reviewed in previous feedback rounds. Only reference earlier work if it is directly related to the current task (e.g., a continuation).
- **Include project_directory** — pass the actual workspace root so the feedback UI has context.
- **No double-asking** — don't ask "is there anything else?" in text *and* call the tool. The tool replaces that question.
- **Respect stop signals** — when the user indicates they're satisfied, stop immediately. Don't call the tool again.
- **Call on blocked progress too** — if the user skips or rejects a command you proposed (e.g. a test run or shell command), do NOT silently continue or guess the reason. Immediately call the feedback tool to ask the user why they skipped and what they'd like you to do instead. The summary should mention which command was skipped and your current progress.

## Retry Policy

The `interactive_feedback` tool may return `MCP error -32001: Request timed out`. This is caused by Cursor's internal MCP client transport timeout (approximately 60-120 seconds), NOT by the MCP server. The server is still waiting for user input when this error occurs.

**When a timeout/error occurs:**

- **Retry immediately** with the exact same parameters. Do NOT give up.
- **Keep retrying indefinitely** until the tool returns a successful response.
- **Never fall back to text** — never substitute the tool call with a text message like "还有什么需要调整的吗？". The tool is the only acceptable feedback mechanism.
- **Never end your turn** without a successful feedback collection (unless the user already signaled completion in a prior successful feedback call).

The MCP server handles retries gracefully: when you pass `feedback_session_id`, the server reuses the same session. Even without it, the existing browser tab handles new sessions via WebSocket, so the user will not see multiple browser windows.
