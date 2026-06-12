# CW-Remote — AI 使用手册

> 运行环境：Python 3.11+，依赖通过 `uv sync` 管理（详见 GUIDE.md）。
> MCP 客户端配置：
> ```json
> {"servers":{"codeworker":{"command":"uv","args":["run","--directory","/workspace/cw-remote","python3","server.py"],"env":{"CODEWHALE_API_URL":"http://127.0.0.1:7878"}}}}
> ```

> 本文档写给调用此 MCP 服务器的 AI 阅读。帮助你在没有额外上下文的情况下理解
> 每个工具的用途,以及如何组合它们完成编程任务。

---

## 一、核心概念

此服务器管理的是 **CodeWhale AI 的编程会话**。有三个基本概念：

### 1. Thread（对话会话）

`thread` 不是操作系统的线程。它是一个 **AI 对话会话** —— 相当于一次完整的
开发任务：从你发出指令开始,到 AI 完成修改文件、执行命令、返回结果为止。

- 每次 `cw_run` 会创建一个新 thread
- 一个 thread 可以包含多次对话（多个 turn）
- thread 有唯一 ID（如 `thr_9d9d9934`）,所有后续操作都通过它引用
- thread 关联一个工作区目录（`workspace`）,AI 在该目录下操作文件和执行命令

### 2. Turn（回合）

`turn` 是 thread 中的 **一次消息交换**。你发一条消息 → AI 思考并执行 → AI 回复。

- 每个 turn 有唯一 ID（如 `turn_0908a75a`）
- 一次 `cw_run` 或 `cw_thread_turn` 产生一个新 turn
- AI 在回复前可以多次调用工具、执行命令,都在同一个 turn 内完成
- turn 的结束状态：`completed`（成功）,`failed`（失败）,`interrupted`（中断）

### 3. Item（条目）

`item` 是 turn 中的 **最小数据单元**。一个 turn 包含多个 item,按顺序排列：

| Item 类型 | 图标 | 内容 |
|-----------|------|------|
| `user_message` | 🧑 | 你发送的 prompt |
| `agent_reasoning` | 💭 | AI 的推理过程 |
| `agent_message` | 🤖 | AI 回复的文本 |
| `tool_call` | ⚙️ | AI 调用了某个工具 |
| `command_execution` | 📋 | AI 执行了 shell 命令（含完整输出） |
| `file_change` | 📝 | AI 修改了文件 |
| `error` | ❌ | 出错了 |

每个 item 在 turn 内有索引号：**`#0`, `#1`, `#2`……**
可以通过 `cw_item_get(thread_id, "#3")` 查看某一条的完整内容。

---

## 二、工作流程

### 流程 1：一次性任务（最推荐）

```
cw_run(prompt="帮我重构 src/main.rs 中的 handle_request 函数")
  → 立即返回:
     { thread_id: "thr_abc", turn_id: "turn_001", status: "started" }

cw_poll(thread_id="thr_abc", block=True, timeout_ms=120000)
  → 阻塞等待直到 AI 完成...
  → 返回:
     ── #turn_001 [✅ completed]

     重构完成,主要改动了 handle_request 的 error 处理逻辑。

  slim=True 时只返回 AI 最终回答（~300 tokens 即可）
```

使用 `cw_run` + `cw_poll(block=True)` 组合,一次对话只需要两次 MCP 调用。
如果你只关心最终结果,`cw_poll` 的 `slim` 返回结果已经够用。

### 流程 2：续接对话

同一 thread 中可以多次对话,AI 会记住前文。

```
cw_thread_turn(thread_id="thr_abc", prompt="再改一下 error 处理")
  → 立即返回,不等待

cw_poll(thread_id="thr_abc", block=True, timeout_ms=120000)
  → 等待新 turn 完成
  → 返回 AI 修改后的结果
```

### 流程 3：查看历史

```
cw_thread_get(thread_id="thr_abc", slim=True)
  → 精简摘要：只返回最近一次回答
  → 如果有多轮对话,显示所有 turn 的摘要索引
  → 节约 token

cw_thread_get(thread_id="thr_abc", slim=False)
  → 完整模式：展开所有 item
  → 包含推理过程、工具调用、命令输出等每个细节
  → token 消耗大,仅在需要时使用

cw_item_get(thread_id="thr_abc", index="#3")
  → 查看某一条 item 的完整 detail
  → 例如查看 #3 命令的完整输出,不看其他内容
  → 最节约 token 的查看方式
```

### 流程 4：需要审批的命令

如果 `cw_run` 设置了 `auto_approve=False`,AI 执行危险命令时会暂停并等待审批。

```
1. cw_run(prompt="删除 dist 目录", auto_approve=False)

2. cw_poll(thread_id="thr_abc", block=True)
   → 返回 in_progress, 卡在某条命令

3. 此时需要你判断是否安全：
   cw_approve(approval_id="ap_xxx", decision="allow")
   → 批准后 AI 继续执行

4. cw_poll(thread_id="thr_abc", block=True)
   → 拿到最终结果
```

默认 `auto_approve=True`,AI 自动执行所有命令,不需要你的干预。

---

## 三、返回格式说明

### slim 模式（默认）

```
── #turn_001 [✅ completed]
Hello, World!
```

只显示 turn 状态 + 最终 AI 回答。2~3 行,消耗极少 token。

### 非 slim（仅 slim=False 时）

```
── Turn #turn_001 [✅ completed]

  🧑 用 Python 写 hello world 并运行
  💭 用户要求用 Python 写 hello world...
  📋 $ exec_shell: Hello, World!
     Hello, World!
  🤖 Hello, World!
```

展开所有 item,显示推理过程和命令输出。

### 名称说明

- `thread_id` 格式：`thr_xxxxxxxx`
- `turn_id`  格式：`turn_xxxxxxxx`  
- `item_id`  格式：`item_xxxxxxxx`

引用方式：
- `#0`, `#1`... = 当前 turn 内的第 N 个 item（自动解析）
- `item_a1b2c3d4` = 全局唯一 item ID（可以直接用）

---

## 四、最佳实践

### 节约 token

1. **尽量用 `cw_poll(block=True)` 而非轮询**：服务器内部查询,减少无效交互
2. **使用 `cw_thread_get(slim=True)`**：只看结果不看过程
3. **用 `cw_item_get(index="#3")`** 代替完整查看：只看某一条
4. **`cw_thread_compact`**：对话太长时压缩旧内容
5. **`auto_approve=True`** 减少审批来回

### 错误处理

- 如果 `cw_poll` 返回 `failed`,用 `cw_thread_get(slim=False)` 查看错误详情
- 如果 `cw_poll` 超时,AI 仍在后台运行,再次 poll 即可继续等待
- 遇到 "approval_id" 相关提示时,调用 `cw_approve` 批准

### 多线程（多对话）

可以同时运行多个 thread,各自独立互不干扰。每个 thread 都有独立的工作区、
模型、上下文。适合同时处理多个不同的编程任务。

### `cw_health` 提示

调用 `cw_health` 会返回 CodeWhale 版本号。兼容范围 0.8.53 ~ 0.8.58（超出此范围服务器会拒绝启动），
`warning` 字段会有提示。此时部分工具可能异常。

### 性能数据

- 一次简单的对话（如 hello world）：~45K tokens,~$0.002
- 缓存命中率：65%~86%（调用方 AI 的 system prompt 一致时更高）
- `cw_poll` 默认超时 60 秒,建议复杂任务设 120~300 秒
