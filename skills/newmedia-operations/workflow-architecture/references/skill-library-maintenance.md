# Skills 体系维护实录（2026-08-11/12）

> 触发：技能库整理、合并重复 skill、删过时、加沉淀机制、验证 skill 引用
> 背景：`.hermes/skills/` 125 个 skill（newmedia-operations 39 个），Claude 审出大量重复/过时

## 一、重复的根因 = 沉淀机制（不是懒）

每次用户纠正都**新建**一个 skill 记录教训 → 同一条知识带 3 个日期版本共存。
**真正修复**：`hermes-agent-skill-authoring/SKILL.md` 加第 0 步强制规则——
「A hit means update, never create」——沉淀新教训前先 grep 现有 skill，命中则改不新建。
**只合并文件不改机制，三个月后重复会长回来。**

## 二、合并重复组（2026-08-11 codex 实施，已完成）

| 组 | 合并成 | 内容去向 |
|:--|:--|:--|
| content-review-gate + content-production-quality-gates + copywriting-quality-gates | content-review-gate | 主 SKILL.md 5.4KB + references/（knowledge-and-humanization / production-material-lessons / scoring-and-judge） |
| media-data-review + content-data-review + wechat-article-data-review + content-data-discipline | content-data-review | references/ 保留 |
| 视频簇（oral-video-production/video-assembly/video-visual-lessons/ai-video-post-editing/video-prompt-reverse/short-video-analysis） | video-production 定位声明 | 各自内容进 references/ |
| hermes-to-n8n-webhook（已废弃） | 归档删除 | 9 文件核对一致 |

结果：125 → 约 100，省 ~1800 行，强制加载链八件套 → 三件套。

## 三、合并踩坑

1. **别信 skill 自我声明**：`video-production` 自称「合并单一入口」，但 AGENTS.md 仍同时强制加载它和被它宣称吸收的文件，且 381 行不可能覆盖 7,317 行——**按实际加载链+关键词交叉计数验证，不信文件里的定位声明**。
2. **归档要留原文可核对**：n8n 归档做对了（9 文件核对一致）；另外 11 个被合并 skill 原文全盘零命中（连 backups 都没有）→ Claude 审核时「没丢内容」只能靠抽样，无法逐条比对。**合并前先留原文副本。**
3. **合并时新建而非 patch 会制造分叉副本**：李玟案例出现两份（3868/3452 字节内容不同、互不引用）——合并用 patch，不用新建。
4. **审核结论先 grep 全库验证**：Claude 说「合规根因词没进合并版」→ grep 全库一查，三个词在 content-redlines 一行里——误报（报告只查了它认定的范围）。李玟案例两份副本 grep 确认是真问题 → 才删（保留方法论样板 liwen-case-demo.md，删具体案例数据，并修复 2 处残留引用）。

## 四、全量 skill 引用验证方法（2026-08-12 codex 验证）

四类引用都要验证，每项查「引用 vs 实际」：
1. **AGENTS.md 的 @ 引用**：提取全部 @skill-name → `.hermes/skills/` 存在（含分类目录搜索）+ frontmatter name 匹配（防同名不同名）+ codex 能读到（`.codex/skills/` 软链存在）
2. **SOUL.md 引用**：如 `huoshan_skill` 不存在（实际 `huoshan`）= 命名漂移
3. **SPEC/REGISTRY**：无 machine-readable skill 依赖字段 = 无法机器校验五件套已加载
4. **代码硬编码路径**：`scripts/*.py` 里 skill 路径必须存在且 frontmatter 匹配

**软链 vs 复制件的判定**：软链 = 单一事实源 OK；实体复制目录即使当前哈希相同也记为漂移（后续不会自动同步）。
**verify 脚本盲区**：`verify_codex_skill_links.py` 只做正向校验（引用的存在），**检测不到 Codex 侧未被引用的陈旧入口**（反向）——复制件分叉就是从盲区漏的。

## 五、本次验证发现（2026-08-12，已全部修复）

- SOUL.md `huoshan_skill` → 已改 `huoshan`（grep 0 残留）
- Codex 32 个 skill 仅 8 个软链，24 个实体复制目录，其中 4 个已内容分叉 → **已全部改软链：32/32 软链、0 实体目录、0 断链**（分叉先以 Hermes 单一源为准合并再链）
- 3 个 skill 目录名与 frontmatter name 不一致 → 已统一
- `codex_preload_manifest.py` PRELOAD_REQUIRED 未覆盖 content-data-review/content-review-gate/video-production → 已补全（五件套预载）
- Git：`6600d70` 全量软链验证 + `6f35a9f` 完整五件套预载

## 六、按模板归档踩坑与资源（2026-09-02 用户指出结构性缺口）

**问题：** 每个模板（探店/剧情/口播/复刻/小红书图文/长篇写作等）有独立 SKILL.md，但踩过的坑和用过的资源散落在三处：
1. Hermes 记忆条目（零散、按时间排列、不按模板分类）
2. `wiki/cases/` 项目复盘（按项目存，不按模板分类）
3. 各 skill 的 references/ 子文件（有但不全）

**后果：** 做同样模板时不会自动引用到之前同类项目的踩坑——每次可能重踩同样的坑。

**正确做法（待落地）：**
- 每个模板的 skill 目录下建 `references/template-pitfalls.md`，按模板类型归档踩坑和资源清单
- 项目复盘写到 `wiki/cases/` 后，把该项目的踩坑**同步摘要**到对应模板 skill 的 `references/template-pitfalls.md`
- 开工前除了读 SKILL.md，还读 `references/template-pitfalls.md` 获取历史教训
- 记忆只存指针（「探店模板踩坑 → huoshan/references/template-pitfalls.md」），不存具体内容

**判断标准：** 用户问「这个模板踩过什么坑」时，能直接从该模板 skill 的 references 里查到，不用翻记忆和散落的项目复盘。

## 七、跨机代码同步到 GitHub（2026-08-12 广州机后端推送实测）

场景：后端在**广州机**（billing-system，13 commits），要推 GitHub（新加坡机可访问 GitHub、广州机也通 `curl github.com`=200）。

**流程（避免经新加坡中转）：**
```bash
# 1. 新加坡机建私有仓库（GH_TOKEN 环境变量绕过 gh auth login 的 read:org 要求）
export GH_TOKEN="ghp_..."
gh repo create <name> --private --description "..."   # 返回 https://github.com/<user>/<name>

# 2. 广州机直接 push（它能访问 GitHub；token 临时拼进 URL）
ssh -p 2222 ubuntu@127.0.0.1 "cd <repo> && git remote add origin https://<user>:<TOKEN>@github.com/<user>/<name>.git && git push -u origin master"

# 3. ⚠️ 立即清除 remote 里的 token（安全）
ssh -p 2222 ubuntu@127.0.0.1 "cd <repo> && git remote set-url origin https://github.com/<user>/<name>.git"
```
**教训：** token 进 remote URL 推送后必须立刻 strip；用 GH_TOKEN 环境变量可以绕过 `gh auth login` 的 read:org 校验（token 缺该 scope 时报 `error validating token: missing required scope 'read:org'`，但 repo 权限够用）。scp -r 拉 git 仓库经常只拉到 .git 目录（文件不齐）——**推送优先在源机做，别拉副本再推**。
