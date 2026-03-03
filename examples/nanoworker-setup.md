# nanoworker 安装和配置

nanoworker 是一个轻量级 Python CLI 工具，用于运行 Worker agent（Coder、Debug、Tester）。Leader（Claude Code）通过 Bash 调用 nanoworker 来分派任务。

## 安装

```bash
# 方式一：pipx（推荐）
pipx install /path/to/nanoworker/

# 方式二：pip + venv
cd /path/to/nanoworker/
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 配置

创建 `~/.nanoworker/config.json`：

```json
{
  "providers": {
    "openai": {
      "api_key": "your-api-key",
      "api_base": "https://your-openai-compatible-endpoint/v1"
    }
  },
  "workers": {
    "coder-1": { "role": "coder", "model": "openai/gpt-5.3-codex", "skills": ["coder"], "max_iterations": 30 },
    "coder-2": { "role": "coder", "model": "openai/gpt-5.3-codex", "skills": ["coder"], "max_iterations": 30 },
    "coder-3": { "role": "coder", "model": "openai/gpt-5.3-codex", "skills": ["coder"], "max_iterations": 30 },
    "debug-1": { "role": "debug", "model": "openai/gpt-5.3-codex", "skills": ["debug-engineer"], "max_iterations": 30 },
    "debug-2": { "role": "debug", "model": "openai/gpt-5.3-codex", "skills": ["debug-engineer"], "max_iterations": 30 },
    "debug-3": { "role": "debug", "model": "openai/gpt-5.3-codex", "skills": ["debug-engineer"], "max_iterations": 30 },
    "tester":  { "role": "tester", "model": "openai/gpt-5.3-codex", "skills": ["testing-engineer"], "max_iterations": 30 }
  }
}
```

Worker 数量可按需调整。Leader 的 Agent Registry 动态读取。

## 使用

```bash
# 基本调用
nanoworker <worker-name> "<task-message>" --workspace <project-path>

# 示例
nanoworker coder-1 --workspace /path/to/project "实现用户认证功能"
nanoworker debug-1 --workspace /path/to/project "审查 src/auth.py 的代码"
nanoworker tester --workspace /path/to/project "运行验证测试"

# 覆盖模型
nanoworker coder-1 --workspace /path/to/project --model openai/gpt-4o "quick task"

# 开启 debug 日志
nanoworker coder-1 --workspace /path/to/project -v "task"
```

## 输出格式

nanoworker 输出 JSON 到 stdout，日志到 stderr：

```json
{
  "success": true,
  "summary": "实现了用户认证功能，修改了 3 个文件",
  "files_changed": ["src/auth.py", "src/middleware.py", "tests/test_auth.py"],
  "iterations": 8
}
```

Leader 通过 `jq -r '.summary'` 提取回复。

## 角色工具集

| Role | 工具 |
|------|------|
| coder | read_file, write_file, edit_file, list_dir, exec |
| debug | read_file, write_file, edit_file, list_dir, exec |
| tester | read_file, write_file, list_dir, exec |

## Skills 目录

nanoworker 从 `skills/` 目录加载角色 SKILL.md，注入 system prompt：

```
skills/
├── coder/SKILL.md
├── debug-engineer/SKILL.md
└── testing-engineer/SKILL.md
```

## 验证

```bash
# 确认安装
which nanoworker
nanoworker --help

# 快速测试
nanoworker coder-1 --workspace /tmp "回答：你是什么角色？"
```
