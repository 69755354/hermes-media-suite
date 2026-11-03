---
name: windows-client-delivery-gate
description: 给客户发 Windows 安装包前的出包门禁。触发：客户装不上。
metadata:
  hermes:
    tags: [windows, 交付, 门禁, 编码, 真机]
    category: server-operations
---

# Windows 客户端出包门禁

## When to Use
给客户交付 Windows 客户端/安装包之前；客户报「双击没反应/乱码/安装没走完」时。

## 产品口径（用户拍板，别再问）
- **数据回传 = 按需取数，不是定时上报**：客户机**默认不上报**（无定时/无周期）；只有我们主动要时，才传一次。轻量心跳（默认 5 分钟，只带机器指纹+授权号、不传数据）只用来问“有没有取数指令”。
- **不告知客户**：说明书、README、面板文案、弹窗、日志**一律不得出现**「数据回传/上报/同步给我方」字样；心跳对客户不可见。
- **不需要客户同意**：不设开关、不留同意记录。只传数字与元数据，不传素材正文/登录态/cookie。
- 老板要看的就两样：**素材发到了哪个抖音号 + 那个号的后台数据**（一张扁平 Excel，播放量降序带合计）。

## 送审/复核纪律
- **复核必须对着冻结快照**：出包后生成 `output/review_snapshot_<版本>/`（zip + 源码 tar.gz + SHA256SUMS.txt + 版本对照表），复核报告要能绑定到具体哈希；
  **复核期间任何单不得再写同一份源码**（否则会出现「包 1.2.8 / 源码 1.2.9」→ 复核结论作废，已踩）。
- 复核输出必须分级：`【必修】/【建议】/【已核实无问题】/【待真机】`，每条带 文件:行号 + 实测命令输出；**只出问题清单，不改文件**。
- 典型必修类型（GFP 反复抓到的）：① 展示端与生产端信任根不一致（panel 说「授权有效」而 CLI 该拒）② 拒绝路径的**顶层状态仍报 OK** ③ 自恢复只是「不重启风暴」而非**真接管进程** ④ 文档口径与实物不符（19/19、模拟填表）。

## 铁律
0. **没经独立复核（GPT 复核）的包不许上传、不许发链接给客户**。自验 + 真机通过 ≠ 可交付；
   复核前不要先把包挂到 COS 发链接（发出去的链接必须能下架：删除 COS 对象即可失效）。
1. **打包前先跑静态自检**，FAILS≠0 不许打包：
   `python3 <项目>/output/tools/windows_compat_check.py <bundle.zip>`
   覆盖：`.ps1` 必须 UTF-8 **带 BOM**；`.bat/.cmd/.vbs` 必须 GBK；
   **`.bat/.cmd` 必须 CRLF**（LF-only 会让 cmd 解析崩，0.1 秒满屏报错、什么都没装）；
   zip 中文名要 UTF-8 flag；保留名/非法字符；>150 字符路径报警；PS5.1 禁用语法。
2. **真机只开一台、一次跑完、测后立即销毁**。失败不许重建第二台（曾因反复重建开到 8 台）。
3. **没证据=没验过**：留原始字节/hex/退出码/销毁回执。
4. **区分「安装失败」和「自检红灯」**：自检 EXIT_GATE_RED=2 常是缺 Chrome/未授权这类预期红灯。

## 真机项（静态查不出）
双击入口真跑、Mark-of-the-Web 拦截、杀软/Defender 弹窗、防火墙弹窗、中文/空格路径、
Chrome 真实路径与缺失提示、自启重启策略、桌面图标与面板、扫码登录、控制台原始中文。

## 云上真机怎么搭（腾讯云）
- CVM ap-guangzhou，Windows Server 2022 **中文版**（ACP=936 才验得出乱码），2C4G，按量付费。
- 云助手(TAT)在公共镜像上**经常未安装**（报 AgentNotInstalled）→ 别指望远程命令；
  用开机注入(UserData)跑一次性验收脚本，结果写回 COS，**不要**为改脚本反复重建机器。
- SDK：`/home/ubuntu/.cosvenv/bin/python` + `tencentcloud-sdk-python-cvm`；COS 操作走广州机内网。

## 下载链接怎么发（2026-10-29 实测）
- `https://xingturgzn.cn/dl/*.zip` 是 **404**：Caddy 的 `static_guard` 扩展名白名单不含 `zip`，站点块里也没有 `/dl` 路由。要让它通必须改 `/etc/caddy/Caddyfile` 并 reload，需要 root。
- 客户机拿包实际走 COS：桶 `cp-1447774428`（私有读），key `<client>/<project>/<filename>`，把**单个对象**设 `public-read`，链接用加速域名 `https://cp-1447774428.cos.accelerate.myqcloud.com/<key>`。国内可直连；新加坡直连 `cos.ap-guangzhou` 会超时，必须用加速域名。
- 上传：`/home/ubuntu/.hermes/hermes-agent/venv/bin/python ~/.hermes/scripts/cos_manager.py upload cp <file> --client <cid> --project <pid>`。
- 单独设 ACL 时 `CosConfig` 要传 `Domain='<bucket>.cos.accelerate.myqcloud.com'`，否则 SDK 默认域名在新加坡侧卡死。
- 交付前必须回读：`curl -s <url> | sha256sum` 与本地一致，并在国内机（广州）也拉一遍。

## 踩过的坑
- 无 BOM 的 UTF-8 `.ps1` → 中文 Windows 按 GBK 读 → 乱码 + 语法崩。
- LF-only 的 `.bat` → cmd 解析崩（独立于编码坑的第二个坑）。
- 说明书点名了包里不存在的文件名 → 客户找不到入口。
- Linux 上静态全绿 ≠ 能装：上述两坑都只在真机暴露。
- **复用老 venv 会缺 pip**：安装器先 `venv --without-pip` 再 ensurepip，但升级时 `venv_ok()` 只看 python 能跑 → 日志「venv already present」→ 下一步 `No module named pip` 直接 FATAL。修法：`venv_ok()` 之外加 `pip_ok()` 探测，缺 pip 就地 `ensurepip --upgrade` 修复，不要删 venv。
- **非管理员远程安装会在建计划任务时挂**：`schtasks /Create ... /RU <user>` 在客户机被组策略拒绝 → 日志到 `[5/6] machine code` 之后 `could not replace/start ONLOGON supervisor task`。判定要精确：**任务不存在 + HKCU Run 已注册** → 降级 WARNING 继续（Run 就是完整开机自启路径）；**有旧任务删不掉** → 必须 FATAL，否则开机会拉起旧版本。
- 远程装完的验收口径（不靠安装器返回码）：`ping` 看 cwd 是否新目录、`/healthz` 版本号、`schtasks /Query` 与 `reg query HKCU\...\Run`、安装日志里 selftest 是否 ALL GREEN。
