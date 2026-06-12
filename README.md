# CW-Remote

**让其他 AI 远程调用 CodeWhale 写代码。**

CW-Remote 是一个 MCP 桥接服务器，将 CodeWhale Runtime API 封装为 15 个 MCP 工具。  
任何支持 MCP 协议的 AI（Claude Desktop、另一个 CodeWhale 等）都可以通过它远程调用 CodeWhale 来写代码、执行命令、操作文件。

```

  另一个 AI                  CW-Remote                  CodeWhale
  (MCP Client) ──stdio──→  (Python MCP Server) ──HTTP──→  Runtime API
                                                              │
                                                          DeepSeek V4
                                                        (65%~86% cache hit)
```

## 核心能力

| 能力 | 说明 |
|------|------|
| **远程编码** | 让 AI 调用另一个 AI 写代码、重构、调试 |
| **执行命令** | 在目标机器上执行 shell 命令并获取输出 |
| **文件操作** | 读文件、写文件、修改文件 |
| **git 操作** | 查看分支状态、提交、推送 |
| **低成本** | 共享 prefix cache，缓存命中率 65%~86% |

## 快速开始

```bash
# 安装依赖
cd cw-remote
uv sync

# 启动 CodeWhale 后端
codewhale-tui serve --http --insecure

# 配置 MCP 客户端
```

MCP 客户端配置：

```json
{
  "servers": {
    "codeworker": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/cw-remote", "python3", "server.py"],
      "env": {
        "CODEWHALE_API_URL": "http://127.0.0.1:7878"
      }
    }
  }
}
```

## 15 个工具

```
AI 对话              会话管理              系统
────────────────────────────────────────────────
cw_run ★             cw_thread_create      cw_health
cw_poll ★            cw_thread_list        cw_workspace_status
cw_approve           cw_thread_update      cw_usage
cw_item_get          cw_thread_turn
cw_thread_get        cw_thread_resume
                     cw_thread_fork
                     cw_thread_compact
```

## 文档

| 文档 | 内容 |
|------|------|
| [`GUIDE.md`](GUIDE.md) | 详细用户手册（安装、配置、启动） |
| [`AI_GUIDE.md`](AI_GUIDE.md) | AI 使用手册（概念、工作流、最佳实践） |
| [`API_ANALYSIS.md`](API_ANALYSIS.md) | CodeWhale 启动参数分析 |
| [`CONFIG.md`](CONFIG.md) | 完整配置参考（config.toml + 环境变量） |

## 技术栈

- Python 3.11+, MCP SDK 1.27+
- uv 包管理
- 依赖 CodeWhale v0.8.53 ~ v0.8.58 Runtime API（版本不匹配时设置 `CW_REMOTE_SKIP_VERSION_CHECK=1` 可跳过检查）
