# CodeWhale 完整配置参考

> 基于源码: `crates/tui/src/main.rs` + `crates/config/src/lib.rs` (v0.8.53)
> 本文档列出 CodeWhale 所有可配置项及其配置方式。

---

## 配置方式优先级

CodeWhale 配置有三条路径，优先级从高到低：

```
1. 命令行参数              (最高优先级)
2. 环境变量                (中等优先级)
3. ~/.codewhale/config.toml (最低优先级，持久化)
```

同一配置项可以通过多条路径设置。例如 API key：

```bash
# 方式1: 环境变量（立即生效）
export DEEPSEEK_API_KEY="sk-xxx"

# 方式2: config.toml（持久化）
api_key = "sk-xxx"

# 方式3: CLI 命令（写入 config.toml）
codewhale auth set --provider deepseek
```

---

## 一、CLI 参数

### 1.1 `codewhale-tui` 通用参数

| 参数 | 环境变量 | config.toml | 说明 |
|------|---------|------------|------|
| `-p, --prompt <TEXT>` | — | — | 初始 prompt（交互模式） |
| `-w, --workspace <DIR>` | — | — | 工作区目录，默认当前目录 |
| `-c, --config <PATH>` | `CODEWHALE_CONFIG_PATH` / `DEEPSEEK_CONFIG_PATH` | — | 配置文件路径，默认 `~/.codewhale/config.toml` |
| `--profile <NAME>` | — | — | 配置 profile |
| `-r, --resume <ID>` | — | — | 恢复指定 session |
| `--continue` | — | — | 恢复最近 session |
| `-v, --verbose` | — | — | 详细日志 |
| `--yolo` | — | `approval_policy = "auto"` | YOLO 模式（自动批准所有操作） |
| `--max-subagents <N>` | — | `[subagents] max_concurrent = N` | 最大并发子 agent |

### 1.2 `serve` 子命令

| 参数 | 环境变量 | 说明 |
|------|---------|------|
| `--http` | — | 启动 Runtime HTTP API（端口 7878） |
| `--mcp` | — | 启动 MCP stdio 服务器 |
| `--mobile` | — | HTTP API + 移动端控制页（绑定 0.0.0.0） |
| `--acp` | — | ACP 编辑器代理 |
| `--host <HOST>` | — | 绑定地址，默认 127.0.0.1 |
| `--port <PORT>` | — | 端口，默认 7878 |
| `--workers <1-8>` | — | 后台 worker 数，默认 2 |
| `--cors-origin <URL>` | `DEEPSEEK_CORS_ORIGINS` | 额外 CORS 源(可重复) |
| `--auth-token <TOKEN>` | `DEEPSEEK_RUNTIME_TOKEN` | API 认证 Token |
| `--insecure` | — | 关闭认证 |
| `--qr` | — | 打印 QR 码 |

### 1.3 MCP 服务器自动启动参数

当前 `cw-mcp-server` 自动启动时使用的参数：

```python
subprocess.Popen([
    cw_bin, "serve", "--http", "--insecure", "--port", port
])
```

如需额外参数(workspace/workers)，修改 `AUTO_START_DELAY` 附近的 `_ensure_runtime` 函数。

---

## 二、config.toml 完整字段

配置文件位置: `~/.codewhale/config.toml`

### 2.1 顶层字段

| 字段 | 类型 | 环境变量 | 说明 |
|------|------|---------|------|
| `api_key` | string | `DEEPSEEK_API_KEY` | DeepSeek API key |
| `base_url` | string | `DEEPSEEK_BASE_URL` | DeepSeek API 地址 |
| `http_headers` | map | — | 附加 HTTP 请求头 |
| `default_text_model` | string | `DEEPSEEK_DEFAULT_TEXT_MODEL` | 默认文本模型 |
| `provider` | enum | `DEEPSEEK_PROVIDER` | 提供商: deepseek/openai/ollama/... |
| `model` | string | `DEEPSEEK_MODEL` | 当前模型 |
| `auth_mode` | string | — | 认证方式: api_key |
| `output_mode` | string | — | 输出模式 |
| `log_level` | string | — | 日志级别 |
| `telemetry` | bool | — | 遥测开关 |
| `approval_policy` | string | — | 审批策略: auto/suggest |
| `sandbox_mode` | string | — | 沙箱模式 |
| `fallback_providers` | array | — | 备用提供商列表 |
| `instructions` | array | — | 自定义指令文件路径 |

### 2.2 `[providers.<name>]` 提供商配置

每个提供商支持的字段：

| 字段 | 环境变量 | 说明 |
|------|---------|------|
| `api_key` | `<PROVIDER>_API_KEY` | 提供商 API key |
| `base_url` | `<PROVIDER>_BASE_URL` | 提供商 API 地址 |
| `model` | `<PROVIDER>_MODEL` | 提供商默认模型 |
| `mode` | — | 模式: agent/plan |
| `http_headers` | — | 附加请求头 |

环境变量映射：

| Provider | ENV API Key | ENV Model |
|----------|------------|-----------|
| deepseek | `DEEPSEEK_API_KEY` | `DEEPSEEK_MODEL` |
| openai | — | — |
| ollama | — | — |
| huggingface | `HF_TOKEN` | — |
| nvidia_nim | `NVIDIA_NIM_API_KEY` | — |
| volcengine | `VOLCENGINE_API_KEY` | `VOLCENGINE_MODEL` |
| openrouter | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` |
| moonshot | `MOONSHOT_API_KEY` | `MOONSHOT_MODEL` / `KIMI_MODEL_NAME` |
| wanjie_ark | `WANJIE_ARK_API_KEY` | `WANJIE_ARK_MODEL` |
| xiaomi_mimo | `XIAOMI_MIMO_API_KEY` | `XIAOMI_MIMO_MODEL` / `MIMO_MODEL` |
| atlascloud | `ATLASCLOUD_API_KEY` | — |

### 2.3 `[providers.deepseek]` 示例

```toml
[providers.deepseek]
api_key = "sk-xxx"
base_url = "https://api.deepseek.com/v1"
model = "deepseek-v4-pro"

[providers.deepseek.http_headers]
X-Custom = "value"
```

### 2.4 `[tools]` 工具开关

```toml
[tools]
enabled = ["exec_shell", "read_file"]   # 白名单
disabled = ["write_file"]               # 黑名单
```

### 2.5 `[network]` 网络策略

```toml
[network]
default_action = "deny"          # allow / deny
rules = [
  { host = "api.deepseek.com", action = "allow" },
  { host = "*.github.com", action = "allow" }
]
```

### 2.6 `[snapshots]` 快照配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | — | 是否启用 |
| `retain_days` | int | 7 | 保留天数 |
| `max_bytes` | int | — | 工作区大小上限 |

### 2.7 `[lsp]` LSP 诊断

```toml
[lsp]
enabled = false
delay_ms = 3000
```

### 2.8 `[hook_sinks]` Hook 输出

```toml
[hook_sinks]
unix_socket_path = "/tmp/codewhale.sock"
```

### 2.9 `[skills]` 社区技能

```toml
[skills]
registry_url = "https://raw.githubusercontent.com/Hmbown/CodeWhale/main/skills"
```

### 2.10 `[[harness_profiles]]` 模型 Profile

```toml
[[harness_profiles]]
provider_route = "deepseek"
model_pattern = "deepseek-v4*"
posture = "cache-heavy"
```

### 2.11 `[[hotbar]]` TUI 快捷栏

```toml
[[hotbar]]
slot = 1
action = "mode.agent"

[[hotbar]]
slot = 2
action = "session.compact"
```

### 2.12 `instructions` 指令文件

```toml
instructions = ["/path/to/global.md", "/path/to/project.md"]
```

这些指令会在每次对话中附加到 system prompt 之前。
本容器中已配置：`instructions = ["/setup/global.md"]`。

---

## 三、完整环境变量速查

### 通用

| 变量 | 说明 |
|------|------|
| `CODEWHALE_HOME` | 数据目录，默认 `~/.codewhale` |
| `CODEWHALE_CONFIG_PATH` | 配置文件路径 |
| `DEEPSEEK_CONFIG_PATH` | (弃用) 同 CODEWHALE_CONFIG_PATH |
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 |
| `DEEPSEEK_MODEL` | 当前模型 |
| `DEEPSEEK_DEFAULT_TEXT_MODEL` | 默认模型 |
| `DEEPSEEK_PROVIDER` | 提供商 |
| `DEEPSEEK_CORS_ORIGINS` | extra CORS origins (comma-separated) |

### Runtime API

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_RUNTIME_TOKEN` | API 认证 Token |
| `CODEWHALE_APP_SERVER_TOKEN` | (弃用) app-server 认证 Token |
| `DEEPSEEK_APP_SERVER_TOKEN` | (弃用) 同上 |

### 模型路由

| 变量 | 对应模型 |
|------|---------|
| `DEEPSEEK_MODEL` | deepseek |
| `VOLCENGINE_MODEL` / `VOLCENGINE_ARK_MODEL` | volcengine |
| `WANJIE_ARK_MODEL` / `WANJIE_MODEL` / `WANJIE_MAAS_MODEL` | wanjie_ark |
| `OPENROUTER_MODEL` | openrouter |
| `MOONSHOT_MODEL` / `KIMI_MODEL_NAME` / `KIMI_MODEL` | moonshot |
| `XIAOMI_MIMO_MODEL` / `MIMO_MODEL` | xiaomi_mimo |

### API Key

| Provider | ENV Key 变量 |
|----------|-------------|
| deepseek | `DEEPSEEK_API_KEY` |
| nvidia_nim | `NVIDIA_NIM_API_KEY` |
| openrouter | `OPENROUTER_API_KEY` |
| moonshot | `MOONSHOT_API_KEY` |
| huggingface | `HF_TOKEN` |

### 文件路径

| 文件 | 默认位置 |
|------|---------|
| config.toml | `~/.codewhale/config.toml` |
| state.db | `~/.codewhale/state.db` |
| mcp.json | `~/.codewhale/mcp.json` |
| secrets.json | `~/.codewhale/secrets/secrets.json` |
| events.jsonl | `.deepseek/events.jsonl` |

---

## 四、常见配置场景

### 最小配置（仅 AI 对话）

```toml
api_key = "sk-xxx"
default_text_model = "deepseek-v4-flash"
provider = "deepseek"
```

### 完整配置（带沙箱）

```toml
api_key = "sk-xxx"
default_text_model = "deepseek-v4-pro"
provider = "deepseek"
approval_policy = "suggest"
sandbox_mode = "auto"

[network]
default_action = "deny"

[network.rules]
"api.deepseek.com" = "allow"
"*.github.com" = "allow"

[tools]
disabled = ["mcp_*", "any_shell_command"]
```

### Runtime API（MCP 服务器后端）

```bash
# 环境变量方式
export DEEPSEEK_API_KEY="sk-xxx"
codewhale-tui serve --http --insecure --port 7878

# 或通过 config.toml (写好后直接启动)
codewhale-tui serve --http --insecure --port 7878
```

### 同时运行 TUI + Runtime API

```bash
# 终端 1: TUI 交互
codewhale

# 终端 2: Runtime API
codewhale-tui serve --http --insecure --port 7878
```

两者共享 `~/.codewhale/` 下的配置文件，但 TUI 不占端口。
> state.db 在多进程并发访问时可能存在短暂不一致，但不影响正确性。
