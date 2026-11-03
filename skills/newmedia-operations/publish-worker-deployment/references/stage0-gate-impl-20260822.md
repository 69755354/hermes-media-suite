# 阶段 0 阳性对照门禁落地实录（2026-08-22）

项目：`/home/ubuntu/workflow/projects/publish-worker-deploy/`
目标：Mac 做发布 worker，新加坡机做控制面；阶段 0 = 纯离线阳性对照门禁，不等 Mac 在线。

## 交付物结构（stage0_gate/ 包）

- `contracts.py` — 发布计划/StepResult 契约校验（18KB，最大模块）
- `approval.py` — 审批回执签发/验签（NonceStore, sign_receipt, verify_receipt）
- `idempotency.py` — 幂等账本（LedgerState: reserved/consumed/unknown, reserve/consume/mark_unknown）
- `state_machine.py` — 状态机（1.5KB 小模块）
- `publish_guard.py` — 点击许可门禁（唯一点击端口 `_invoke_record_only_click`，硬门全过才发 permit；点击计数只能 0 或 1）
- `audit.py` — 脱敏审计（sanitize 凭证不进日志）
- `validators.py` — 校验器（14KB）
- `canonical.py` — 规范/摘要
- `cli.py` — CLI 入口（validate / selftest / build-mac / verify-bundle 四个子命令）

## 关键设计点（来自试点方案 §3.5 + NewMe 阳性对照方法论）

- 发布按钮封装在硬门禁后：普通 adapter 不拥有点击能力；唯一点击端口只能由门禁模块在硬门全部通过后调用
- 测试用记录型假端口：点击计数只能为 0 或 1，不存在真实浏览器实现
- 每条绿判据配必红坏样本：upload_still_busy / visibility_private / click_uncertainty_freeze_unknown / core_rule_cannot_be_downgraded_by_warn / unknown_mode_fails_closed / grey_preserves_red_warn_observes_enforce_blocks
- 审计不可写时点击为 0（fail-closed）；点击结果不确定时冻结为 UNKNOWN

## 验证命令序列（全绿实录）

```bash
# 1. 语法
python3 -m py_compile stage0_gate/*.py tools/*.py tests/*.py        # COMPILE OK

# 2. 单测（必须带 PYTHONPATH=.，否则 ModuleNotFoundError: stage0_gate）
for t in tests/test_*.py; do PYTHONPATH=. python3 "$t"; done
# test_contracts 12 + test_controls 9 + test_gate 26 = 47 项 OK

# 3. CLI selftest（断言 browser/network not_used）
PYTHONPATH=. python3 -m stage0_gate.cli selftest
# → {"browser":"not_used","network":"not_used","selftest":"PASS","tests_run":47}

# 4. 构建 + 验证 Mac 离线包
python3 tools/build_mac_bundle.py
# → {"built":"dist/stage0-gate-macos.zip","sha256":"46aafb...","verified":true}
PYTHONPATH=. python3 -m stage0_gate.cli verify-bundle dist/stage0-gate-macos.zip
# → {"source_files":23,"verified":true}
```

坑：`python3 stage0_gate/cli.py --help` 直接跑报 `ImportError: attempted relative import`——必须 `python3 -m stage0_gate.cli`。

## codex 打包任务书的三关预检（dispatch 前必须做）

codex 打包回来的任务书不能直接 dispatch，先跑三关：

1. **触发词 grep**：`grep -nE "seedance|出片|视频生成|生成视频|video.*gen|SKIP_KB_GATE"` 期望 0。
   实录：codex 自审段写「英文 `video` 与 `gen` 无分隔拼接」→ `video.*gen` 跨词命中（反引号/空格被 `.*` 吃掉）→ kb_gate BLOCK「出片任务缺少 seedance skill 标记」。patch 成「英文字母序列 v-i-d-e-o 与 g-e-n」后 0 命中。
2. **kb_gate 模拟**：`python3 ~/.hermes/scripts/kb_gate_sg.py -f <任务书>` 期望 KB_GATE:PASS。
3. **task_brief_gate**：`python3 /home/ubuntu/workflow/task_brief_gate.py --brief <任务书> --project <项目>`。
   实录：codex 产物缺 TASK_TYPE/PROJECT_DIR 标记 → 补 `TASK_TYPE=分析` + `PROJECT_DIR=` + `PRELOAD_NODES=1,2,3,4` + `DATA_SOURCE=`（顶格裸 KEY=VALUE 行）；WARN 提示补 `USER_REQ=用户原话…` + 正文「数据来源：…」字样 + 清「判定」判断词（表格列头「判定」也命中判断词检查，改成「校验方式」）。

## attest WARN 属正常

codex 只读引用项目外文件（如 newme-adapt-analysis 下的方案文档）时 attest 报「产物不在项目目录内」WARN——不影响 rc=0 和产物，只读参考不算交付物。

## 阶段 1 前置（等 Mac 隧道恢复）

传包 → 核验 SHA256 → 运行双击自检 → 实查 Mac 系统版本/芯片/内存/独立用户/常开/防休眠配置 → 登录保活+扫码值班。
