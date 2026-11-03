# 视频团队系统（video_team）

团长 = Hermes，只调度不生产。四个执行单位：视频组、审核组、发布组、数据组。
一条片子一个任务号（V001…），从选题走到复盘，所有动作落 SQLite 台账。

## 一、分层

```
teamctl（唯一入口：团长/组员都用它）
   │
   ├── engine.py    状态机 + 门禁（唯一写权限）
   ├── adapters.py  执行器适配（codex / codex_review / publish_gate / data_tools / stub）
   ├── db.py        SQLite 台账（tasks/stages/artifacts/calls/events）
   └── daemon        teamctl daemon 子命令：租约到期判定、自动派活（默认关闭）
```

配置：`pipeline.json`（阶段/依赖/验收标准/是否付费）、`roles.json`（角色）、`config.json`（执行器/租约/自动派活）。

## 二、9 阶段状态机

选题 → 文案 → 分镜 → 生成 → 合成 → 合规 → 发布 → 取数 → 复盘

状态：`pending → ready → working → done`；异常 `blocked`；退单 = `ready` + assignee=leader。

硬规则（代码里，不在提示词里）：
1. 上游全部 done，下游才 ready。
2. 同一片子同时只能一个阶段 working（单飞）。
3. `done` 必须登记真实产出物：路径存在 + sha256 + 大小。
4. 付费阶段（生成/合成）没登记调用次数不许开工；超预算直接拦。
5. 团长（leader）不能被指派承接任何阶段。
6. 卡点必须写原因 + 下一处理者；没解除不能开工。
7. 租约 900 秒，心跳不续 → 自动 blocked。
8. 退单不清上游产出物，只把承接人交回团长改派。
9. **任务书闸**：任务书必须由 `teamctl brief/dispatch` 生成并登记 sha256，文件对不上不许开工。
10. **验收闸**：合规必须有 `VERDICT: PASS`；发布必须有 `CONFIRMED` 回读证据；取数必须是表格。
11. **人工闸**：发布阶段必须先 `teamctl approve <id> PUBLISH`，没放行开不了工。
12. **审核独立**：合规阶段只能派给审核组，不能派给视频组。

## 三、派活协议

```
teamctl add "片名" --batch B01 --account 漫半拍 --budget 6
teamctl next                          # 团长看哪些阶段可开工
teamctl brief V001 [--stage TOPIC]    # 生成任务书并登记
teamctl dispatch V001 --stage TOPIC   # 派活：brief→start→执行器→验收→done；失败自动 blocked
teamctl run V001                      # 从当前阶段一路往前推，遇付费/人工闸自动停
teamctl approve V001 PUBLISH          # 人工放行发布（一次放行该片该阶段）
teamctl status V001 | artifacts V001 | events V001
teamctl reject/assign/block/unblock/calls
```

## 四、组与执行器（现状）

| 组 | 承接阶段 | 执行器 | 现状 |
|---|---|---|---|
| 视频组 | 选题/文案/分镜/生成/合成 | `codex`（codex exec，DeepSeek 壳） | 已接通；实测产出选题单 |
| 审核组 | 合规 | `codex_review`（另起一次 Codex，只判不写） | 已接通；无 VERDICT: PASS 进不了发布 |
| 发布组 | 发布 | `publish_gate`（出待发工单 → 人工 approve → 执行 → 回读） | 人工闸；工单 `handoffs/PUB_<tid>.md` |
| 数据组 | 取数/复盘 | `data_tools`（`tools/collect_report.py` → 20 列作品表） | 已接通；客户机离线时明确报错，不假成功 |
| 联调 | 任意 | `stub` / `stub_ok` | 只造占位/能过闸的假文件，不代表真跑通 |

任何执行器给不出 `OUTPUT:` 路径、产出物不存在、退出码非 0，一律记失败并 blocked，禁止假成功。

## 五、测试

`python3 -m pytest -q tests` —— 覆盖：全链跑通、任务书闸、付费未登记拦截、超预算、
审核 VERDICT 闸、发布人工闸、发布回读闸、取数表格闸、退单后必须改派、卡点不可开工、租约到期。
