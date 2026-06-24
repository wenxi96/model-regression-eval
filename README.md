# Model Regression Eval

一个用于检测模型/Agent 能力回归的小型评测框架。它不是“智商测试”，而是用固定题库、结构化输出、确定性判分、分层抽样、token budget、重复运行统计与成对基线比较，判断模型在特定能力维度上是否出现可复现下降。

当前版本：`0.9.4`

## 核心功能

- 300 题中文核心题库：数学、逻辑、代码、阅读、指令遵守、鲁棒性、元认知。
- 二维评测配置：`--profile smoke|standard|full` 控制题量，`--depth quick|confirm|deep` 或 `--repeats N` 控制每题循环次数。
- 请求与 token 成本控制：`--max-requests`、`--max-observed-tokens`、`budget` 子命令。
- 会话评测主流程：`export-session` 生成不泄露答案的题包，当前会话 Agent 或同模型 subagent 返回固定答案集，`import-session` 导入判分。
- 多 runner 插件化：Codex、Claude、Gemini、OpenAI-compatible、Hermes、HTTP、自定义 subprocess、OpenCode、mock；这些属于 CI/API/自动化高级路径，不是 skill 默认评测路径。
- 手工/外部 Agent 兼容流程：`export-prompts` / `import-results` 仍保留；`export-prompts` 默认不导出 expected，只有显式 `--include-answers` 才用于调试。
- Skillpack 生成：`skill build` 只生成包不安装，支持 ChatGPT、Claude、Codex、Gemini、Windsurf、Cursor、Cline、GitHub Copilot、OpenCode、Hermes、主流 AI IDE、Web 手工流程、Qwen/GLM API preset 与 generic 兼容目标。
- Deterministic graders：整数、字符串、选择题、包含全部关键词、NAND 表达式、数值容差、无序集合。
- 报告指标：accuracy、score、weighted accuracy、weighted score、majority accuracy、consistency、confidence calibration、difficulty/tier/answer_mode 分组、unstable cases、stable failures、token 汇总。
- Baseline/candidate compare：case-level regressions、task-majority stable regressions、McNemar/sign-test 风格统计。

## 0.9.4 会话评测工作流

本版本将 skill 默认使用方式调整为“会话内评测”：当前 Agent 或同模型 subagent 直接回答不含 expected 的题包，本地 evaluator 只负责出题、导入、判分和报告。`run --runner` 仍保留给 CI/API/自动化场景，但不再是 CLI/IDE/Web skill 的默认能力评测路径。

- 新增 `export-session`：导出不泄露答案的会话题包，包含固定答案集 schema。
- 新增 `import-session`：导入当前会话、subagent、手动新会话或 runner 产出的答案集，并记录 `execution_mode` / `agent_instance`。
- `export-prompts` 默认不再输出 `expected` / `grader`；只有显式 `--include-answers` 才生成带答案调试文件。
- 任务 metadata 支持 `difficulty`、`tier`、`answer_mode`、`rubric`、`variant_group` 的基础校验，未标注任务默认为 `basic` / `baseline` / `deterministic`，并支持 `--difficulty` / `--tier` / `--answer-mode` 过滤。
- 报告新增 score、weighted score、平均置信度、高置信错误率，以及按 difficulty / tier / answer_mode 分组。
- 已吸收的 20 道复杂数学/逻辑题标记为 `difficulty=hard`、`tier=frontier`，可作为第一批能力上限子集。
- 多片段类 grader（`contains_all`、`contains_ordered`、`unordered_set`）在保持 `correct` 严格判定的同时提供部分得分。

## 0.9.3 题库与校验更新

本版本是题库破坏性更新版本：`tasks/core.zh.jsonl` 仍保持 300 道 active 题，但题目组成、答案分布和部分 expected 已调整，旧版本 baseline 不应与本版本结果直接比较。`compare` 仍会在任务集或 case 集不一致时输出 warning。

- 新增 `tests/test_task_answers.py`，对可自动复算的算术、方程、单位换算、库存状态题以及可执行 Python 输出题进行交叉校验。
- 新增 `tests/test_task_quality.py`，守住选择题答案字母分布、近重复 prompt 骨架、domain 覆盖和题库总数。
- `exact_string` 与 `choice` grader 支持 `metadata.accept` 等价答案白名单，并在加载题库时校验其必须为字符串列表。
- `logic_nand_nand_expression_001` 改用结构化 `nand_expression` 判分，避免 `contains_all` 接受碎片拼接或拒绝合法 LaTeX 反斜杠形式。
- 修复已确认的答案与题面缺陷，包括 `logic_truthfulness_004`、`logic_conditional_011`、`instruction_sort_005`、`reading_table_001`、`logic_negation_008`、`code_trace_001`、`code_trace_004`。
- 吸收 20 道复杂数学/逻辑题，覆盖组合、几何、递推、概率、SVM、变量质量运动、密码约束和字符平均解密等方向。
- 复审记录见 `docs/task_review.md`。

## 0.6.1 修复说明

本版本修复了审查中确认的边界与性能问题：

- `_proportional_quotas` 在请求数量超过总容量时会防御性封顶，避免外部复用时出现非进展循环。
- Codex/CLI runner 的版本查询增加缓存，避免每个 case 重复执行 `--version` 子进程。
- `run` 命令的 `results.jsonl` 改为增量追加写入，避免每个 case 全量重写造成 O(n²) IO。
- `compare` 在 baseline/candidate 任务集、case 集或 domain 不一致时输出 warning；domain 不一致的 paired case 不再从 by-domain regression 统计中丢失。
- `numeric` grader 增加首个数值提取兜底，可接受 `约等于3.14`、`3.14π` 等 answer 字段。
- 新增 `.gitignore` 与 `dev` 可选依赖：`pip install -e .[dev]`。

## Skillpack / Agent 包生成

除了作为普通 CLI 项目运行，本项目还可以生成面向不同 Agent/IDE/Web 环境的便携包。生成命令只写入 `--out-dir`，不会自动安装或修改任何全局 Agent 配置。

本项目区分两类部署：

- `skill install-skill`：真实 Agent Skill 安装。默认把一份 canonical skill copy 安装到 `~/.agents/skills/model-regression-eval`，再按需把 IDE/Agent 自己的 skills 管理目录软链到这份全局 copy。
- `skill install-rules` / `skill install`：兼容旧 Agent 的项目规则安装，会写入 `AGENTS.md`、`CLAUDE.md`、`.cursor/rules/` 等 managed block，并复制一份项目本地包到 `.model-regression-eval/package`。

如果目标环境支持 `SKILL.md` skills 目录，应优先使用 `install-skill`，不要用规则文件伪装 skill 安装。

目标按支持等级分为：

- `strong`：有明确专用入口或项目规则文件。
- `best_effort`：生成该 IDE 常见规则文件 + `AGENTS.md` 兜底，需用户确认本地版本会读取。
- `manual_web`：网页产品通常不能安装本地可执行 skill，使用导出 prompts / 导入结果流程。
- `api_preset`：API/网关预设，实际调用走 OpenAI-compatible、HTTP 或 subprocess runner。
- `generic`：未知目标的兼容兜底。

常用 target：

| target | 支持等级 | 输出用途 |
|---|---|---|
| `chatgpt` | strong | 标准 ChatGPT Skill 包。单目标构建时输出 `skill.zip`。 |
| `claude` / `claude-code` | strong | Claude / Claude Code 包，含 `SKILL.md`、`CLAUDE.md`、`.claude/rules/`。 |
| `codex` | strong | Codex Skill 包，含 `SKILL.md` 与 `AGENTS.md` 兼容说明。 |
| `gemini` / `gemini-cli` | strong | Gemini CLI 项目指令包，含 `GEMINI.md` 与 `.gemini/settings.json`。 |
| `windsurf` | strong | Windsurf/Devin Desktop 包，含 `.devin/rules/`、`.windsurf/rules/`、`.windsurfrules`、`AGENTS.md`。 |
| `cline` | strong | Cline Skill 包，含 `SKILL.md`、`.clinerules/` 与 `AGENTS.md` 兼容说明。 |
| `github-copilot` / `copilot` | strong | GitHub Copilot 包，含 `.github/copilot-instructions.md` 和 `.github/instructions/*.instructions.md`。 |
| `opencode` | strong | OpenCode 包，含 `AGENTS.md` 与 `OPENCODE.md`。 |
| `hermes` | strong/api | Hermes / OpenAI-compatible 指令包。 |
| `cursor`、`roo-code`、`kilo-code`、`zed`、`aider`、`trae`、`continue`、`junie`、`kiro`、`augment-code`、`warp` | best_effort | 包含 `SKILL.md`；同时保留对应 AI IDE 规则文件 + `AGENTS.md` 兜底用于兼容旧环境。 |
| `ai-ide` | best_effort | 多规则文件包，适合不确定 IDE 会读取哪种规则文件时使用。 |
| `web-manual`、`qwen-web`、`glm-web`、`kimi-web`、`deepseek-web`、`doubao-web`、`yuanbao-web`、`claude-web`、`gemini-web` | manual_web | 网页产品手工导出/导入评测包。 |
| `qwen-api`、`glm-api` | api_preset | OpenAI-compatible/API preset 包。 |
| `generic` | generic | 通用兼容包；未知 target 会自动降级为 generic。 |
| `all` | mixed | 一次性生成所有目标包。 |

查看完整 target 清单：

```bash
python -m model_regression_eval.cli skill list-targets
```

查看已知 skills 目录预设：

```bash
python -m model_regression_eval.cli skill list-skill-dirs
```

生成 ChatGPT Skill 包：

```bash
python -m model_regression_eval.cli skill build \
  --target chatgpt \
  --out-dir dist/chatgpt
# 输出：dist/chatgpt/skill.zip
```

生成某个 IDE 包：

```bash
python -m model_regression_eval.cli skill build \
  --target windsurf \
  --out-dir dist/skillpacks
```

生成网页手工评测包：

```bash
python -m model_regression_eval.cli skill build \
  --target qwen-web \
  --out-dir dist/skillpacks
```

生成所有目标包：

```bash
python -m model_regression_eval.cli skill build \
  --target all \
  --out-dir dist/skillpacks
```

生成目录而不是 zip：

```bash
python -m model_regression_eval.cli skill build \
  --target ai-ide \
  --format directory \
  --out-dir dist/skillpacks
```

每个包都携带完整 300 题题库与评测核心。默认 skill 使用方式是在 Agent 对话中生成题包、让当前 Agent 或同模型 subagent 作答，再由本地 evaluator 导入评分。入口脚本为 evaluator 工具，不表示默认要通过 CLI runner 请求模型：

```bash
./scripts/mre export-session --tasks tasks/core.zh.jsonl --profile smoke --depth quick --out runs/session_packet.json
```

安装自检可单独运行 `mock`；它会直接返回 expected answer，只用于确认包、题库加载和判分链路正常，不能作为 Agent 能力测试结果：

```bash
./scripts/mre run --runner mock --tasks tasks/core.zh.jsonl --profile smoke --depth quick --out-dir runs --run-id selfcheck
```

Windows 可用：

```bat
scripts\mre.bat export-session --tasks tasks/core.zh.jsonl --profile smoke --depth quick --out runs\session_packet.json
```

## Skill 安装

真实 skill 安装默认遵循“全局 copy + 软链”的模式：

1. canonical copy：`~/.agents/skills/model-regression-eval`
2. 可选链接：`<ide-or-agent-skills-dir>/model-regression-eval -> ~/.agents/skills/model-regression-eval`

默认 dry-run：

```bash
python -m model_regression_eval.cli skill install-skill --dry-run
```

实际安装到默认全局目录：

```bash
python -m model_regression_eval.cli skill install-skill
```

指定目标时，CLI 会优先安装全局 copy，再为已知 target 选择默认软链目录：

| target | 默认软链目录 |
|---|---|
| `codex` | 无额外软链；Codex 直接读取 canonical `~/.agents/skills/model-regression-eval` |
| `claude` | `~/.claude/skills/model-regression-eval` |
| `cline` | `~/.cline/skills/model-regression-eval` |
| `cursor` | `<project-root>/.cursor/skills/model-regression-eval` |
| 其他 / `generic` | 不额外软链，只安装 canonical global copy |

示例：

```bash
python -m model_regression_eval.cli skill install-skill --target codex
python -m model_regression_eval.cli skill install-skill --target cursor --project-root /path/to/project
```

已确认的官方 skills 目录来源：

- Codex：官方 [Agent Skills 文档](https://developers.openai.com/codex/skills/)列出 repo/user/admin skills roots：`$REPO_ROOT/.agents/skills`、`$HOME/.agents/skills`、`/etc/codex/skills`，且说明支持 symlinked skill folders。
- Cursor：官方 [Agent Skills 文档](https://cursor.com/docs/skills)列出 project-level `.cursor/skills/`、user-level `~/.agents/skills/`。
- Cline：官方 [Skills 文档](https://docs.cline.bot/customization/skills)列出 workspace `.cline/skills/`，也识别 `.clinerules/skills/`、`.claude/skills/`；global `~/.cline/skills/`。
- Claude Code：官方 [Skills 文档](https://code.claude.com/docs/en/skills)说明 personal `~/.claude/skills/<skill>/SKILL.md`，并确认 `.claude/skills/<skill>/SKILL.md` 形式可用。

未在官方文档中确认的 IDE/Agent，不预设路径；安装时用 `--skills-dir` 或脚本变量 `SKILLS_DIR` 显式传入。

自定义 canonical 全局目录和 IDE/项目 skills 目录：

```bash
python -m model_regression_eval.cli skill install-skill \
  --global-skills-dir /tmp/agents/skills \
  --skills-dir /tmp/project/.cursor/skills \
  --target cursor
```

安装会校验已存在的全局 skill：

- 版本一致：返回 `validated_current`，不会复制第二份；不同 target 会复用同一份 canonical copy，只新增或校验对应 skills 目录软链。
- 版本不一致：默认失败并提示 `--overwrite`。
- 链接目录已有非预期路径：默认失败，避免覆盖用户文件；显式 `--overwrite` 才会替换。

第三方 Agent 的一键安装脚本默认也是 dry-run。确认输出后再设置 `DRY_RUN=0`：

```bash
curl -fsSL https://raw.githubusercontent.com/wenxi96/model-regression-eval/main/scripts/install.sh | sh
curl -fsSL https://raw.githubusercontent.com/wenxi96/model-regression-eval/main/scripts/install.sh | sh -s -- --target cursor --apply
curl -fsSL https://raw.githubusercontent.com/wenxi96/model-regression-eval/main/scripts/install.sh | sh -s -- --apply --global-skills-dir "$HOME/.agents/skills" --skills-dir "$PWD/.cursor/skills"
```

PowerShell：

```powershell
iwr https://raw.githubusercontent.com/wenxi96/model-regression-eval/main/scripts/install.ps1 -OutFile install.ps1
.\install.ps1 -Target cursor
.\install.ps1 -Target cursor -Apply
```

需要兼容旧规则文件安装时，显式使用：

```bash
python -m model_regression_eval.cli skill install-rules --target codex --dry-run
python -m model_regression_eval.cli skill install-rules --target codex --overwrite
```


## 安装

```bash
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e .
# 开发/测试依赖：
pip install -e .[dev]
```

不安装也可以在源码目录直接运行：

```bash
python -m model_regression_eval.cli --help
```

## 目录结构

```text
model_regression_eval/
  model_regression_eval/      # Python 包
  schemas/final_answer.schema.json
  tasks/core.zh.jsonl         # 中文核心题库，300 题
  examples/                   # 示例预算与报告
  tests/                      # 单元测试
  README.md
  pyproject.toml
```

## 评测策略

`profile` 只控制题量：

| profile | 任务数 | 用途 |
|---|---:|---|
| `smoke` | 40 | 低成本冒烟测试 |
| `standard` | 100 | 默认回归筛查 |
| `full` | 300 | 完整题库确认 |

`depth` 控制每题循环次数：

| depth | repeats | 用途 |
|---|---:|---|
| `quick` | 1 | 单次筛查，成本最低 |
| `confirm` | 3 | 常规复核 |
| `deep` | 5 | 高成本稳定性检查 |

`--repeats N` 优先级高于 `--depth`。旧的 `--profile deep` 仍兼容，等价于 `--profile full --depth confirm`，但不推荐新用法。

## 题库质量与公正性验证

当前 `tasks/core.zh.jsonl` 适合做固定题集下的回归筛查，但不能仅凭“题目由 GPT 生成”就认定足够公正或高质量。用于第三方 Agent 测试前，至少应完成以下核验：

- 结构核验：运行 `python -m pytest -q`（没有 `python` alias 时用 `python3`），确认 300 题可加载、ID 与 prompt 不重复、mock answer 可被确定性判分。
- 覆盖核验：运行 `budget --profile full --depth quick`，检查 domain / skill 分布是否符合本次测试目的。
- 答案复核：对新增或改动题目进行人工或独立模型复算，重点检查数学、逻辑、代码 trace、歧义题和 contains_all 题。
- 偏差核验：避免题目只覆盖某一语言、文化背景、固定表达模板或单一难度层级。
- 实证校准：用至少一个稳定 baseline 跑 `standard confirm` 或 `full confirm`，结合 majority accuracy、consistency、stable regressions 和人工复核判断，不用单次 accuracy 下结论。

本仓库已提供结构、判分和题库质量自检，但还没有独立专家审题、难度标定、跨模型区分度分析或偏差审计。因此当前题库可以作为工程回归筛查基线，不应单独作为模型综合能力排名或公正性评估的最终依据。

本版本内置的题库守门测试包括：

- `tests/test_task_answers.py`：自动复算一部分可计算 expected，执行可隔离运行的 Python 输出题，并对部分复杂题做穷举或精确方程校验。
- `tests/test_task_quality.py`：检查选择题答案字母偏置、近重复 prompt 骨架、domain 覆盖和 300 题总量。
- `tests/test_tasks_file.py`：检查题库可加载、ID 唯一、prompt 唯一、mock answer 可被确定性判分。

安装与判分自检组合。以下命令使用 `mock`，会直接返回 expected answer，只能证明评测链路正常，不能证明模型或 Agent 真实能力：

```bash
# 40 题 x 1 次
python -m model_regression_eval.cli run --runner mock --tasks tasks/core.zh.jsonl --profile smoke --depth quick

# 100 题 x 3 次
python -m model_regression_eval.cli run --runner mock --tasks tasks/core.zh.jsonl --profile standard --depth confirm

# 300 题 x 1 次
python -m model_regression_eval.cli run --runner mock --tasks tasks/core.zh.jsonl --profile full --depth quick
```

## 先估算成本

```bash
python -m model_regression_eval.cli budget \
  --tasks tasks/core.zh.jsonl \
  --profile standard \
  --depth confirm
```

输出会包含任务数、请求数、估算 prompt tokens，以及按 domain / skill 的分布。估算值是 tokenizer-free 规划值；真实消耗以 runner 返回的 usage 为准。

## 会话 Agent / Skill 默认流程

真实使用 skill 时，默认不要让本工具后台调用其他 CLI/API runner 去请求模型。推荐流程是：当前 CLI/IDE/Web 对话中的 Agent 读取 skill，拿到一组不含 expected 的题目，直接返回固定格式答案集；如果当前环境支持创建 subagent，则每个 subagent 必须使用和主会话完全一致的供应商与模型。

导出不泄露答案的会话题包：

```bash
python -m model_regression_eval.cli export-session \
  --tasks tasks/core.zh.jsonl \
  --profile smoke \
  --depth quick \
  --out runs/session_packet.json
```

只测已标注的 hard/frontier 子集：

```bash
python -m model_regression_eval.cli export-session \
  --tasks tasks/core.zh.jsonl \
  --tier frontier \
  --difficulty hard \
  --out runs/frontier_packet.json
```

Agent 或 subagent 应返回 JSON 对象：

```json
{
  "answers": [
    {
      "task_id": "math_001",
      "repeat": 1,
      "agent_instance": "subagent-1",
      "execution_mode": "subagent",
      "answer": "21",
      "confidence": 0.9,
      "reasoning_summary": "一句话说明关键依据"
    }
  ]
}
```

导入答案集并判分：

```bash
python -m model_regression_eval.cli import-session \
  --tasks tasks/core.zh.jsonl \
  --answers runs/session_answers.json \
  --out-dir runs \
  --run-id session_agent_test \
  --runner-name session_agent
```

执行模式口径：

- `current_session`：当前会话直接作答，不能视为多轮独立样本。
- `subagent`：同供应商、同模型的子代理作答，适合做 repeats。
- `manual_new_session`：不支持 subagent 时，用户或宿主 IDE 手动/后台创建的新会话。
- `runner`：高级自动化路径，由本工具适配器调用外部 runner。

题库层级口径：

- 未标注旧题默认是 `difficulty=basic`、`tier=baseline`、`answer_mode=deterministic`。
- 当前第一批 20 道复杂数学/逻辑题标为 `difficulty=hard`、`tier=frontier`。
- `rubric` / `judge` 题第一阶段不会默认进入确定性准确率；未配置 judge 时会标记 unsupported。

## 支持的 runner（高级自动化路径）

runner 适合 CI、API 网关、自动化 harness 或受控批量回归；它不是 skill 在 CLI/IDE/Web 对话中的默认评测路径。

| runner | 说明 |
|---|---|
| `mock` | 直接返回 expected answer，仅用于安装、题库加载和判分自检；不要作为模型或 Agent 能力评测。 |
| `codex` / `codex_cli` | 调用本地 Codex CLI。 |
| `claude` / `claude_cli` | 调用 Claude Code CLI。默认使用 `claude --bare -p ... --output-format json --json-schema ...`。 |
| `claude_api` | 调用 Anthropic Messages API。需要 `ANTHROPIC_API_KEY` 或 `--agent-api-key`。 |
| `gemini` / `gemini_cli` | 调用 Gemini CLI。默认使用 `gemini -p ... --output-format json`。不同版本 CLI 若参数不兼容，可用 `subprocess` runner 兜底。 |
| `gemini_api` | 调用 Gemini generateContent REST API。需要 `GEMINI_API_KEY` / `GOOGLE_API_KEY` 或 `--agent-api-key`。 |
| `openai_api` | 调用 OpenAI Chat Completions 风格 API，默认 base URL 为 `https://api.openai.com/v1`。 |
| `openai_compatible` | 调用 OpenAI-compatible `/chat/completions` 服务。适合本地模型网关、中转服务、vLLM、Ollama 兼容层等。 |
| `hermes` | Hermes 适配别名，按 OpenAI-compatible 接口调用。使用 `HERMES_BASE_URL`、`HERMES_API_KEY`、`HERMES_MODEL` 或显式参数。 |
| `http` | 通用 HTTP Agent：POST `{prompt, model, schema}` 到 `--agent-url`。 |
| `subprocess` | 通用本地命令适配器，使用 `--agent-command`，prompt 同时写入 stdin 和临时 `{prompt_file}`。 |
| `opencode` / `opencode_cli` | OpenCode CLI 适配器。默认 `opencode run <prompt>`；若你的版本不同，建议用 `subprocess` runner 自定义命令。 |

### Codex CLI

```bash
python -m model_regression_eval.cli run \
  --runner codex \
  --tasks tasks/core.zh.jsonl \
  --profile standard \
  --depth quick \
  --model gpt-5.5 \
  --effort medium
```

### Claude CLI

```bash
python -m model_regression_eval.cli run \
  --runner claude_cli \
  --tasks tasks/core.zh.jsonl \
  --profile smoke \
  --depth quick \
  --model claude-sonnet-4-5
```

Claude Code CLI 默认会接收 `--json-schema`。如果本地版本参数变化，可改用：

```bash
python -m model_regression_eval.cli run \
  --runner subprocess \
  --agent-command 'claude --bare -p @prompt_file --output-format json' \
  --tasks tasks/core.zh.jsonl \
  --profile smoke
```

### Claude API

```bash
export ANTHROPIC_API_KEY=...
python -m model_regression_eval.cli run \
  --runner claude_api \
  --tasks tasks/core.zh.jsonl \
  --profile smoke \
  --model claude-sonnet-4-5
```

### Gemini CLI

```bash
python -m model_regression_eval.cli run \
  --runner gemini_cli \
  --tasks tasks/core.zh.jsonl \
  --profile smoke \
  --model gemini-2.5-pro
```

### Gemini API

```bash
export GEMINI_API_KEY=...
python -m model_regression_eval.cli run \
  --runner gemini_api \
  --tasks tasks/core.zh.jsonl \
  --profile smoke \
  --model gemini-2.5-pro
```

### OpenAI / OpenAI-compatible / Hermes

```bash
export OPENAI_API_KEY=...
python -m model_regression_eval.cli run \
  --runner openai_api \
  --tasks tasks/core.zh.jsonl \
  --profile smoke \
  --model gpt-5.5
```

本地 OpenAI-compatible 服务：

```bash
python -m model_regression_eval.cli run \
  --runner openai_compatible \
  --agent-url http://localhost:8000/v1 \
  --model local-model \
  --tasks tasks/core.zh.jsonl \
  --profile smoke
```

Hermes：

```bash
export HERMES_BASE_URL=http://localhost:8000/v1
export HERMES_MODEL=NousResearch/Hermes-3-Llama-3.1-8B
python -m model_regression_eval.cli run \
  --runner hermes \
  --tasks tasks/core.zh.jsonl \
  --profile smoke
```

### 通用 HTTP Agent

你的服务只需要接受：

```json
{
  "prompt": "...",
  "model": "...",
  "schema": {...}
}
```

并返回以下任意一种可解析形态：

```json
{"final_json":{"answer":"21","confidence":0.9,"reasoning_summary":"..."},"usage":{"input_tokens":100,"output_tokens":20}}
```

或：

```json
{"answer":"21","confidence":0.9,"reasoning_summary":"..."}
```

运行：

```bash
python -m model_regression_eval.cli run \
  --runner http \
  --agent-url http://localhost:8000/eval \
  --agent-header 'Authorization: Bearer xxx' \
  --tasks tasks/core.zh.jsonl \
  --profile smoke
```

### 通用 subprocess Agent

```bash
python -m model_regression_eval.cli run \
  --runner subprocess \
  --agent-command 'my-agent --model {model} --schema {schema_path} --prompt-file {prompt_file}' \
  --model my-model \
  --tasks tasks/core.zh.jsonl \
  --profile smoke
```

支持占位符：

```text
{prompt_file}
{schema_path}
{final_out_path}
{model}
```

同时 prompt 会写入 stdin，便于兼容读取 stdin 的工具。

## Legacy 单题导出 / 外部 Agent 流程

优先使用 `export-session` / `import-session`。`export-prompts` 只保留给已有集成或逐题调试使用；默认不会导出 `expected`，避免把答案泄露给被测 Agent。

```bash
python -m model_regression_eval.cli export-prompts \
  --tasks tasks/core.zh.jsonl \
  --profile smoke \
  --out runs/manual_prompts.jsonl
```

如果确实要生成带答案的调试文件，必须显式添加 `--include-answers`，且不要交给被测 Agent。

回答 JSONL 仍可通过旧导入命令导入：

```json
{"task_id":"math_001","repeat":1,"answer":"21","confidence":0.9,"reasoning_summary":"..."}
```

```bash
python -m model_regression_eval.cli import-results \
  --tasks tasks/core.zh.jsonl \
  --outputs runs/manual_outputs.jsonl \
  --out-dir runs \
  --run-id manual_agent_test \
  --runner-name web_agent
```

## 比较 baseline 与 candidate

```bash
python -m model_regression_eval.cli compare \
  --baseline runs/baseline/results.jsonl \
  --candidate runs/candidate/results.jsonl \
  --out-md runs/compare.md \
  --out-json runs/compare.json
```

多次重复运行时，应优先看：

- `majority_accuracy`
- `consistency_rate`
- `stable_regressions`
- `net_stable_regressions`

不要只凭单次 accuracy 断言“降智”。

## 自检

```bash
python -m pytest -q
```

mock 全量自检：

```bash
python -m model_regression_eval.cli run \
  --runner mock \
  --tasks tasks/core.zh.jsonl \
  --profile full \
  --depth quick \
  --out-dir runs \
  --run-id mock_full_300
```

## 注意事项

- 不同 runner 的 token usage 字段不同。报告会区分 observed tokens、null/unknown tokens 与估算 prompt tokens。
- CLI runner 的工具使用检测取决于其输出结构。Codex JSONL 支持较好；HTTP/API runner 需要服务返回 tool events 才能可靠检测。
- Hermes 没有单一标准官方 Agent CLI；本项目将 `hermes` 实现为 OpenAI-compatible runner 便于接入本地或网关部署。
- OpenCode CLI 生态变化较快；内置 `opencode_cli` 是一个默认适配，真实项目中推荐用 `subprocess` runner 精确指定命令。

## One-click and project installation

Version 0.9.2 introduced the project-local installer and fixed direct target-specific skillpack installation. The existing `skill build` command still only creates packages; `skill install` writes safe, managed project files.

### Detect the current environment

```bash
python -m model_regression_eval.cli skill detect --project-root .
```

The detector reports both the likely IDE/agent target and the local runtime system. It looks for known IDE/agent files such as `CLAUDE.md`, `GEMINI.md`, `AGENTS.md`, `.windsurf/rules`, `.devin/rules`, `.clinerules`, `.cursor/rules`, GitHub Copilot instruction files, and common local CLI commands. It also reports Windows/macOS/Linux/WSL, shell hints, Python path, git/curl/wget availability, and the recommended launcher for the installed package. If no specific agent signal is found, it falls back to `generic`.

JSON output includes the same information:

```bash
python -m model_regression_eval.cli skill detect --project-root . --json
```

### Dry-run before installing

```bash
python -m model_regression_eval.cli skill install \
  --target auto \
  --project-root . \
  --dry-run
```

### Install into the current project

```bash
python -m model_regression_eval.cli skill install \
  --target auto \
  --project-root .
```

The installer:

- writes the evaluator package under `.model-regression-eval/package/`;
- writes agent rules as managed blocks or managed files;
- preserves existing root files such as `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md`;
- backs up modified files under `.model-regression-eval/backups/`;
- records all writes in `.model-regression-eval/install-manifest.json`;
- never writes API keys and never installs to global user directories by default.

To refresh an existing managed package, pass `--overwrite`.

### Uninstall

```bash
python -m model_regression_eval.cli skill uninstall --project-root . --dry-run
python -m model_regression_eval.cli skill uninstall --project-root .
```

Uninstall removes only files/blocks recorded in `.model-regression-eval/install-manifest.json`. Backups are kept.

### Install from URL

The Python installer supports zip URLs and JSON install manifests that point to a source zip:

```bash
python -m model_regression_eval.cli skill install \
  --from-url https://github.com/wenxi96/model-regression-eval/archive/refs/heads/main.zip \
  --target auto \
  --project-root . \
  --dry-run
```

Optional checksum verification:

```bash
python -m model_regression_eval.cli skill install \
  --from-url https://github.com/wenxi96/model-regression-eval/archive/refs/heads/main.zip \
  --sha256 <expected-sha256> \
  --target auto \
  --project-root .
```

### Install from Git

```bash
python -m model_regression_eval.cli skill install \
  --from-git https://github.com/wenxi96/model-regression-eval.git \
  --ref main \
  --target auto \
  --project-root . \
  --dry-run
```

### Third-party Agent distribution

推荐给第三方 Agent 提供两种入口。公开仓库场景优先使用仓库内的一键脚本；脚本会下载公开源码 zip，在当前项目目录执行安装，并默认只做 dry-run。

1. Unix/macOS/Linux/WSL:

```bash
curl -fsSL https://raw.githubusercontent.com/wenxi96/model-regression-eval/main/scripts/install.sh -o install.sh
bash install.sh                    # dry-run by default
DRY_RUN=0 bash install.sh           # apply changes
```

指定目标时设置 `TARGET`：

```bash
TARGET=codex bash install.sh
DRY_RUN=0 TARGET=codex bash install.sh
```

2. Windows PowerShell:

```bash
irm https://raw.githubusercontent.com/wenxi96/model-regression-eval/main/scripts/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File install.ps1
powershell -ExecutionPolicy Bypass -File install.ps1 -Apply
```

指定目标时传入 `-Target`：

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -Target codex
powershell -ExecutionPolicy Bypass -File install.ps1 -Target codex -Apply
```

3. 已经安装或 clone 本项目的环境，也可以直接从公开 zip 或 Git 安装：

```bash
python -m model_regression_eval.cli skill install \
  --from-url https://github.com/wenxi96/model-regression-eval/archive/refs/heads/main.zip \
  --target auto \
  --project-root . \
  --dry-run
```

确认预览结果后去掉 `--dry-run` 执行真实安装。`--target auto` 可替换为明确目标，例如 `--target codex`、`--target claude`、`--target cursor` 或 `--target web-manual`。

### Generate bootstrap scripts

```bash
python -m model_regression_eval.cli skill bootstrap \
  --platform auto \
  --source-url https://github.com/wenxi96/model-regression-eval/archive/refs/heads/main.zip \
  --out dist/install.sh

python -m model_regression_eval.cli skill bootstrap \
  --platform windows \
  --source-url https://github.com/wenxi96/model-regression-eval/archive/refs/heads/main.zip \
  --out dist/install.ps1
```

`--platform auto` writes a Unix shell script on macOS/Linux/WSL and a PowerShell script on native Windows. The generated scripts preserve the original project root before entering temporary download directories, so URL/Git installs target the directory where the user or agent launched the script.

```bash
python -m model_regression_eval.cli skill bootstrap --platform unix --source-url https://github.com/wenxi96/model-regression-eval/archive/refs/heads/main.zip --out dist/install.sh
```

Recommended safe usage:

```bash
curl -fsSL https://example.com/install.sh -o install.sh
bash install.sh          # dry-run by default
DRY_RUN=0 bash install.sh
```

PowerShell:

```powershell
irm https://example.com/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File install.ps1       # dry-run by default
powershell -ExecutionPolicy Bypass -File install.ps1 -Apply
```

### Generated skillpack self-installer

Every generated skillpack now contains:

```text
install.py
install.sh
install.ps1
```

After unpacking a skillpack, run:

```bash
python install.py --target auto --project-root . --dry-run
python install.py --target auto --project-root .
```

### Web products

Web-only products such as Qwen Web, GLM/Z.ai Web, Kimi, DeepSeek Web, Doubao, Yuanbao, Claude Web, and Gemini Web generally cannot install local executable skills automatically. Use `web-manual` packages instead:

```bash
python -m model_regression_eval.cli skill build --target qwen-web --out-dir dist/skillpacks
```

Then upload or copy `WEB_AGENT_INSTRUCTIONS.md`, answer the session packet in the web product, and import the answer set locally with `import-session`.
