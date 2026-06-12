# CodeWhale MCP Server — 用户手册

将 CodeWhale 的 AI 编程能力封装为 MCP 工具，让其他 AI（Claude Desktop、其他 CodeWhale 等）能远程调用 CodeWhale 来写代码、执行命令、操作文件。

## 快速开始

```bash
# 1. 安装 uv（如果还没有）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 进入项目目录
cd /workspace/cw-mcp-server

# 3. 一键安装依赖（uv 自动管理虚拟环境）
uv sync

# 4. 启动 CodeWhale 后端
codewhale-tui serve --http --insecure --port 7878

# 5. 配置 MCP 客户端
```

MCP 客户端配置：

```json
{
  "servers": {
    "codeworker": {
      "command": "uv",
      "args": ["run", "--directory", "/workspace/cw-mcp-server", "python3", "server.py"],
      "env": {
        "CODEWHALE_API_URL": "http://127.0.0.1:7878"
      }
    }
  }
}
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CODEWHALE_API_URL` | `http://127.0.0.1:7878` | CodeWhale Runtime API 地址 |
| `DEEPSEEK_RUNTIME_TOKEN` | — | Bearer 认证令牌（`serve --http` 时自动生成） |

## 启动参数

```bash
# 安全模式（推荐，自动生成 token）
codewhale-tui serve --http

# 无认证模式（仅 loopback）
codewhale-tui serve --http --insecure

# 指定端口
codewhale-tui serve --http --port 7878

# 后台运行
nohup codewhale-tui serve --http --insecure > /tmp/cw.log 2>&1 &
```

## 15 个工具概览

### 核心对话（AI 调用方使用）

| 工具 | 用途 |
|------|------|
| `cw_run` | 启动 AI 任务，立即返回 |
| `cw_poll` | 查询任务进度，支持阻塞等待 |
| `cw_approve` | 批准/拒绝 AI 执行命令 |
| `cw_item_get` | 查看单条详细内容 |
| `cw_thread_get` | 查看对话历史 |

### 会话管理

| 工具 | 用途 |
|------|------|
| `cw_thread_create` | 创建空对话 |
| `cw_thread_list` | 列出所有对话 |
| `cw_thread_update` | 修改对话属性 |
| `cw_thread_turn` | 在已有对话中发消息 |
| `cw_thread_resume` | 恢复对话 |
| `cw_thread_fork` | 分叉对话（副本） |
| `cw_thread_compact` | 压缩旧对话节省 token |

### 系统

| 工具 | 用途 |
|------|------|
| `cw_health` | 健康检查 |
| `cw_workspace_status` | Git 状态 |
| `cw_usage` | Token 用量和费用 |

## 版本兼容

此 MCP 服务器锁定 CodeWhale v0.8.53 的 Runtime API。
启动时会自动检查版本：

```
[cw-mcp-server] CodeWhale Runtime API v0.8.53 (127.0.0.1:7879)
```

如果版本低于 0.8.50 或 >= 0.9.0 会输出警告。如果 Runtime API 未启动，会尝试自动启动
（需要 `codewhale-tui` 在 PATH 中），失败则报错退出。

## 性能

- **缓存命中率**: 65%~86%（DeepSeek prefix cache）
- **单次对话费用**: ~$0.002
- **每次 MCP 调用超时**: `cw_poll` 默认 60 秒，可配置

## 文件结构

```
cw-mcp-server/
├── API_ANALYSIS.md   ← 启动参数分析
├── CONFIG.md         ← 完整配置参考（config.toml + 环境变量）
├── AI_GUIDE.md       ← AI 使用手册（给调用方 AI 看）
├── README.md         ← 本文件
├── client.py         ← HTTP 客户端
├── server.py         ← MCP 服务器
└── pyproject.toml
```
