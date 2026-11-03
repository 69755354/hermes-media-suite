# 部署落地核实三连 + 脚本自报不算数（2026-08-23 G07 部署实录）

## 场景

G07 四补丁 + 两模块 root 部署完成，脚本输出 `DEPLOYMENT_READY=YES`。用户等结果。Hermes 不能光凭脚本自报向用户报「部署完成」——pitfall 12 就是脚本假成功的前科（git apply 静默跳过 rc=0）。

## 收工核实三连（部署后必做，再向用户汇报）

1. **生产文件 hash vs patched 快照逐字节核对**：
   ```bash
   cd /home/ubuntu/workflow/projects/<项目>
   for f in /path/prod_file1 /path/prod_file2 ...; do md5sum "$f"; done
   for f in kb_gate_sg.py gate_config.yaml codex_exec_gated.sh hermes_task_dispatch.py; do md5sum "staging/patched/$f"; done
   ```
   逐对一致（4/4）才算补丁真生效。本次 G07 四文件 hash 与 patched 快照全匹配。

2. **新装模块确认存在**：`ls -la /home/ubuntu/.hermes/scripts/taskbook_attest_gate.py /home/ubuntu/.hermes/scripts/dispatcher_g07_adapter.py`——root:root 755、大小合理（12989/2391 字节）。

3. **备份目录确认存在**：`stat -c "%a %U:%G %n" /home/ubuntu/workflow/backups/<ts>/`——**0700 root:root 时非 root `ls` 列不出内容、`sudo -n` 也要密码，这是正常保护不是部署失败**；目录能 stat 到即可，备份指针 BACKUP_DIR 部署输出里已有。

## 判断标准

- 脚本自报 `DEPLOYMENT_READY=YES` / `DEPLOYMENT_PREFLIGHT=PASS` = 脚本内部自检，**不等于落地**。收工汇报前必须亲自核实三连。
- 核实完才向用户报「部署完成」；核实中任一不符 = 先查原因（基线漂移/补丁没生效/模块没装），不报完成。
- 用户问「好了没」时，若部署脚本刚跑完：先核实三连再答，别用脚本自报顶替核实结果。
