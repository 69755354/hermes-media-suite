# 门禁/切模式决策：验证「结构性不可达」的方法（2026-08-22 claude 判断实例）

> 场景：用户问「改完是不是广州所有东西都要我批」「切啊」，Hermes 需要判断 execute-api 门禁能不能切硬模式。
> claude 判断发现三个决定性事实，全部靠只读源码 + 仿真，不靠猜。

## 核心方法：判定「门禁是否结构性不可达 rc=0」

切硬模式前最危险的不是「业务没走完流程被拦」，而是**门禁本身在当前代码下永远不可能通过**——这时候切硬 = 全量关停，不是按规则拦。

### 三步验证（全部只读，零付费）

1. **读 registry 的 implemented/manual 标记**
   ```yaml
   G_RENDER_READY:
     checks:
       - {id: three_view_structure, implemented: true}
       - {id: render_readiness, implemented: false, manual: true}   # ← 关键
   ```
2. **读 gate check() 尾部对 manual 的处理**
   ```python
   if manual:
       print(f"MANUAL_REVIEW_REQUIRED:{gate_id}:...")
       return 3          # ← manual=true 的闸永远走这里
   record_gate(..., "ALLOWED", ...)
   return 0              # ← 对 manual 闸不可达
   ```
3. **只读仿真**：直接调 `manual_checks`/`has_implemented_checks`/`entry_route` 打全 19 个门的 rc 分布。实例结果：19 门里 17 个 rc=3-only，只有 2 个可达 rc=0。

**结论：** 即使把所有上游哈希补齐补对，`rc=0` 对 manual 闸不可达。执行副本 `if r.returncode != 0` 把 rc=3 当拦截 → 硬模式拦截率 100%。

## 双 100% 阻断：闸1 也要单独验

不能只查闸2。实例：闸1（confirm_gate）也 100% 拦——`find / -name CONFIRM.json` 全机只有测试残留，所有真实项目都没有确认状态文件。**闸链是串联的，先过的闸先拦，验证要逐个跑**（`confirm_gate.py check <proj> node12_render` 实跑 rc=2）。

## 副本分叉陷阱：执行副本 vs 新副本

同一命令在广州机有多个副本（`~/.hermes/scripts/workflow_gate.py` 执行用 vs `workflow/scripts/workflow_gate.py` 新版）：
- MD5 不同、子命令不同（执行副本无 approve）、状态文件位置不同（外置+HMAC vs 项目内无签名）
- **用新副本 approve 批门，执行副本看不见 = 白批**
- 排查：`md5sum` 对比 + 实跑 `approve` 看是否「未知命令」+ 读 state_path 代码确认读哪个文件

## 影子演练：切硬前必做的只读验证

不动 drop-in、不改代码、不出片：在硬模式环境变量下只读跑一遍四闸，把每个闸的真实 rc 和完整输出打成表。
- 价值：坐实「双 100% 阻断」推断（从源码推出的是推断，端到端实跑才是事实）
- 顺序铁律：先影子演练出 rc 表，再碰 drop-in/改代码
- 实例结果：闸0 EXISTS / 闸1 rc=2 未确认 / 闸2 rc=2 上游未批（批了也 rc=3 不可达）/ 闸3 rc=0 空转 / permission_gate rc=0 unlimited

## 相关结论（本实例，可复用于类似判断）

- 软模式（HERMES_GATE_SOFT=1）下所有闸转 SOFT_PASS 审计放行 = 门形同虚设，但审计日志是排查绕过口的最好证据（39 条 SOFT_PASS 全同因 = 唯一绕过口、唯一客户）
- 出片记账（costs.db）是「未批准扣费」的铁证来源：v11-v15 连出 6 次全 charged，无一次经过确认闸
- 权限 unlimited + 软模式三闸开 = 「管不住」的结构性根因，不是执行器不听话
- 修闸对自动化影响面要单独评估：实例中只伤小鹿直调（video_talk 不带 project_dir），/execute 端点零流量无影响
