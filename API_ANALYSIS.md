# CodeWhale 启动参数完整分析

> 基于源码: `crates/tui/src/main.rs` (v0.8.53)

---

## 一、通用参数（所有子命令共享）

`codewhale-tui` 的顶层 `Cli` 结构提供以下参数，适用于 `serve` 以及所有其他子命令：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-p, --prompt <PROMPT>` | 初始 prompt（交互式 TUI 用） | — |
| `-c, --config <PATH>` | 配置文件路径 | `~/.codewhale/config.toml` |
| `--profile <NAME>` | 配置 profile 名称 | — |
| `-w, --workspace <PATH>` | 工作区目录 | 当前目录 |
| `-r, --resume <ID>` | 恢复指定 session | — |
| `--continue` | 恢复最近 session | — |
| `-v, --verbose` | 详细日志 | — |
| `--yolo` | YOLO 模式（自动批准+允许 shell） | — |
| `--max-subagents <NUM>` | 最大并发子 agent 数（1-20） | — |
| `--mouse-capture` / `--no-mouse-capture` | TUI 鼠标捕获 | — |
| `--enable <FEATURE>` / `--disable <FEATURE>` | 动态特性开关 | — |

> **注意**：`serve --http` 模式下这些参数中 `--workspace` 和 `--config` 有意义，`--yolo`/`--prompt` 等 TUI 参数无实际作用。

---

## 二、`serve` 子命令专用参数

来源：`struct ServeArgs`（行 657-695）

### 启动模式（互斥，必选其一）

| 参数 | 功能 |
|------|------|
| `--mcp` | 启动 MCP stdio 服务器（给其他 CodeWhale/Claude 提供工具） |
| `--http` | **启动 Runtime HTTP/SSE API（端口 7878），即本 MCP 服务器的后端** |
| `--mobile` | 同上 + 内置移动端控制页面 + 绑定 0.0.0.0 |
| `--acp` | 启动 ACP 编辑器代理（Zed 等） |

### 网络

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--host <HOST>` | 绑定地址 | `127.0.0.1`（`--mobile` 时 `0.0.0.0`） |
| `--port <PORT>` | 绑定端口 | **7878** |
| `--cors-origin <URL>` | 额外 CORS 允许源（可重复） | 默认允许 localhost:3000/1420 + tauri://localhost |

### 运行时

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--workers <1-8>` | 后台任务 worker 数 | 2 |
| `--auth-token <TOKEN>` | API 认证 Token | 未指定时读 `DEEPSEEK_RUNTIME_TOKEN` 环境变量，都没有则自动生成 |
| `--insecure` | **关闭认证**（仅 loopback 安全） | — |

### 移动端

| 参数 | 说明 |
|------|------|
| `--qr` | 终端打印 QR 码（需配合 `--mobile`） |

---

## 三、实际调用链

```
用户输入
  ↓
codewhale serve --http --port 7878 --insecure
  ↓  CLI 调度器 → 转发给 TUI 二进制
codewhale-tui serve --http --port 7878 --insecure
  ↓  加载 config.toml + 解析 CORS origins
  ↓  构建 RuntimeApiOptions { host, port, workers, cors_origins, auth_token, ... }
  ↓
runtime_api::run_http_server(config, workspace, options)
  ↓
启动 axum HTTP 服务器 → 监听 7878
  ├── /health
  ├── /v1/stream          (SSE AI 对话)
  ├── /v1/threads/**       (线程管理)
  ├── /v1/tasks/**         (任务)
  ├── /v1/approvals/**     (审批)
  ├── /v1/usage            (用量)
  └── ...
```

---

## 四、MCP 服务器适配建议

当前 `cw-mcp-server` 的自动启动命令：

```python
subprocess.Popen(
    [cw_bin, "serve", "--http", "--insecure", "--port", port],
    ...
)
```

可扩展为支持额外参数的环境变量：

| 环境变量 | 对应参数 | 建议默认值 |
|----------|---------|-----------|
| `CODEWHALE_API_URL` | — | `http://127.0.0.1:7878` |
| `DEEPSEEK_RUNTIME_TOKEN` | 注入到 `--auth-token` | — |
| `CWHALE_WORKSPACE` | `--workspace` | 当前目录 |
| `CWHALE_WORKERS` | `--workers` | 2 |
| `CWHALE_HOST` | `--host` | 127.0.0.1 |
| `CWHALE_PORT` | `--port` | 7878 |

> 当前 MCP 服务器的自动启动只设了 `--http --insecure --port`，其他参数取默认值。
> 如果需要指定 workspace 或 workers，可通过环境变量扩展。
