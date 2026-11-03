# 广州机火锅店演示路径（12 步）完整细节

来源：广州机 `/home/ubuntu/ai-video-factory/README.md` + `app/orchestrator.py` + `app/gates.py` 代码核对，2026-08-18。

## 完整 12 步

1. 客户输入天行者分配的数值客户编号；**余额大于 0 才能进入**并新建短视频项目。
2. 分别上传菜单、价目、门头、菜品、服务过程五类证据素材，可另传一条授权 MP4 用于免费合成。
3. 内部登录，在 **O1 对项目授权执行「先检查依据」**，取得 **5 分钟短效 token** 后再放行。
4. 通过内部接口导入**不少于 3 条已核验洞察**，然后逐步执行；增长打法和三版文案由本机 `codex exec` 真实生成。
5. **冻结门店事实**；文案进入全文件红线扫描及**事实、合规、授权、可执行四硬门**。
6. 客户在 **C1** 明确选择「确认 / 修改 / 暂停」，**没有超时自动通过**。
7. 生成 **8 列分镜**并准备素材，流程到 `MEDIA_PREP` 后停在**付费审批边界**。
8. 内部选择已授权 MP4 执行合成；成片成功后调用广州 `/tasks/{id}/settle` **扣 750 积分，失败不扣**。
9. 客户在 **C2** 明确确认成片。
10. **交付门**同时断言广州任务已结算、授权链、C2、正式产物和无 MOCK，随后预生成 ZIP。
11. 客户下载 ZIP 前**再次调用广州交付门禁**；通过后才返回文件。
12. **O9** 查看队列、孤儿任务、待审核、磁盘与备份状态；审计接口验证哈希链。

## 代码锚点

- `app/orchestrator.py` 状态机节点：`MEDIA_PREP`（SIGNED_OFF）、`MEDIA_PRODUCTION`（RUNNING / INTERNAL_REVIEW / FAILED_RETRYABLE）、等待点 `WAITING_C1` / `WAITING_C2`、`DELIVERY_PACKAGE`（查 `G_DELIVERY_READY`）。
- 确认对象：C1 target = `A_TOPIC_FINAL / A_COPY_FINAL / A_PLATFORM_COPY_PACK`；C2 target = `A_VIDEO_MASTER / A_COVER / A_SUBTITLES / A_TECH_QC`。
- 预览：`previews/C2_low.mp4`（低带宽预览，进 C2 前生成并审计）。
- `app/gates.py`：`G_PROJECT_AUTHORIZED`、`G_COPY_READY`（`_copy_hard_gate` 输出 `COPY_HARD_GATES_ALLOWED:已扫 N 个文件；事实/合规/授权/可执行已分别检查`）、`G_DELIVERY_READY`；门禁清单 `build_gate_manifest` 含上游门状态；人工复核 `MANUAL_REVIEW_REQUIRED:<gate_id>:branch_quality_review`（rc=3）。
- 回退矩阵：`shot_only_change → MEDIA_PREP`、`tech_issue → MEDIA_PRODUCTION`；`COPY_PACKAGE` 及之前改文案会 invalidate `["C1","C2"]`，之后只 invalidate `["C2"]`。
- billing：`/home/ubuntu/billing-system/`（app.py + invariants.py + ARCHITECTURE.md），billing.service 常驻；工厂经 `XG_FACTORY_BILLING_BASE_URL=http://127.0.0.1:18080`（2222 反隧 + 本地转发）。
- 验收脚本：`scripts/accept_p1_hotpot.py`（完整：真实 codex exec + ffmpeg；`--fast`：确定性测试适配器 + ffmpeg 真合成）。

## 语义工作流主链（19 节点）

`PROJECT_CHARTER → BUSINESS_DIAGNOSIS → MARKET_INSIGHT/OFFER_PATH → GROWTH_STRATEGY → OPERATING_INFRA/CONTENT_CALENDAR → TOPIC_EXPERIMENT → COPY_PACKAGE → CREATIVE_BLUEPRINT → MEDIA_PREP → MEDIA_PRODUCTION → DELIVERY_PACKAGE → PUBLISH_OPERATE → LEAD_OPERATION → CONVERSION_OPERATION → RETENTION_OPERATION → WEEKLY_REVIEW → MONTHLY_CLOSE`

（两机统一 AGENTS.md 合并草稿，来源 workflow/AGENTS.md；待广州 skill 同步完成才转唯一源。）
