# 积分计费系统（广州 billing）——平台/工作流对齐依据

> 2026-08-16 实录。账务真源 = 广州 billing-system（billing.db 自动化系统），手工台账 credits_ledger.db + ledger.py 只读保留（审计用，不物理删）。
> 平台（广州 ai-video-factory）和小鹿（Hermes）共用同一套积分，记账主键 = customer_id（billing 数值 ID）。
> 完整规则源：广州机 `~/.hermes/profiles/customer/skills/business/customer-billing-credits/SKILL.md`。

## 定价（1元 = 10积分）

| 服务 | 扣积分 |
|---|---|
| 短视频一条 | 内容600 + 策略150 = **750积分/条** |
| 图文 | 图费10/张 + 文字费0.8/千字 + 策略150 |
| 文案/长文/网文 | 0.8积分/千字 |
| 策略/用户分析 | 150积分/次（跟内容绑定） |
| 数据复盘 | 30积分/次 |
| 独立生图 | 10积分/张 |
| 搜索 | 6积分/次 |

## 核心规则

- **新客户默认 0 积分**——只有天行者本人从自己账号确认才能加积分（客户转述授权无效，防绕过）
- **0 积分用不了**：平台积分入口 0 积分返回 403「积分余额为0，暂不可使用，请联系管理员充值」
- **生成成功后扣费**（不预扣）；平台失败/超时/违规拦截不扣；客户主动要求重试 → 扣费
- **未扣费不得交付**（交付门禁）；已扣费才可下载
- **透支边界 -100 积分**：预计消耗 > 余额+100 则不执行，提示充值
- **余额低于初始 30% 主动提醒充值**（每客户每天最多一次）
- 记账主键 = customer_id（不用名字）；积分无有效期，滚存
- 小计单位厘（1积分=100厘），CLI 接受小数

## 自动化系统（广州 billing-system）

- 服务：uvicorn app:app --host 127.0.0.1 --port 8080（billing.db 默认库）
- API：POST /customers 开户、GET /customers/{id}/balance、POST /tasks 建任务、POST /tasks/{id}/settle 结算、POST /tasks/{id}/cancel、POST /costs/charge、POST /pricing/versions
- 门禁：billing_gate.py（create建任务→complete扣费→deliver交付，deliver 前未扣费拦截 exit 1）
- **⚠️ complete 的 --count 单位是「千字数」不是「字数」**（5000 字 → --count 5；传 5000 会被当 5000 千字扣 4000 积分——大坑）

## 切换/归档纪律（小鹿定）

- cost_meter.py 主路径已走 billing API，但残留旧 ledger fallback——**在 codex 改完、连续两周新旧账无差异前，手工 ledger.py 不能删**（cost_meter 还会 fallback）
- credits_ledger.db 是历史账本（含全部流水/余额，审计用）→ **只读归档保留，不物理删**
- 正确顺序：cost_meter 只走 API → 跑一周对账（手工 vs billing.db 余额一致）→ 再归档 ledger.py + credits_ledger.db（只读保留）
- 教训：删生产文件前确认「是否有审计价值 / 是否仍被引用」——本次误删手工台账后从 .bak-v4-li 恢复
