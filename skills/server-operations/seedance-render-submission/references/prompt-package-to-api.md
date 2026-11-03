# PROMPT_PACKAGE → API 可提交文本（2026-08-23 火龙实测）

## 为什么不能直接提交

分镜阶段的 PROMPT_PACKAGE（四层结构文档）是**给人看的文档**，直接塞给 API 会污染 prompt：
- markdown 标题（`### 第一层` 等）是排版符号，模型当噪音
- `@图N=/home/...绝对路径` 会把路径当文字喂给模型；路径应走 `reference_images` 参数
- 文档校验/注释行（如「台词校验：9 个句级口播子镜…」「物理段列示合计 73 字…」）是给质检看的，进 prompt 会干扰台词生成
- 参考图路径重复描述（人物外貌/服装/场景）违反 prompt 简化铁律——参考图已锁这些信息

## 提交前清洗清单

1. 去 markdown 标题（`### 第一层` 等），保留四层正文
2. `@图N=/绝对路径` 改 `@图N`（路径走 reference_images）
3. 去掉校验/注释行（台词校验、字数标注、物理段合计）
4. 台词保留英文双引号，去反引号/列表符号
5. 参考图顺序固定：人物在前、场景在后、闪屏/素材最后，与 @图1/@图2/@图3 对应

## 长度实测

- API 无硬性限制：本地 helper（execute_api.py 1889）拿到 prompt 直接透传 ARK，不截断
- 之前跑通的长 prompt ~1300 字符可出片
- 但第三方实测（CSDN）：提示词超 80 字符后语义解析准确率断崖下跌（76%→39%）
- 结论：API 不拒绝长文，但指令密度太高模型抓不住重点；参考图已锁内容不重复描写，每镜尽量压短

## 出片提交接口（/seedance-exact/job，SG 1889）

必填字段：
- `prompt`：清洗后的提示词文本
- `duration`：4-15 整数秒（2.033s 之类短镜需生成 4s 冗余再裁切）
- `reference_images`：项目内绝对路径列表（须在 projects 目录内，顺序与 @图 对应）
- `output_path`：projects 目录内 .mp4
- `customer_id`：权限闸，unlimited 才放行（basic 拦截）
- `project_dir`：项目目录（gate 校验出片确认用）

## 出片确认闸坑（2026-08-23 R7 单向棘轮）

- confirm_gate 的 node12_render 确认点 8/23 R7 起绑定产物哈希：**一旦确认记录绑定过产物，check 必须提供同一产物，否则拦截**
- 旧确认（R7 前、无 artifact_sha）会被拦：`旧确认未绑定产物；当前已启用产物校验，需重新确认`
- 现象：手动 `confirm_gate.py check <proj> node12_render` 不带产物能过（宽限期），但出片接口 `_gate_chain` 会带产物调用 → 被拦。**必须重新 confirm 绑定产物**
- 修复：
  ```
  python3 /opt/hermes/gates/confirm_gate.py confirm <项目目录> node12_render "<用户出片原话>" <产物绝对路径>
  ```
- 产物候选优先级（execute_api.py `_confirm_artifact`）：
  1. `guard/confirm_artifact`（显式指针，内容为产物路径）
  2. `staging/SHOT_REF.yaml`
  3. `artifacts/A_STORYBOARD.md`
  4. `guard/shot_verify.json`

## 交付纪律（2026-08-23 天行者纠正）

分镜交付只出**主文件**（分镜脚本），素材映射合并进脚本素材引用段；自审/实施报告等流程文件归档不端给用户。用户原话：「你出个脚本分镜还要写这么多报告的吗」。

## 调试坑

- `/job/status` 轮询长脚本容易误报 404；直接 `curl -s -X POST http://127.0.0.1:1889/job/status -d '{"job_id":"..."}'` 看真实状态
- job 可能秒回 blocked（gate 拦），轮询脚本看不到就误以为还在生成——先查 job 真实 status 再判断
