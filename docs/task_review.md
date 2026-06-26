# Task Review And Adjustment Notes

日期：2026-06-23

## 方案评审结论

原调整方案方向成立：先补自动校验，再修确定缺陷，随后处理判分鲁棒性、答案偏置、题库难度和文档留痕。执行时按当前仓库状态做了两点修正：

- 不保留“允许失败”的测试。新增测试必须作为绿色守门，避免把已知失败固化为可忽略状态。
- 不机械执行“约 -42/+42”。当前题库已经吸收 20 道复杂数学/逻辑题且仍保持 300 道 active 题；继续按数量目标大规模置换会扩大 baseline 断裂面。后续扩展应基于实测区分度和专家审题再分批进入。

工具使用题暂不进入 active 主题库。原因是不同 runner 的 tool event 暴露能力差异较大，当前 reporting 已能标注 unknown，但还不足以把工具检测失败稳定解释为模型能力回归。后续若要加入工具题，应先单列实验维度或使用 quarantined 状态。

## 已执行调整

- `model_regression_eval/graders.py`
  - `exact_string` 支持 `metadata.accept`。
  - `choice` 支持 `metadata.accept`，并继续只取选项首字母判定。
  - 新增 `nand_expression`，对 LaTeX 风格与非-与非式做整体归一化比较，避免 `contains_all` 碎片误判。
  - 新增 `contains_ordered`，用于既需要容忍说明文本、又必须保持片段顺序的题目。
- `model_regression_eval/tasks.py`
  - 加载题库时校验 `metadata.accept` 必须为 `list[str]`。
- `tasks/core.zh.jsonl`
  - 总数保持 300 道 active 题。
  - 修复 `logic_truthfulness_004`，将乙的陈述改为“甲说真话”，保留唯一答案“丙”。
  - 修复 `logic_conditional_011` 的双解干扰项，答案为 `B`。
  - 明确 `instruction_sort_005` 为“按拼音首字母升序”，并增加等价标点 accept。
  - 将 `reading_table_001` 改为 `choice` grader。
  - 为 `logic_negation_008` 增加等价中文答案 accept。
  - 修复自动执行验证发现的 `code_trace_001` expected：`7 -> 12`。
  - 修复自动执行验证发现的 `code_trace_004` expected：`15 -> 19`。
  - 吸收 20 道复杂数学/逻辑题，目标 ID 全部存在。
  - 将 `logic_nand_nand_expression_001` 从 `contains_all` 改为 `nand_expression`。
  - 将 `math_raindrop_variable_mass_distance_001` 改为 `contains_ordered`，把负号与对数项绑定，避免正负号反例通过。
  - 将 `math_triangle_incircle_distance_extrema_001` 改为 `contains_ordered`，避免“最小值, 最大值”倒序答案通过。
- `tests/test_graders.py`
  - 覆盖 accept 命中、不命中和非法 metadata 加载失败。
  - 覆盖合法 NAND-NAND LaTeX 表达式、`\bar` 等价写法和碎片拼接拒绝。
  - 覆盖 `contains_ordered` 对顺序的约束。
- `tests/test_task_answers.py`
  - 自动复算可覆盖的算术、方程、单位换算和库存状态题。
  - 在隔离子进程内执行可解析的 Python 输出题，核对 stdout 与 expected。
  - 对拼接排列、座位约束、削角立方体水位、保险箱密码、字符平均解密、随机翻转吸收概率做程序化复算。
- `tests/test_task_quality.py`
  - 检查选择题答案字母分布。
  - 检查同 domain/skill 下近重复 prompt 骨架数量。
  - 检查 300 题总量与 domain 最低覆盖。
- `model_regression_eval/installer.py`
  - 修复 generic skillpack 在 `--target auto` 下忽略项目 skills 信号的问题：非 generic 的目标包仍优先使用包自身 target，generic 包会回退到项目检测。
  - 修复 WSL 向 Windows 挂载项目安装 true skill 时的 junction 目标路径问题：`/mnt/c/Users/<user>/...` 项目默认 global skill root 落到同一 Windows 用户的 `.agents/skills`，并在创建 Windows junction 时转换目标路径。
  - 修复全局 canonical skill copy 的 target 独占问题：同版本已安装时，不再因 target 不同阻断新 IDE/Agent skills 目录软链。
- `install.py`
  - 根目录安装入口默认改为 true skill 安装，并保留 `--mode rules` 兼容旧规则安装。
- `tests/test_installer.py`
  - 覆盖 generic 包 auto 安装到 Cursor skills 项目时应解析为 `cursor`。
  - 覆盖 WSL Windows 项目默认 global skill root 与 Windows junction 目标转换。
  - 覆盖根目录 `install.py --dry-run` 默认走 `install_type=skill`。
  - 覆盖同版本全局 skill copy 可被不同 target 复用并继续建立新软链。

## 20 道复杂题吸收清单

以下题目已进入 `tasks/core.zh.jsonl`：

- `math_colored_polygon_isosceles_trapezoid_001`
- `math_rectangle_five_points_small_triangles_001`
- `math_concat_permutation_001`
- `math_recurrence_integer_terms_001`
- `logic_nand_nand_expression_001`
- `math_cube_cut_water_level_001`
- `math_folding_dihedral_min_cos_001`
- `math_rational_recurrence_mod_001`
- `math_parabola_focus_conic_slope_001`
- `math_trig_product_max_sum_001`
- `logic_safe_password_001`
- `math_svm_max_margin_001`
- `math_raindrop_variable_mass_distance_001`
- `math_piecewise_function_collinear_slope_001`
- `math_tetrahedron_inner_cube_sphere_area_001`
- `math_seating_constraints_001`
- `math_triangle_incircle_distance_extrema_001`
- `math_grid_coloring_three_colors_interval_001`
- `logic_letter_average_cipher_001`
- `math_random_flip_absorption_001`

## 复审结论

当前版本可作为工程回归筛查题库使用，但结论边界如下：

- 独立评审策略已调整为：未显式指定时只使用 Codex review / Codex subagent，不再默认调用 OpenCode、Claude、Gemini、Qwen 等第三方 CLI。
- Codex review 已推动修复多轮 P2：WSL/Windows junction 目标路径、web/manual 包默认 skill 模式、安装脚本非法 mode 静默回退、两道复杂题判分过宽。最后一轮 Codex review 因 provider 额度返回 403 中断；中断前已跑过 `uv run pytest -q`（102 passed）和 `git diff --check`，并暴露了全局 skill target mismatch 的多端复用问题，已修复并补测试。
- 自动校验覆盖的是可计算题和可执行 Python 输出题；复杂几何、组合、递推、语义阅读、metacognition 和 `contains_all` 题仍需要人工或独立专家复核。
- `logic_nand_nand_expression_001`、`math_raindrop_variable_mass_distance_001`、`math_triangle_incircle_distance_extrema_001` 已退出 `contains_all` 风险面；剩余 `contains_all` 仍适合做召回型宽判，不适合单独支撑强精度结论。
- 题库组成已经变化，旧 baseline 与本版本不应直接比较。
- 未做独立专家审题、难度标定、跨模型区分度分析和偏差审计。

## 2026-06-26 真实 Codex runner 复测修复

触发证据：`codex-cli 0.142.1` 真实运行 `standard/quick` 100 题，初始因 Codex CLI 参数兼容问题全量失败；移除废弃 `-a never` 参数后，真实运行达到 92/100，`format_error=0`、`returncode_nonzero=0`、`tool_violation=0`。8 个失败样本复核后分为真实模型失败与判分口径问题。

已执行定点修复：

- `model_regression_eval/runner.py`
  - Codex command 不再传递当前 CLI 不支持的 `-a <approval>`。
  - Codex 鉴权失败且仍启用 `--ignore-user-config` 时，在 stderr 追加 `--no-ignore-user-config` 操作提示。
- `model_regression_eval/graders.py`
  - `numeric` 支持整段简单分数与 LaTeX 分数答案，例如 `10/3`、`\frac{10}{7}`。
  - `contains_all` 支持 `metadata.accept_parts`，按 expected 片段配置等价表述，避免把“不能得到唯一数值答案”这类确定性等价表达误判为缺少“信息不足”。
- `model_regression_eval/tasks.py`
  - 校验 `metadata.accept_parts` 必须为 `list[list[str] | null]`。
- `tasks/core.zh.jsonl`
  - `logic_ordering_004` 接受 `周四任务`。
  - `logic_negation_008` 接受 `少于3个通过` / `少于三个通过`。
  - `reading_state_012` 接受 `测试阻塞` / `阻塞待修复`。
  - `metacognition_insufficient_002` / `003` 增加不足信息与差值类等价片段。
- `README.md`
  - 补充 Codex CLI runner 在依赖本机登录配置时需使用 `--no-ignore-user-config`。

未放宽项：

- `candy_ambiguity_001` 仍要求同时识别歧义并给出两种解释下的数值 `21` / `29`。本次 Codex 回答只识别歧义、未给数值，保留为模型/指令失败，不作为 grader 误杀处理。

## 验收证据

本轮应使用以下命令作为完成前验证：

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q model_regression_eval
git diff --check
./.venv/bin/python -m model_regression_eval.cli run --runner mock --tasks tasks/core.zh.jsonl --profile full --depth quick --out-dir /tmp/model-regression-eval-mock --run-id mock_full_300
```
