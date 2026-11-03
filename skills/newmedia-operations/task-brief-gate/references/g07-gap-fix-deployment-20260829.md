# G07 Attest 闸剩余缺口修复部署实录（2026-08-29）

## 背景

Codex 8/29 审计发现 G07 attest 闸两机仍存在缺口：
- SG: ds_fallback.sh 未接 G07、config 损坏 fail-open
- GZ: gz_brief_gate_check.sh 传 config={}+trust_boundary_strong=False（运行时退化为 WARN）、gz_ox_shell.sh 未接闸、ds_fallback/claude_wrapper 吞 BLOCK 退出码、write_attest.sh 权限不对、--search/--gen-img 旁路未收口

## 修复流程

1. 临时切 WARN（`sed -i 's/^  mode: BLOCK/  mode: WARN/' gate_config.yaml`）
2. 收集两机真实基线文件到 `projects/g07-fix-gap/inputs/baselines/`
3. 派 codex 打包修复补丁（传话书：USER_REQ 原话 + DATA_SOURCE 基线路径 + 审计报告）
4. codex 产出：逐文件 hunk patch + 部署映射表 + 部署脚本 + 验证探针 + fail-closed 单测
5. Hermes 验证：补丁 SHA 一致、候选文件语法全过、基线 SHA 匹配、fail-closed 单测通过
6. 用户终端跑 `sudo bash deploy_g07_fix.sh sg` + `verify_g07_deployment.sh sg`
7. scp 项目到 GZ，用户终端跑 `sudo bash deploy_g07_fix.sh gz` + `verify_g07_deployment.sh gz`

## 部署踩坑序列

### 坑1: setfacl 未安装
- 两机都没装 `acl` 包，部署脚本 `command -v setfacl` 失败 exit
- 修法: `sudo apt install -y acl`
- 环境问题不捕获为持久规则

### 坑2: SG claude_remote_wrapper.sh 是软链
- `.hermes/scripts/claude_remote_wrapper.sh` → `workflow/scripts/claude_remote_wrapper.sh`
- 部署脚本 `verify_baseline` 里 `[ ! -L "$target" ]` 拒绝软链直接 exit 3
- 首次部署备份了前4个文件但到 claude_wrapper 就退了，write_attest 迁移和 gate_config 落盘没跑
- 修法: 改 `verify_baseline` 跟随软链 `real_target=$(readlink -f "$target")`，部署也部署到真实路径

### 坑3: 部分部署后基线 SHA drift
- 坑2导致首次部署部分成功（5个文件已覆盖成候选值），但基线 SHA 还是原始值
- 重跑时 verify_baseline 报 drift
- 修法: `sha256sum` 已覆盖文件，更新部署脚本基线 SHA 为当前生产值（== 候选值）
- 注意只改已覆盖的，未覆盖的保持原始值

### 坑4: sed 全局替换跨机污染
- 用 `sed -i 's/旧SHA/新SHA/'` 更新 SG 基线时，把 GZ 侧同名文件 dispatcher_g07_adapter.py 的基线也改了
- 两机该文件 SHA 不同（SG 已部署成候选值、GZ 还是原始值）
- GZ 部署时 verify_baseline 报 drift: expected=<SG候选值> actual=<GZ原始值>
- 修法: 用 patch 工具按上下文限定替换，不用全局 sed

### 坑5: GZ claude_wrapper 路径不在 ~/.hermes/scripts/
- codex 部署脚本写 GZ claude_wrapper 目标为 `~/.hermes/scripts/claude_remote_wrapper.sh`
- 实际在 `workflow/scripts/claude_remote_wrapper.sh`（GZ 无软链）
- 修法: sed 改部署脚本 GZ 侧路径 + 验证探针路径

### 坑6: 验证探针 index vs rindex
- GZ OX 探针 `t.index("ox_native_invoke.py")` 匹配到注释行（第177字符）
- 实际调用在第3171字符，断言 `177 < 2196 < 3171` 失败
- 修法: `t.rindex("ox_native_invoke.py")` 从后往前找实际调用位置

## 最终状态

两机全 PASS：
- gate_config: BLOCK/strong (root:ubuntu 440)
- g07_brief_gate_check.py: root:ubuntu 550
- dispatcher_g07_adapter.py: root:ubuntu 440
- write_attest.sh: /usr/local/libexec/hermes/ (root:ubuntu 550 + attest_writer ACL r-x)
- ubuntu 不可改 writer、attest_writer 可读不可改
- DS/Claude/OX 全接 G07
- --search/--gen-img 硬关 (GZ)
- fail-closed + 项目外 brief 拦截

## 仍未签署

- write_attest.sh 正文不在输入包，signer 能否拒绝伪造 attest 的对抗测试未跑
- 后续需真实 packager 跑一轮 forgery test