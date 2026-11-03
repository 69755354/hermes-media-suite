# 广州 hash-verify 补齐 + 部署后整体终审配方（2026-08-23 C2 实录）

## 场景

C2 补丁（SG dispatcher/gate + GZ codex_remote）已部署两机完成，SG 侧 F-10 已闭环（hash-verify 15→17 条）。剩余两项：「两边的一起弄完」= ① GZ 侧 hash-verify 补齐（codex_remote.sh 进广州本机完整性校验清单）；② 部署后整体终审（验证生产状态与候选一致、完整性校验全过、无付费调用）。

## 第 1 步：GZ hash-verify 补齐（codex 打包 → codex 实施 → Hermes 部署）

### 1.1 摸清 GZ 现状（Hermes 只读实测，不凭记忆）

```bash
ssh -p 2222 ubuntu@127.0.0.1 "md5sum /home/ubuntu/.hermes/scripts/hash-verify.sh; ls /home/ubuntu/.hermes/guard/hashes/"
```

- GZ hash-verify.sh 往往比 SG 旧（本实例 8 条 FILES、注释还写「新加坡机版」= 拷贝残留）
- GZ hashes 目录没有目标文件记录 = 该文件裸奔，需新增
- 生产基线 cp 进项目 `inputs/<x>-prep/` 让 codex 基于真实生产版改（容器读不到宿主路径）

### 1.2 派 codex 打包补齐任务书（不自己写）

任务书要点：DATA_SOURCE 指 `inputs/.../GZ_hash-verify.production.sh` + `SG_hash-verify.F10.sh`（参考 SG 侧 F10 做法）+ `GZ_codex_remote.C2.sh`（MD5 核对）。codex 设计：codex_remote.sh 加入 FILES 清单（GZ 生产绝对路径）、列出清单内其他条目缺失记录、注释修正（广州版说明）、产出部署说明（Hermes 执行部署）。

### 1.3 部署执行（按 codex 的 DEPLOY_INSTRUCTIONS.md 逐节）

部署说明是 codex 产物，Hermes 按它执行——关键纪律：

1. **预检全过才动手**：目标路径存在、生产 hash-verify MD5 = 预期、生产 codex_remote MD5 = C2 候选、原 8 项源文件/记录全 PRESENT、目标记录确认不存在（已存在=漂移，停）
2. **先生成记录、后启用引用它的脚本**（避免缺失记录窗口）：现场 `md5sum` 生产文件 → 写临时记录 → 校验单行/首字段 32 位 hex/第二字段生产绝对路径 → 原子 rename 落位。**禁止直接把项目内提案记录复制覆盖生产**——记录必须锚定生产实际字节
3. **原子替换 hash-verify.sh**：mktemp 临时文件 → cp 候选 → chmod 保持目标权限 → mv 替换（注意：scp/cp 候选会丢执行位，替换后要 `chmod 755` 或按原权限）
4. **验证**：`bash hash-verify.sh` rc=0、逐项 OK、末行 ALL_OK
5. 备份带 UTC 时间戳，失败成对恢复（脚本+记录一起回滚，不单独回一个）

## 第 2 步：部署后整体终审（POST_DEPLOY_REVIEW）

### 2.1 终审任务书也必须 codex 打包（本会话踩坑：Hermes 自写被抓）

Hermes 直接按 DEPLOY_INSTRUCTIONS 第 5 节写 POST_DEPLOY_REVIEW_TASK.md 被自纠——**即使内容照抄 codex 自己的文档，任务书也派 codex 转格式**（USER_REQ 原话 + DATA_SOURCE + 产出要求，让 codex 打包成带 gate 标记的终审任务书 + 自审）。越界自我识别：写完发现「清单/输出格式/判定规则全是我定的」= 越界。

### 2.2 终审清单（codex 从 DEPLOY_INSTRUCTIONS 第 5 节提取，Hermes 只传话）

| 侧 | 检查项 |
|---|---|
| SG | dispatcher MD5、gate MD5、hash-verify 17 项、`bash hash-verify.sh` rc=0 ALL_OK、test 文件 py_compile、备份存在 |
| GZ（ssh 只读） | codex_remote MD5、hash-verify 9 项、`bash hash-verify.sh` rc=0 ALL_OK、新记录首字段=实算 MD5 |
| 跨侧 | 三份 C2 核心文件生产摘要与部署记录一致、全程无付费/外部 API、无服务重启 |

### 2.3 终审结论三态

`POST_DEPLOY_REVIEW: PASS` / `FAIL` / `NEED_INFO`——缺任何一项证据判 NEED_INFO，不判 PASS。claude 独立执行，不采信部署记录自述。

## 关键教训

1. **hash-verify 记录必须现场重算**，不复制提案——提案只证明「候选字节与部署提案对应」，不证明生产
2. **scp 远程部署先建远程目录**（本地 mkdir 没用，scp 不会自动建远端目标目录）
3. **cp 替换丢执行位**：hash-verify.sh 部署后 bash 直跑报 Permission denied → `chmod 755`
4. **GZ 注释残留「新加坡机版」**= 拷贝粘贴遗留，补齐时顺手修正
5. **用户「两边的一起弄完」= 授权把跨机剩余项一次清完**（GZ hash 补齐 + 部署后终审），但任务书打包纪律不变
