# NewMe 单账号抖音试点部署方案要点（2026-08-21 实测）

来源：codex 部署方案《本地生活单账号抖音试点部署方案_20260821.md》+ Hermes 源码抽查。

## 机器实测数据

- 新加坡服务器：3.6G 内存 / 2 核 / 磁盘剩 20G / 有 Playwright Chromium 1228
- NewMe 原版基线：8GB Mac，单 Chrome 串行，单个 Chrome 约 1.5-2GB，启动前要求 ≥2GB 可用内存
- 结论：当前新加坡机不当首期真发 worker（内存低于 8G 基线 + 出口非账号常用登录地 + Linux 化改造量大）

## 方案核心结构（可复用为模板）

1. 试点范围与前提：单账号/单平台/我们长期代运营+书面授权+内容排期人工批准；明确不做三平台/多租户
2. 机器选型对比表（11 维度：内存/登录态风控/扫码路径/headless/交互差异/7x24/服务监督/资源争用/profile 安全/改造工作量/故障接管）
3. 改造清单 7 组件：抖音发布执行器、登录保活、调度服务、数据回读、阳性对照门禁、作业队列/服务监督、账号 profile 隔离——每项【改动点】【风险】【验证方式】
4. 分阶段部署 0-3 + 每阶段验收
5. 最终验收 20 条硬标准
6. 风险责任边界表 + 回滚方案
7. 依赖决策点 9 项（老板拍板）

## NewMe 源码硬编码点抽查（publish_douyin.py 842 行）

真正要动的只有 3 处：
- POI 逻辑：`set_location` 搜「Dubai」取城市级（兰博基尼未来城/迪拜之窗是坑），要改成搜客户门店名+回读门店 POI ID
- 账号/profile 参数化：`PROFILE = ~/NewMe/profiles/douyin`、keychain 取密码
- 外部加壳：审批令牌、幂等键、发布回执、审计（不碰核心发布流程）

不用动的：选择器（文件口 input[type=file][accept*=video]、标题 input.semi-input、发布键 button.button-dhlUZE.primary-cECiOJ 文字==「发布」）、上传完成判据、双封面流程、话题 div[data-mention]、Meta+a（Mac 环境）、时区 CDP Asia/Shanghai。

## 关键红线（从 NewMe AGENTS.md 提炼）

- 发布键永不禁用，点下去就发——体检/阳性对照是唯一防线
- 永不 `pkill -f chrome`，只能精确杀 profile 进程
- 不往活 profile 回灌旧 cookie（会覆盖新会话）
- 视频号不用 headless（HeadlessChrome 判异地新设备作废会话），用屏幕外真窗口 --window-position=-3000,0
- 抖音发布后必须作品管理页回读平台作品 ID 收口，URL/标题不算成功
- 掉线不刷新登录态快照，只有在线时才存

## 用户电脑配置查询路径（小鹿 guardian 链路）— 2026-08-22 实查更新

- 用户 Mac：MacBook Pro（SSH key 显示 <MAC_HOST>，<MAC_USER> 用户）
- 广州机 /home/ubuntu/public/guardian.py：Mac 守护器轮询 http://<GZ_HOST>/api/tasks（caddy `/api/*` → 127.0.0.1:8088 task_api.py）
- ⚠️ **guardian shell action 已禁用（2026-08-22 实查）**：`if action == "shell": raise Exception("shell action 已禁用")`——只剩 export_jianying / upload_file / list_bgm / upload_bgm。旧文档「可下发 shell 查 system_profiler」已失效，不能靠它远程装环境/跑脚本。
- 广州机 authorized_keys 6 个 key：u0_a209@localhost / hk-to-gz / ubuntu@VM-0-11-ubuntu / mac-jianying / singapore-to-guangzhou / <LOCAL_EMAIL> —— Mac 反向隧道 key 已配好，但**隧道不会自动起**；2026-08-22 实查 Mac 离线（广州 who 无连接、新加坡 8000 无监听）。
- **Mac 远程执行替代通道**：jianying-remote-automation 那套（Mac 上 jianying-web.py Flask :8000 + `ssh -R 8000:localhost:8000` 反向隧道），隧道起来了服务器才能 POST /run。部署 Mac worker 前置三件套：**Mac 开机 + 隧道在线 + 能执行命令**；缺一部署推不动。
- **直连 Mac SSH 的反向隧道命令（2026-08-22 实配）**：Mac 终端跑 `ssh -R 2223:localhost:22 -N ubuntu@<GZ_HOST>`（广州机，2223 自定义端口；首次 yes + 输 ubuntu 密码；命令挂住不退出=隧道活），服务器侧 `ssh -p 2223 ubuntu@127.0.0.1` 连回 Mac。Mac 国内宽带多为 CGNAT 大内网（`curl ifconfig.me` 公网 IP ≠ 本地 IP、本地 IP 为 100.64.x/10.x/192.168.x 即大内网），服务器无法直连，只能 Mac 主动建隧道。发此命令给用户必须纯文本（禁反引号/代码块，聊天复制会带脏字符）。
- **guardian 在线探针（验证 Mac 守护器是否活着，2026-08-22 实跑）**：放一个 pending 只读任务到广州机 `task_api.py` 队列，等 ~75 秒（guardian 30 秒轮询周期），看是否被取走：
  ```bash
  # 广州机
  cat > /home/ubuntu/public/tasks/cmd_mac_probe_001.json << 'EOF'
  {"id":"cmd_mac_probe_001","type":"command","action":"list_bgm","status":"pending","created_at":"2026-08-22T21:20:00+08:00","note":"Mac 在线探测（只读）"}
  EOF
  sleep 75 && cat /home/ubuntu/public/tasks/cmd_mac_probe_001.json
  ```
  status 仍 pending = Mac 离线（2026-08-22 实查即此结果，guardian 最后响应停在 8/14）；被取走/finished 目录有回传 = 在线。用完删探针文件。同法可查 `who`（活跃 SSH 会话身份：Termux 是 u0_a209@localhost 手机，Mac 是 <MAC_USER>@<MAC_HOST>）+ `ss -tlnp`（8000/2223 隧道端口）。
- 广州机 customer profile 会话库：/home/ubuntu/.hermes/profiles/customer/state.db（搜「guozhiyong」可找到 Mac 名）
- 注意：任何动用户 Mac 的动作需用户点头
