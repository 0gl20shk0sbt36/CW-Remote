"""CodeWhale MCP Server — 封装 Runtime API 为 MCP 工具。

连接 CodeWhale TUI 内置的 runtime_api（端口 7878）。
提供 AI 对话能力，输出经过格式化以减少上下文消耗。

环境变量:
    CODEWHALE_API_URL        Runtime API 地址（默认 http://127.0.0.1:7878）
    DEEPSEEK_RUNTIME_TOKEN   Bearer 认证令牌
"""

import json
import asyncio
import sys
import os
import shutil
from typing import Any

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from client import create_client, RuntimeApiClient

# 兼容的 CodeWhale 版本范围（当前锁定版本）
MIN_CW_VERSION = "0.8.53"
MAX_CW_VERSION = "0.8.54"
AUTO_START_DELAY = 5  # 自动启动后等待秒数


# ═══════════════════════════════════════════════════════════════════════
# Version check
# ═══════════════════════════════════════════════════════════════════════

def _parse_version(v: str) -> tuple:
    """解析版本号 '0.8.53' → (0, 8, 53) 用于比较。"""
    try:
        parts = v.split("-")[0].split(".")
        return tuple(int(p) for p in parts[:3])
    except (ValueError, IndexError):
        return (0, 0, 0)


def _check_version(actual: str) -> str:
    """检查版本兼容性，返回警告文本（无警告返回空字符串）。"""
    min_v = _parse_version(MIN_CW_VERSION)
    max_v = _parse_version(MAX_CW_VERSION)
    cur_v = _parse_version(actual)
    if cur_v < min_v:
        return (f"⚠️ CodeWhale v{actual} 过低（需要 >= {MIN_CW_VERSION}）。"
                f"接口可能发生变化，部分工具可能异常。")
    if cur_v >= max_v:
        return (f"⚠️ CodeWhale v{actual} 过高（本 MCP 服务器最高兼容 < {MAX_CW_VERSION}）。"
                f"版本不匹配可能导致工具异常。请更新 cw-mcp-server。")
    return ""


async def _ensure_runtime(cw: RuntimeApiClient) -> str:
    """启动时连接 runtime_api，必要时自动启动。返回状态文本。"""
    # 先尝试连接
    for attempt in range(3):
        try:
            info = await cw.runtime_info()
            version = info.get("version", "0.0.0")
            warn = _check_version(version)
            return f"CodeWhale Runtime API v{version} ({info.get('bind_host','?')}:{info.get('port','?')})  {warn}".strip()
        except Exception:
            if attempt < 2:
                await asyncio.sleep(0.5)
                continue
            break
    else:
        pass  # 所有尝试都失败

    # 连接失败：尝试自动启动
    cw_paths = [
        shutil.which("codewhale-tui"),
        shutil.which("codewhale"),
        os.path.expanduser("~/.local/bin/codewhale-tui"),
        "/usr/local/bin/codewhale-tui",
    ]
    cw_bin = next((p for p in cw_paths if p), None)
    port = cw.base_url.rsplit(":", 1)[-1] if ":" in cw.base_url else "7878"

    if cw_bin:
        import subprocess
        try:
            subprocess.Popen(
                [cw_bin, "serve", "--http", "--insecure", "--port", port],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

        for i in range(AUTO_START_DELAY * 2):
            await asyncio.sleep(0.5)
            try:
                info = await cw.runtime_info()
                version = info.get("version", "0.0.0")
                warn = _check_version(version)
                return f"✅ 自动启动了 CodeWhale Runtime API v{version}（{info.get('bind_host','?')}:{info.get('port','?')}）  {warn}".strip()
            except Exception:
                continue

    return ("❌ 无法连接 CodeWhale Runtime API。请手动启动：\n"
            f"   codewhale-tui serve --http --port {port}\n"
            f"   或设置 CODEWHALE_API_URL 指向已运行的实例")


# ═══════════════════════════════════════════════════════════════════════
# Formatting
# ═══════════════════════════════════════════════════════════════════════

def _fmt_turn_items(turns: list, items: list, slim: bool = True) -> str:
    """格式化线程内容。slim=True 只返回最后一个 turn 的最终回答+索引。"""
    if not turns:
        return "(无回合记录)"

    lines = []
    for turn in turns:
        status = turn.get("status", "?")
        icon = {"completed": "✅", "failed": "❌", "in_progress": "⚡", "interrupted": "⏸️"}.get(status, "❓")
        turn_id = turn.get("id", "?")
        usage = turn.get("usage", {})
        usage_str = ""
        if usage:
            total = usage.get("total_tokens", 0)
            cached = usage.get("cache_hit_tokens", 0)
            if total:
                usage_str = f"  tokens={total}  cache={cached}  cost=${usage.get('cost_usd', 0):.4f}"

        if slim:
            lines.append(f"── #{turn_id} [{icon} {status}]{usage_str}")
        else:
            lines.append(f"\n── Turn #{turn_id} [{icon} {status}]{usage_str}")

        turn_items = [i for i in items if i.get("turn_id") == turn_id]
        if slim and status == "completed" and len(turns) < 2:
            # 单一已完成 turn: 最后 agent_message + 索引
            last_agent = ""
            for it in reversed(turn_items):
                if it.get("kind") == "agent_message" and it.get("detail"):
                    last_agent = it["detail"]
                    break
            if last_agent:
                lines.append(f"\n{last_agent}")
            continue

        if not slim:
            for it in turn_items:
                kind = it.get("kind", "?")
                s = it.get("summary", "")
                d = it.get("detail")
                if kind == "user_message":
                    lines.append(f"\n  🧑 {s}")
                elif kind == "agent_message":
                    lines.append(f"\n  🤖 {(d or s)}")
                elif kind == "tool_call":
                    lines.append(f"  ⚙️  {s}")
                elif kind == "command_execution":
                    lines.append(f"  📋 $ {s}")
                    if d:
                        for dl in d.split("\n")[:15]:
                            lines.append(f"     {dl}")
                elif kind == "error":
                    lines.append(f"  ❌ {(d or s)}")
                elif kind == "agent_reasoning":
                    lines.append(f"  💭 {(d or s)[:120]}")
                else:
                    lines.append(f"  [{kind}] {(d or s)[:80]}")
            continue

        # slim + 多 turn / 未完成: 索引表
        kind_icons = {
            "user_message": "🧑", "agent_message": "🤖", "agent_reasoning": "💭",
            "tool_call": "⚙️", "command_execution": "📋", "file_change": "📝",
            "error": "❌", "status": "ℹ️",
        }
        for idx, it in enumerate(turn_items):
            ico = kind_icons.get(it.get("kind", ""), "❓")
            summary = (it.get("detail") or it.get("summary", ""))[:100]
            lines.append(f"  #{idx} {ico} {summary}")

    return "\n".join(lines)


def _format_item(item: dict) -> str:
    kind = item.get("kind", "?")
    summary = item.get("summary", "")
    detail = item.get("detail")
    metadata = item.get("metadata")

    kind_labels = {
        "user_message": "🧑 User", "agent_message": "🤖 AI",
        "agent_reasoning": "💭 Reasoning", "tool_call": "⚙️ Tool",
        "command_execution": "📋 Command", "file_change": "📝 FileChange",
        "error": "❌ Error", "status": "ℹ️ Status",
    }

    lines = [f"Item: {item.get('id','?')}  |  {kind_labels.get(kind, kind)}  |  {item.get('status','?')}"]

    if summary:
        lines.append(f"Summary: {summary}")
    if detail:
        lines.append(f"\n── Detail ──\n{detail}")
    if metadata:
        lines.append(f"\n── Metadata ──\n{json.dumps(metadata, ensure_ascii=False, indent=2)}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# MCP Tools
# ═══════════════════════════════════════════════════════════════════════

TOOLS = [
    # ★ AI 对话（核心）
    Tool(name="cw_run",
        description="【启动 AI 任务】发送 prompt 给另一个 CodeWhale AI，立即返回不等待。"
                    "返回 thread_id（对话会话 ID）和 turn_id（本次轮次 ID）。"
                    "之后用 cw_poll 跟踪进度。"
                    ""
                    "CodeWhale 中 '线程(thread)' 是一个 AI 对话会话。"
                    "一次对话 = 一个 thread。每次发消息 = 启动一个新 turn（回合）。"
                    "每个 turn 中包含多个 item（用户消息、AI 回复、工具调用、命令执行等）。"
                    ""
                    "默认 auto_approve=True，AI 会自动执行 shell 命令而无需审批。",
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "发送给 AI 的指令文本。例如 '帮我重构 src/main.rs 中的函数'"},
                "model": {"type": "string", "description": "模型名，如 deepseek-v4-pro, deepseek-v4-flash"},
                "mode": {"type": "string", "description": "agent=完整工具权限, plan=只规划不执行, yolo=完全自主", "default": "agent"},
                "workspace": {"type": "string", "description": "AI 的工作目录路径（文件操作和命令执行的根目录）"},
                "allow_shell": {"type": "boolean", "description": "是否允许 AI 执行 shell 命令", "default": True},
                "auto_approve": {"type": "boolean", "description": "是否自动批准 AI 执行命令（设为 false 后需用 cw_approve 手动批准）", "default": True},
                "system_prompt": {"type": "string", "description": "自定义系统级别指令，叠加在默认 system prompt 之上"},
                "title": {"type": "string", "description": "线程标题，方便在列表中识别"},
            },
            "required": ["prompt"],
        },
    ),
    Tool(name="cw_poll",
        description="【查询 AI 任务进度】查询某个 thread（对话会话）中最新 turn（轮次）的状态。"
                    "block=True 时服务器内部循环查询直到完成或超时再返回（推荐）。"
                    "block=False 立即返回当前快照。"
                    ""
                    "返回内容包含：当前状态（completed/failed/in_progress）、"
                    "已产生的 item 摘要列表（每条有 #N 编号，可用 cw_item_get 获取完整内容）。"
                    "如果 AI 在执行 shell 命令，poll 会展示命令内容和输出进度。",
        inputSchema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "线程 ID（来自 cw_run 的返回值）"},
                "block": {"type": "boolean", "description": "true=阻塞等待直到完成, false=立即返回当前状态", "default": True},
                "timeout_ms": {"type": "integer", "description": "最大等待毫秒数（block=True 时有效，超时返回当前进度）", "default": 60000},
            },
            "required": ["thread_id"],
        },
    ),
    Tool(name="cw_approve",
        description="【批准/拒绝 AI 执行命令】只有 auto_approve=False 时需要用此工具。"
                    "当 AI 想执行 shell 命令但需要审批时，会收到 approval_id。"
                    "调用 cw_approve(approval_id=xxx, decision='allow') 即可放行。"
                    "批准后 AI 会继续执行，之后用 cw_poll 查看结果。",
        inputSchema={
            "type": "object",
            "properties": {
                "approval_id": {"type": "string", "description": "审批请求 ID（来自 AI 的审批请求）"},
                "decision": {"type": "string", "description": "'allow'=批准执行 / 'deny'=拒绝", "default": "allow"},
                "remember": {"type": "boolean", "description": "记住此决定，后续同类操作自动放行", "default": False},
            },
            "required": ["approval_id"],
        },
    ),
    Tool(name="cw_item_get",
        description="【查看单条详细内容】获取 thread（对话会话）中某条 item 的完整内容。"
                    "item 是 turn（回合）中的最小数据单元，例如：一条用户消息、AI 一段回复、一次工具调用、一条命令输出。"
                    "在 cw_run/cw_poll/cw_thread_get 的返回中，item 显示为 #0, #1, #2... 的索引。"
                    "传入索引 '#3' 或完整 item_id 即可获取完整 detail。"
                    "适用于：查看 AI 完整回复文本、查看命令的完整输出、查看工具调用的全量参数。",
        inputSchema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "线程 ID"},
                "index": {"type": "string", "description": "item 索引 '#0','#1'... 或完整 item_id（如 'item_a1b2c3d4'）"},
            },
            "required": ["thread_id", "index"],
        },
    ),
    Tool(name="cw_thread_get",
        description="【查看对话历史】获取指定 thread（AI 对话会话）的完整对话记录。"
                    "slim=True（默认）：精简模式，只返回最近一个 turn 的 AI 最终回答，适合快速了解结果。"
                    "slim=False：完整模式，展开所有 turns 和 items，包括用户消息、AI 推理过程、工具调用、命令输出等每个细节。"
                    "如果线程有多个对话轮次，精简模式会显示所有 turn 的摘要索引。",
        inputSchema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "线程 ID"},
                "slim": {"type": "boolean", "description": "true=精简摘要（节约 token）, false=完整全部内容", "default": True},
            },
            "required": ["thread_id"],
        },
    ),
    # ── 线程管理（对话会话管理）──
    Tool(name="cw_thread_create",
        description="【创建空对话会话】创建一个新的 AI 对话线程，返回 thread_id。"
                    "创建后需用 cw_thread_turn 或 cw_run 发消息。",
        inputSchema={
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "模型名"},
                "mode": {"type": "string", "description": "agent / plan / yolo", "default": "agent"},
                "system_prompt": {"type": "string", "description": "系统 prompt"},
                "workspace": {"type": "string", "description": "工作目录"},
            },
        },
    ),
    Tool(name="cw_thread_list",
        description="【列出所有对话会话】返回所有 thread 列表，包含每个会话的 ID、模型、模式、工作区、归档状态等信息。",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "最多返回多少条"},
                "include_archived": {"type": "boolean", "description": "是否包含已归档的会话"},
            },
        },
    ),
    Tool(name="cw_thread_update",
        description="【修改对话属性】更新 thread 的各种属性：修改标题方便识别、归档/取消归档、切换模型、切换 agent/plan/yolo 模式等。",
        inputSchema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "线程 ID"},
                "title": {"type": "string", "description": "新标题"},
                "archived": {"type": "boolean", "description": "true=归档隐藏, false=取消归档"},
                "model": {"type": "string", "description": "切换模型"},
                "mode": {"type": "string", "description": "切换模式：agent/plan/yolo"},
                "allow_shell": {"type": "boolean", "description": "是否允许执行 shell"},
            },
            "required": ["thread_id"],
        },
    ),
    Tool(name="cw_thread_compact",
        description="【压缩对话历史】当 thread 的上下文太长（token 消耗大）时，压缩旧的对话内容为摘要。"
                    "压缩后旧消息的细节会丢失，但线程能继续对话且 token 消耗大幅降低。",
        inputSchema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "线程 ID"},
                "reason": {"type": "string", "description": "压缩原因说明"},
            },
            "required": ["thread_id"],
        },
    ),
    Tool(name="cw_thread_turn",
        description="【在已有对话中发消息】向一个已有 thread 发消息启动新回合。"
                    "AI 会带着前文历史回复。此工具立即返回（不等待 AI 完成），"
                    "需调用 cw_poll 等待完成或用 cw_thread_get 查看结果。",
        inputSchema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "线程 ID"},
                "prompt": {"type": "string", "description": "发送给 AI 的消息"},
                "model": {"type": "string", "description": "模型名"},
            },
            "required": ["thread_id", "prompt"],
        },
    ),
    Tool(name="cw_thread_resume",
        description="【恢复对话】恢复一个已结束/中断的 thread，使其重新处于可对话状态。",
        inputSchema={
            "type": "object", "properties": {
                "thread_id": {"type": "string", "description": "线程 ID"},
                "model": {"type": "string", "description": "模型名"},
            }, "required": ["thread_id"],
        },
    ),
    Tool(name="cw_thread_fork",
        description="【分叉对话】基于已有 thread 创建一个副本（分支）。用于尝试不同方向的探索而不影响原对话。",
        inputSchema={
            "type": "object", "properties": {
                "thread_id": {"type": "string", "description": "要分叉的线程 ID"},
            }, "required": ["thread_id"],
        },
    ),
    # ── 系统 ──
    Tool(name="cw_health",
        description="【健康检查】检查 CodeWhale Runtime API 是否在线。返回服务状态、版本号、版本兼容性。",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(name="cw_workspace_status",
        description="【工作区状态】查看 CodeWhale 工作目录的 git 状态：当前分支、是否有未提交的更改、未推送的提交等。",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(name="cw_usage",
        description="【用量统计】查看 token 消耗量和费用统计。可按模型、按天、按 provider 分组。",
        inputSchema={"type": "object", "properties": {
            "group_by": {"type": "string", "description": "分组方式：day/model/provider/thread", "default": "day"},
        }},
    ),
]

# ═══════════════════════════════════════════════════════════════════════
# Dispatch
# ═══════════════════════════════════════════════════════════════════════

async def handle_tool(name: str, args: dict, client: RuntimeApiClient) -> list[TextContent]:
    try:
        result = await _dispatch(name, args, client)
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
        return [TextContent(type="text", text=text)]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


async def _dispatch(name: str, args: dict, client: RuntimeApiClient) -> Any:
    match name:
        # ── AI 对话 ──
        case "cw_run":
            prompt = args["prompt"]
            # 创建线程
            thread = await client.create_thread(
                model=args.get("model"),
                mode=args.get("mode", "agent"),
                workspace=args.get("workspace"),
                system_prompt=args.get("system_prompt"),
                allow_shell=args.get("allow_shell", True),
            )
            tid = thread.get("id")
            if not tid:
                return {"error": "Failed to create thread", "response": str(thread)[:500]}

            # 设置 auto_approve
            await client.update_thread(tid, auto_approve=args.get("auto_approve", True))

            # 设置标题
            if args.get("title"):
                await client.update_thread(tid, title=args["title"])

            # 启动 turn
            turn = await client.start_turn(
                thread_id=tid, prompt=prompt, model=args.get("model")
            )
            turn_id = turn.get("turn", {}).get("id", turn.get("id", "?"))

            return json.dumps({
                "status": "started",
                "thread_id": tid,
                "turn_id": turn_id,
                "hint": f"使用 cw_poll(thread_id=\"{tid}\", block=True) 等待完成",
            }, ensure_ascii=False)

        case "cw_poll":
            tid = args["thread_id"]
            block = args.get("block", True)
            timeout_ms = args.get("timeout_ms", 60000)
            max_wait = timeout_ms / 1000.0 if block else 0.0

            interval, waited = 1.5, 0.0
            last_seq = -1
            stable_rounds = 0

            while waited <= max_wait:
                detail = await client.get_thread(thread_id=tid)
                turns = detail.get("turns", [])
                items = detail.get("items", [])

                if not turns:
                    return "Thread exists but has no turns yet."

                last = turns[-1]
                status = last.get("status", "?")
                current_seq = len(items)

                # 构建输出
                result_lines = [
                    f"Thread: {tid}  Turn: {last.get('id','?')}  [{'✅' if status == 'completed' else '❌' if status in ('failed','interrupted') else '⚡'}]",
                    f"Status: {status}",
                ]

                if status == "completed":
                    result_lines.append("")
                    result_lines.append(_fmt_turn_items(turns, items, slim=True))
                    return "\n".join(result_lines)

                elif status in ("failed", "interrupted"):
                    result_lines.append("")
                    err_items = [it for it in items if it.get("kind") == "error"]
                    for it in err_items:
                        result_lines.append(f"Error: {(it.get('detail') or it.get('summary',''))[:300]}")
                    return "\n".join(result_lines)

                # in_progress: 显示已有进度
                turn_items = [it for it in items if it.get("turn_id") == last.get("id")]
                result_lines.append(f"Items so far: {len(turn_items)}")
                for idx, it in enumerate(turn_items):
                    s = (it.get("detail") or it.get("summary", ""))[:100]
                    result_lines.append(f"  #{idx} [{it.get('kind')}] {s}")

                # 是否有未完成的 command_execution 或 tool_call
                pending = [it for it in turn_items if it.get("status") == "in_progress"]
                if pending:
                    result_lines.append(f"\nPending: {pending[-1].get('kind')} = {pending[-1].get('summary','')[:80]}")

                # 检查是否卡住（item 无变化多次）
                if current_seq == last_seq:
                    stable_rounds += 1
                else:
                    stable_rounds = 0
                    last_seq = current_seq

                # 如果连续5轮（~10秒）无进展，怀疑卡在审批
                if stable_rounds >= 5 and pending:
                    result_lines.append("\n⚠️ AI 可能正在等待审批。如需审批请提供 approval_id。")
                    result_lines.append("如果当前不需要审批，请稍后重试。")

                if not block:
                    return "\n".join(result_lines)

                await asyncio.sleep(interval)
                interval = min(interval * 1.5, 8.0)
                waited += interval

            # 超时
            detail = await client.get_thread(thread_id=tid)
            lines = [f"⏰ 轮询超时（{timeout_ms}ms）"]
            lines.append(_fmt_turn_items(detail.get("turns", []), detail.get("items", []), slim=True))
            lines.append(f"\n用 cw_poll(thread_id=\"{tid}\", block=True) 继续等待")
            return "\n".join(lines)

        case "cw_approve":
            return await client.decide_approval(
                approval_id=args["approval_id"],
                decision=args.get("decision", "allow"),
                remember=args.get("remember", False),
            )

        case "cw_item_get":
            tid, index = args["thread_id"], args["index"]
            detail = await client.get_thread(thread_id=tid)
            items = detail.get("items", [])

            if index.startswith("#"):
                last_turn_id = detail.get("turns", [{}])[-1].get("id") if detail.get("turns") else None
                turn_items = [i for i in items if i.get("turn_id") == last_turn_id]
                try:
                    pos = int(index[1:])
                    if 0 <= pos < len(turn_items):
                        return _format_item(turn_items[pos])
                except (ValueError, IndexError):
                    pass
                return {"error": f"Invalid index '{index}', valid 0..{len(turn_items)-1}"}

            for it in items:
                if it.get("id") == index:
                    return _format_item(it)
            return {"error": f"Item not found: {index}"}

        case "cw_thread_get":
            raw = await client.get_thread(thread_id=args["thread_id"])
            return _fmt_turn_items(raw.get("turns", []), raw.get("items", []), slim=args.get("slim", True))

        # ── 线程管理 ──
        case "cw_thread_create":
            return await client.create_thread(
                model=args.get("model"), mode=args.get("mode", "agent"),
                system_prompt=args.get("system_prompt"), workspace=args.get("workspace"),
            )

        case "cw_thread_list":
            return await client.list_threads(limit=args.get("limit"), include_archived=args.get("include_archived"))

        case "cw_thread_update":
            kwargs = {k: args[k] for k in ("title", "archived", "allow_shell", "model", "mode") if k in args and args[k] is not None}
            return await client.update_thread(thread_id=args["thread_id"], **kwargs)

        case "cw_thread_compact":
            return await client.compact_thread(thread_id=args["thread_id"], reason=args.get("reason"))

        case "cw_thread_turn":
            return await client.start_turn(thread_id=args["thread_id"], prompt=args["prompt"], model=args.get("model"))

        case "cw_thread_resume":
            return await client.resume_thread(thread_id=args["thread_id"], model=args.get("model"))

        case "cw_thread_fork":
            return await client.fork_thread(thread_id=args["thread_id"])

        # ── 系统 ──
        case "cw_health":
            h = await client.health()
            try:
                info = await client.runtime_info()
                version = info.get("version", "?")
                warn = _check_version(version)
                h["version"] = version
                if warn:
                    h["warning"] = warn
            except Exception:
                h["version"] = "unknown"
            return h

        case "cw_workspace_status":
            return await client.workspace_status()

        case "cw_usage":
            return await client.usage(group_by=args.get("group_by", "day"))

        case _:
            return {"error": f"Unknown tool: {name}"}


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

async def main():
    cw = create_client()
    status = await _ensure_runtime(cw)
    print(f"[cw-mcp-server] {status}", file=sys.stderr)
    server = Server("codewhale-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        return await handle_tool(name, arguments, cw)

    init_options = server.create_initialization_options()
    async with stdio_server() as (read, write):
        await server.run(read, write, init_options)


if __name__ == "__main__":
    asyncio.run(main())
