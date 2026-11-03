# R7 confirm_gate + execute_api 部署（SG 批2，root + 重启）

来源：`staging/unified-fix-20260823/SG/R7_fixed/部署说明.md`，2026-08-23 实测整理。

## 为什么需要人执行

- `/opt/hermes/gates/confirm_gate.py` 是 `-r--r--r-- root:root`（被管方不能改管自己的闸）
- 重启 PID 会断在途请求（`/seedance-exact/job` 异步 job 随进程丢失），属不可逆操作，铁律 7 须人批准

## 部署时间窗

`huolong-guide` 的 `node12_render` 确认时间 `2026-08-22 18:48:29`，TTL 24h ⇒ **须在 08-23 18:48 前部署**，否则火龙项目需重新走客户出片确认。

## 基线（部署前 md5sum 核对，不符即停）

```
三份 confirm_gate.py 均 072609d0e2d401c774e317d8ec5d03a7
execute_api.py        c97a37942530cd3438855fc2f5a254a7（727 行）
```

部署后期望：三份 confirm_gate = `3eb05c1e28179b04f66685b073e82b52`，execute_api.py = `de78ce5d2213a409ae3d3987f7692cc5`（781 行，含 R1+R7）。

## 命令序列

```bash
export SRC=/home/ubuntu/workflow/projects/xiaolu-bug-sweep/staging/unified-fix-20260823/SG/R7_fixed
export TS=20260823

# ① 备份
sudo cp -a /opt/hermes/gates/confirm_gate.py            /opt/hermes/gates/confirm_gate.py.bak-$TS
cp -a /home/ubuntu/.hermes/scripts/confirm_gate.py      /home/ubuntu/.hermes/scripts/confirm_gate.py.bak-$TS
cp -a /home/ubuntu/workflow/scripts/confirm_gate.py     /home/ubuntu/workflow/scripts/confirm_gate.py.bak-$TS
cp -a /home/ubuntu/execute_api.py                       /home/ubuntu/execute_api.py.bak-$TS
cp -a /home/ubuntu/.hermes/guard/hashes/confirm_gate.py.md5 /home/ubuntu/.hermes/guard/hashes/confirm_gate.py.md5.bak-$TS

# ② 换 confirm_gate 三副本（须 root，用 install 避免 chmod+写中间窗口）
sudo install -o root -g root -m 444 "$SRC/confirm_gate.py" /opt/hermes/gates/confirm_gate.py
install -m 444 "$SRC/confirm_gate.py" /home/ubuntu/.hermes/scripts/confirm_gate.py
install -m 664 "$SRC/confirm_gate.py" /home/ubuntu/workflow/scripts/confirm_gate.py
md5sum /opt/hermes/gates/confirm_gate.py /home/ubuntu/.hermes/scripts/confirm_gate.py /home/ubuntu/workflow/scripts/confirm_gate.py
# 三行都应 3eb05c1e...

# ③ 同步哈希基线
echo "3eb05c1e28179b04f66685b073e82b52  /home/ubuntu/.hermes/scripts/confirm_gate.py" > /home/ubuntu/.hermes/guard/hashes/confirm_gate.py.md5
bash /home/ubuntu/.hermes/scripts/hash-verify.sh

# ④ 换 execute_api.py（含 R1，无需 root）——此时可停，中间态安全
install -m 644 "$SRC/execute_api.py" /home/ubuntu/execute_api.py
md5sum /home/ubuntu/execute_api.py    # de78ce5d...
python3 -m py_compile /home/ubuntu/execute_api.py && echo "语法 OK"

# ⑤ 重启 1889（⚠️ 不可逆，先确认无在途 job）
ss -ltnp | grep 1889
kill 3588183        # 或当前实际 PID
sleep 2
nohup python3 /home/ubuntu/execute_api.py >> /home/ubuntu/execute_api.log 2>&1 &
sleep 3
curl -s http://127.0.0.1:1889/ping   # {"status":"alive"}

# ⑥ 验收
python3 /opt/hermes/gates/confirm_gate.py check /home/ubuntu/workflow/projects/huolong-guide node12_render; echo "rc=$?"   # 0
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:1889/execute -d '{}'   # 410
```

## 回滚

```bash
sudo install -o root -g root -m 444 /opt/hermes/gates/confirm_gate.py.bak-$TS /opt/hermes/gates/confirm_gate.py
install -m 444 /home/ubuntu/.hermes/scripts/confirm_gate.py.bak-$TS  /home/ubuntu/.hermes/scripts/confirm_gate.py
install -m 664 /home/ubuntu/workflow/scripts/confirm_gate.py.bak-$TS /home/ubuntu/workflow/scripts/confirm_gate.py
cp /home/ubuntu/.hermes/guard/hashes/confirm_gate.py.md5.bak-$TS /home/ubuntu/.hermes/guard/hashes/confirm_gate.py.md5
install -m 644 /home/ubuntu/execute_api.py.bak-$TS /home/ubuntu/execute_api.py
# 再走一次 ⑤ 重启
```

## 实测坑（2026-08-23）

- 用户从 Termux 直接跑命令，`pkg install python` 提示 = 命令跑在手机本地，必须先 `ssh ubuntu@<SG_HOST>` 登新加坡机。
- 服务先重启、文件后换 = 白重启（curl 仍 200 不是 410）。顺序必须是 ②③④ 换文件 → ⑤ 重启。
