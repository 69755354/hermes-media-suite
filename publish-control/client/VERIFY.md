# 1.2.196 实现验证记录

本轮聚焦 1.2.195 复核 P0：poller 数据根与 worker 对齐、已有正式授权时可补接入、`control_error` 客户可见、面板常驻显示飞书接入状态；同时区分复查线程的显式鉴权失败与瞬时连接失败。实现与 Linux 定向自检不代表 Windows 实机验收或独立终审。

当前源码分支：VERSION=1.2.196。MANIFEST.json、PACKAGE_BINDING.json、SHA256SUMS.txt 由打包阶段按 1.2.196 统一重算；PACKAGE_BINDING.json 按自绑定设计不计入 SHA256SUMS，其完整性由 MANIFEST 中的规范化自绑定摘要校验（该字段单独定义、非文件原始哈希）。本记录随源码分支交付，打包后清单覆盖本文件自身；任何后续改动都必须重算清单后才能再打包。未上传客户机。

面板仅在实际 PID、owner program/version 与当前包一致时保留 owner，多余 supervisor 不使合法 owner 失效；安装阶段同版本 owner 也先停止并确认退出；旧 owner 先停止并确认退出，新 VBS 在原子 guard 下重试取得锁，覆盖原有 30 秒锁保护期。未知 owner 或异常遗留 guard 仍须人工核实，不自动删除。安装统一失败出口追加原始异常类型、owner 原文与解析、锁状态和日志尾部；面板入口及桌面启动器显式加入包根。已在 Linux /tmp、非包根 cwd 下通过 runpy.run_path 注入接管超时验证弹窗证据，Windows 桌面实测仍待执行。历史 ANSI owner 按 UTF-8→mbcs/GBK→latin-1 回退并记日志；无法证明归属的服务端口占用立即失败。

进程镜像允许当前 program 或 data，仍须通过进程归属、health version、ready PID/instance 与 supervisor owner 校验；停止逻辑额外支持经过验证的历史版本路径。tasklist 调用失败或非零退出使清理状态变为不确定，警告并跳过目录删除及重命名。

report 不再使用内置 demo key；心跳与上传均要求显式非空 key（含 loopback），否则返回明确错误且不发送，离线台账和导出仍可使用。已删除 tools/report_129_sample.py（含 demo 共享密钥与管理员口令的示例脚本）。tools/demo_offline_cycle.py、tools/hot_update_drill.py、tools/hot_update_fake_agent.py、tools/make_fixture.py 为既有离线演练与测试夹具工具，不含真实凭据，按原样保留。

保留历史约束：注册表异常 fail-closed；星图点击与回读绑定同一 DOM 实例，挂载证据限定同一直接容器；旧 v1 试用不自动重签。enrollment token 为既有扫描白名单，扫描不证明服务端绑定与撤销机制。

本轮自检记录见 `review/FIX_REPORT_1.2.196.md`；历史记录见外部 FIX_REPORT_1.2.167_GPT.md。Windows WMI/VBS、Task Scheduler、双入口竞争及真实发布仍待实机验证。

## 1.2.196 相对 1.2.195 的变更
- `agent/winport/main.py`：专用单客户机默认 `single_root=True`，poller/worker 的 `--data` 等于面板与素材所在的 `<data>` 根；仅当历史 `<data>/customers/<customer_id>` 存在且 `<data>/inbox` 不存在时保留租户根。
- `agent/winport/activation.py`：已有正式授权但 `control.json` 缺失/无效时，继续执行一次 exchange 补齐接入；补接入失败不回退已有授权，并区分「授权已生效，接入已补齐」与「授权已生效，但接入未完成：原因」。
- `agent/winport/control_status.py`（新增）：原子写入 `0600` 的 `<data>/control-status.json`，记录 `connected|missing|error|disabled`、原因、时间、customer_id、device_id，不写 token。
- `agent/winport/panel.py`：授权区块常驻显示「飞书接入：已连接 / 未连接（原因）」，新增「重新获取接入配置」按钮（走一次 exchange，无激活码时提示输入）。
- `agent/winport/main.py`：复查线程只在 401/403 等显式鉴权失败时停止；连接失败/超时按 30 秒继续重试，最多 24 小时。
- `CUSTOMER_README.txt`：明确试用期内飞书发布/抓取不可用，需要激活后自动接入，并说明「飞书接入：已连接」才算开通完成。

## 1.2.176 相对 1.2.175 的变更
- `agent/winport/publish_exec.py`：pre-submit 窗口不再无条件抑制 hold。验证码、短信验证、风控、登录失效四类故障即使发生在 fill 阶段（点发布之前）也写入通道冻结，避免账号异常后队列继续撞墙；其余 fill 前置失败仍只回收账本占位、不冻结，可安全重试。异常文本与 `extra` 中的页面证据都会参与故障分类。
- `agent/winport/publish_exec.py`：fill 阶段抛出未经过 `_fail` 的账号级异常时，`run_publish` 在回收占位后按具体故障类型补写冻结，不再只依赖驱动内部调用点。
- `tests/test_presubmit_hold.py`：新增 7 条用例覆盖上述规则（登录/短信/风控/验证码冻结，普通前置失败不冻结，提交后失败仍冻结，显式 kind 优先）。
- `tools/devsign.py`：补回仓库（DEV/TEST-ONLY，不含生产私钥，按调用方传入的测试种子签名）；`tests/receipt_fixture.py`、`config/` 模板与入口脚本一并补齐，使 `static_verify.py` / `e2e_selfverify.py` 可在源码树内直接运行。

## 1.2.175 相对 1.2.174-r2 的变更
- `agent/winport/publish_exec.py`：fill 阶段的前置失败（话题回读、封面、上传等，未进入发布点击）改为回收账本 v2 占位并保持通道未冻结；`_click_failed` 仍按不确定结果处理（UNKNOWN + 冻结）。回收失败时回退为冻结，避免静默反复撞 RESERVED。
- `agent/winport/publish_exec.py`：`_apply_hold` 在 pre-submit 窗口内不写 hold。
- `agent/winport/cli.py`：外层通用异常出口在 pre-submit 失败时不再写 PUBLISH_UNKNOWN。
- `tools/build_bundle.py`：重建时把包版本同步写进 `PACKAGE_BINDING.json`（此前停留在旧版本号）。
- 其余为 VERSION / MANIFEST / SHA256SUMS / PACKAGE_BINDING 重算，无新增或删除源码文件。
