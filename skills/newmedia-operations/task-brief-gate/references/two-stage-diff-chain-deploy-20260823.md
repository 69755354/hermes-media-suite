# 两段 diff 串联部署 + 跨机隧道部署 + 零花费探针（2026-08-23 C2 实录）

场景：生产在基线（C 从未部署），候选是 C2（C→C2 迭代修复版）。部署不能直接用 C2 完整文件覆盖
（REPAIR 纪律：生产部署必须应用 diff），也不能只应用 C.diff（那是 C 版不是 C2）。解法：**两段 diff
串联**——先 C.diff（基线→C）再 C-to-C2.diff（C→C2），每段验证 MD5。

## 0. 部署前事实核对（先摸清，再动手）

```bash
# 生产基线必须 = C2 的输入基线，否则部署目标错
md5sum /home/ubuntu/workflow/hermes_task_dispatch.py /home/ubuntu/.hermes/scripts/codex_exec_gated.sh
# 本实例：872fcf31（dispatcher 基线）/ 1a6f21cb（gate 基线）——与 REPAIR/复审记录一致才继续
# 广州侧：ssh -p 2222 ubuntu@127.0.0.1 "md5sum /home/ubuntu/.hermes/scripts/codex_remote.sh" → f592f5e9
```

C 候选 MD5、C2 候选 MD5 都先 `md5sum` 出来做门禁值（不要抄方案文档自述，用实际文件算）。

## 1. 临时副本演练（必做，30 秒排掉白部署）

diff 头是**裸文件名**（`--- hermes_task_dispatch.py`），临时副本文件名必须匹配裸名：

```bash
T=$(mktemp -d /tmp/c2drill.XXXXXX)
cp /home/ubuntu/workflow/hermes_task_dispatch.py "$T/hermes_task_dispatch.py"
cp /home/ubuntu/.hermes/scripts/codex_exec_gated.sh "$T/codex_exec_gated.sh"
cd "$T"
git apply --check -p0 <C.diff> && git apply -p0 <C.diff>   # 基线→C
md5sum hermes_task_dispatch.py                             # 期望 = C 候选 MD5
git apply --check -p0 <C-to-C2.diff> && git apply -p0 <C-to-C2.diff>  # C→C2
md5sum hermes_task_dispatch.py                             # 期望 = C2 候选 MD5
cmp hermes_task_dispatch.py <C2 完整文件>                  # 逐字节一致才算过
python3 -c 'compile(...)' / bash -n                        # 语法检查
```

演练全过 → 正式部署照同一顺序跑（先备份 .bak-c2-before-<TS> 再 apply）。

## 2. SG 正式部署 + 无付费探针（不调模型）

部署后探针（零花费，验证闸行为）：

1. `TASK_GATE_ENABLED=1 gate "probe" /tmp` → rc=2 BLOCKED（默认强制仍有效）
2. `TASK_GATE_ENABLED=0 gate "probe" /tmp`（不带 SKIP_REASON）→ rc=2 提示 SKIP_REASON（关闸必须声明原因）
3. dispatcher 零字节 prompt → rc=2 `codex prompt 来源缺失或字节数为 0`（签票前拦截，证明修复非空转）

三个探针都过再谈 GZ。

## 3. GZ 隧道部署（关键坑：远程目录要先建）

```bash
TS=$(date +%Y%m%d_%H%M%S)
REMOTE_TMP="/tmp/c2-gz-deploy-${TS}"
# ① 先 SSH 建远程目录——scp 目标目录不存在会报 "dest open: No such file or directory"，
#    本地 mkdir -p 建的是本地目录，没用（本实例第一次就这么失败的）
ssh -p 2222 ubuntu@127.0.0.1 "mkdir -p $REMOTE_TMP"
# ② 传 diff
scp -P 2222 <C.diff> ubuntu@127.0.0.1:$REMOTE_TMP/c.diff
scp -P 2222 <C-to-C2.diff> ubuntu@127.0.0.1:$REMOTE_TMP/c2.diff
# ③ 远程执行：基线核对 → 备份 → 串联 apply → bash -n → MD5 复核 → 关键结构 grep
# ④ 清理远程临时目录
ssh -p 2222 ubuntu@127.0.0.1 "rm -rf $REMOTE_TMP"
```

GZ 静态探针（不发模型任务）：
- `bash -n codex_remote.sh` OK
- A 豁免残留 grep = 0（`SKIP_REASON=gz_brief_gate_passed_pending_task_token`）
- `REMOTE_CMD=.*TASK_GATE_ENABLED=0` 硬编码 = 0
- 协议握手逻辑在位（`--protocol-version` 查询行存在）
- 关键结构保留：kb_gate_hard / gz_brief_gate_check / record_producer 计数不为 0

## 4. F-10 配套部署（hash-verify + md5 记录 + 测试落位）

- hash-verify.sh cp 替换后会**丢执行位**（cp 保留原文件权限，新文件无 x）→ `chmod 755` 再跑，否则 Permission denied
- md5 记录用**部署后真实值**生成（部署后 `md5sum` 生产文件），不是直接抄候选值
- 新测试落位 `/home/ubuntu/workflow/tests/` 后 `py_compile` + unittest 跑一遍
- 全量验证：跑 hash-verify.sh 17 条全 OK（含新增两条）才算 F-10 闭环

## 5. 部署记录

写 `staging/sg-deploy-<日期>/DEPLOY_RECORD_C2.md`：每文件部署前/后 MD5、备份路径、探针结果、
遗留项（F-08 用户接受风险 / GZ 跨机哈希剩余 / F-07/F-09/F-11 另案）。

## 5.5 广州 hash-verify 旧版补齐（用户「两边的一起弄完」定案）

SG 侧 F-10 闭环只覆盖 SG 本机；广州侧 hash-verify.sh 可能还是**旧版**（8 条 FILES 清单、注释写
「新加坡机版」= 复制时没改机名），hash 记录目录也可能没有 codex_remote.sh.md5。补齐动作：
① Hermes 先 `ssh -p 2222 ubuntu@127.0.0.1 "md5sum /home/ubuntu/.hermes/scripts/hash-verify.sh"`
拉真实生产版进项目 inputs/（MD5 门禁基线）——codex 容器改不了广州文件也读不到宿主目录，必须
先拉进项目；② 派 codex 打包任务书 → 实施产出候选（FILES 加 codex_remote.sh + 修正机名注释 +
生成 .md5 记录候选 + 核对清单其他条目记录文件是否齐全）；③ Hermes SSH 部署到广州 + 复核。
注意广州 hash-verify 是独立文件（不是软链到 SG），两机清单各自维护；SG 清单管不到广州文件是
架构事实，登记为跨机剩余风险即可。

## 铁律

- 生产部署必须 diff 应用，不用完整文件覆盖（REPAIR 纪律）
- 每段 apply 后 MD5 门禁，不符即停（BLOCKED + 备份可回滚）
- 探针全部零花费，不调真实模型/付费 API
- 备份先做：`.bak-c2-before-<TS>`，回滚路径明确
