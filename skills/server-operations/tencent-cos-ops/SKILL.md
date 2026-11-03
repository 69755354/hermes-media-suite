---
name: tencent-cos-ops
description: 腾讯云COS素材/成品存储。触发：磁盘满/传素材/存成片/清理服务器/COS连接。
author: Hermes curator
license: MIT
version: 1.0
metadata:
  hermes:
    tags: [cos, 腾讯云, 存储, 素材, 成品, 磁盘]
    category: server-operations
---

# 腾讯云 COS 素材/成品存储

## When to Use

触发：服务器磁盘满要卸载素材/成片、客户素材归档、交付成片存储、临时文件中转、COS 连接/上传/下载/清理。素材和成品放 COS 是「服务器磁盘满」的最终解决方案。

## 桶（已建好，ap-guangzhou）

| 桶 | 名称 | 用途 |
|:--|:--|:--|
| 素材 | `sc-1447774428` | 客户素材/实景图/AI 生成图 |
| 成品 | `cp-1447774428` | 交付成片 |
| 中转 | `zz-1447774428` | 临时文件（Seedance 中转/ffmpeg 临时，用完删） |

## 连接（已配好，勿重装）

- SDK：`/home/ubuntu/.cosvenv/bin/python`（新加坡机 + 广州机都建了独立 venv）
- 密钥：`~/.hermes/.env` 的 `COS_SECRET_ID` / `COS_SECRET_KEY` / `COS_REGION=ap-guangzhou`（权限 600，勿外泄）
- 脚本：`/home/ubuntu/.hermes/scripts/cos_manager.py`（两台机都有）

## 用法（关键：走广州机！）

```bash
# 🔴 新加坡机跨境访问 COS 极慢/超时——COS 操作一律经广州机（腾讯云内网秒连）
ssh -p 2222 ubuntu@127.0.0.1 \
  "/home/ubuntu/.cosvenv/bin/python /home/ubuntu/.hermes/scripts/cos_manager.py <cmd>"

# 常用命令
cos_manager.py test                        # 三桶连通性
cos_manager.py list <sc|cp|zz> [prefix]    # 列文件
cos_manager.py upload <sc|cp|zz> <本地文件> <cos路径>
cos_manager.py download <sc|cp|zz> <cos路径> <本地路径>
cos_manager.py delete <sc|cp|zz> <cos路径>
cos_manager.py size <sc|cp|zz>             # 桶用量

# 批量卸载（磁盘满时首选）：>5M 媒体文件自动传对应桶后删本地
cos_sync.py --dry-run --roots <目录>       # 预览（不执行）
cos_sync.py --run --roots <目录>           # 执行（分类：FINAL/成片→cp，tmp→zz，其他→sc）
```

## 标准卸载流程（大文件迁移，0813 实战）

1. `cos_sync.py --dry-run` 或 `cos_manager.py list` 预览要传什么
2. 迁移前先筛保留版（`*FINAL*` 等最新交付留本地），旧版本才迁
3. 大文件 scp 到广州机 /tmp（内网快）→ 广州机 `cos_manager.py upload`
4. **上传后必须先 `cos_manager.py list <桶> <prefix>` 核对文件数/字节数对上，才删本地**
5. 清理本地 + 广州机 /tmp 临时
```

## 新建连接（换账号/换桶时）

1. 控制台拿密钥：https://console.cloud.tencent.com/cam/capi（SecretId + SecretKey，SecretKey 只显示一次，丢了要重建）
2. 建桶：COS 控制台 → 创建存储桶 → 名称 + 地域选广州（跟广州机同区，内网快）+ 私有读写
3. 装 SDK（🔴 PEP 668 拦截系统 pip）：`python3 -m venv ~/.cosvenv && ~/.cosvenv/bin/pip install cos-python-sdk-v5`
4. 密钥写两台机 `~/.hermes/.env`（新加坡机的 .env 不会自动同步到广州机，要各写一份）
5. 测连通：`/home/ubuntu/.cosvenv/bin/python cos_manager.py test`

## 预签名 URL（把文件发给用户，尤其微信通道）

`hermes send --to weixin` 发文件必失败（`Weixin media send failed`）→ 改发 COS 预签名链接。飞书能直发文件，不用走这条。

```bash
/home/ubuntu/.cosvenv/bin/python - <<'PY'
import sys, os, importlib.util
sys.path.insert(0, "/home/ubuntu/.hermes/scripts"); os.environ["COS_ACCELERATE"]="1"
spec=importlib.util.spec_from_file_location("cm","/home/ubuntu/.hermes/scripts/cos_manager.py")
cm=importlib.util.module_from_spec(spec); spec.loader.exec_module(cm)
BN = cm.resolve_bucket("cp")            # 必须先 resolve！
cl, region, acc = cm.get_client(BN)      # 第二个返回值是 region，不是桶名
url = cl.get_presigned_url(Bucket=BN, Key="huolong/delivery/xxx.docx", Method="GET", Expired=604800, SignHost=True, Headers={})
print(url)   # 只 print(url)；别的 print 会污染 stdout，链接就变成那句废话了
PY
```

**三个坑（都踩过）**：
1. `get_client("cp")` 传短名 → 加速域名缺 appid，预签名一律 `400 InvalidRequest: Bucket format should be <bucketname>-<appid>`。**先 `resolve_bucket("cp")` 再传**。
2. `get_client()` 返 `(client, region, accelerate)`——第二个是 region，当 Bucket 传必 400。
3. 验链用 **GET**（读前几十字节看 `PK`/`%PDF` 头）；`HEAD` 会 400，别当成链接坏了。

生成后必自测再发用户：HTTP 200 + Content-Length 与本地文件一致。

## 发文件给用户的两条路

- **飞书**：`hermes send --to feishu "MEDIA:/abs/path"` 直接发文件，可用。
- **微信**：不支持发文件 → 走上面的预签名链接；**链接独立一行纯文本、不带任何标点**（铁律八）。
- **站点静态目录别用**：广州站 Caddy 白名单只放行 jpg/png/mp4/txt/docx/pdf 等，**xlsx/csv 一律 404**，`/dl/` 这类路径也可能被应用层拦掉；要发文件就走 COS。

## 踩坑

1. **PEP 668 拦截**：系统 pip3 装 cos-python-sdk-v5 被拒（externally-managed-environment）→ 必须建 venv。SDK 包名 `cos-python-sdk-v5`，import `from qcloud_cos import CosConfig, CosS3Client`。
2. **新加坡机连 COS 慢/超时**：公网跨境到腾讯云广州限速（test 命令 60s+ 超时）——新加坡机勿直接操作 COS，统一走广州机内网。
3. **密钥写 .env 不是代码**：cos_manager.py 从 `~/.hermes/.env` 读（COS_SECRET_ID 等），不在脚本里写死；.env 权限 600。
4. **广州机 .env 各写一份**：跨机不自动同步。
5. **上传前检查本地文件存在**：cos_manager.py 会拒绝不存在的本地文件。
6. **先核对再删本地**（0813 教训）：批量迁移时「终版.mp4 没传就删了」（COS 只有 11/12 个）——上传后 list 核对是硬步骤，尤其遍历上传时看有没有跳过的文件。
7. **COS 操作依赖广州机反隧，反隧断则整条链断**（0814 实测）：「走广州机」的前提是 `ssh -p 2222 ubuntu@127.0.0.1` 反隧在线；新加坡机升级/重启后反隧断了 → 跨境直连广州 COS 又超时（ConnectTimeout 30s）→ COS 上传彻底失败。恢复前只能等反隧重建（广州机重新 ssh -R），或改发摘要/图片交付。排查顺序：先 `ss -tlnp | grep 2222` 确认反隧在不在，再决定走不走广州机。
8. **用对 venv**：COS 脚本用专用 venv `/home/ubuntu/.cosvenv/bin/python`（已装 qcloud_cos）。误用 hermes-agent venv 会 `ModuleNotFoundError: qcloud_cos`（那个 venv 没装、也没 pip，要 ensurepip + pip install 浪费一轮）。
9. **COS 加速域名（新加坡机直连的备用通道）**（0814 实测）：普通域名 `cos.ap-guangzhou.myqcloud.com` 新加坡机跨境超时，但**全球加速域名 `<桶>.cos.accelerate.myqcloud.com` 网络通**（curl 返回 400 正常）。坑：桶没在控制台开「全球加速」时，SDK 经加速域名上传报 `BucketAccelerateNotEnabled`——开加速是控制台操作（PUT /?accelerate 手动签名也走不通，跨境死结）。cos_manager.py 已加 `COS_ACCELERATE=1` 支持（Domain 参数 + upload 传 bucket）。**成功路径（0814 实测）**：用户在控制台开加速后，`COS_ACCELERATE=1 cos_manager.py upload <桶> <本地> <cos路径>` 直接上传成功（56KB docx 秒传）。**控制台准确路径**：桶详情 → 左侧「域名与传输管理」→「默认加速域名/全球加速」→ 开开关——**不需要添加自定义域名**（「添加域名」是 CDN 自定义域名那套，别走）；「基础配置」里没有这项。开完等 1-2 分钟生效（没生效时上传仍报 BucketAccelerateNotEnabled）。**⚠️ 加速是逐桶开的，不是全账号统一**（0815 实测 → 0826 更新）：当前 **三桶（sc/cp/zz）全已开加速**（0826 实测 `check_cos_accelerate.py` 三个都返回 Enabled）。0815时 cp/zz 没开，后来在控制台补开了。往任意桶传文件都可走 `COS_ACCELERATE=1` 加速通道。但仍建议先 `timeout 60 python3 /home/ubuntu/.hermes/scripts/check_cos_accelerate.py` 确认状态（控制台设置可能被改回）。新加坡机大文件交付标准路径 = `COS_ACCELERATE=1` + 加速桶（秒传）→ 预签名 URL（见 #12）。**批量上传实测**（0826）：56首BGM共431MB，`COS_ACCELERATE=1 cos_manager.py upload sc` 逐个上传，127秒全过，单文件7-50KB级秒传。
10. **微信平台文件交付限制**（0814 实测）：微信适配器 `_message_type_from_media` 只认 `image/`、`video/`、`audio/`——**docx/pdf 等文件类型 MEDIA: 投递直接失败**（系统报 "Couldn't deliver the file attachment"）。交付文档给微信用户 = 转图片（PIL 长图，中文字体 `/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc`，可复用脚本 `scripts/md_to_png.py`，用法 `python3 md_to_png.py <输入.md> [输出目录]`）或发摘要；要文件本体就走 COS 链接。**Word 交付（用户偏好「文档发 Word」）**：`sudo apt-get install -y pandoc && pandoc 输入.md -o 输出.docx`（pandoc 装一次即可；docx 里中文表格/代码块转换正常）；微信发不了 docx → docx 上传 COS + 预签名 URL 发文本链接（见 #12）。
12. **预签名URL在本机生成，别SSH到广州机**（0904实测）：`get_presigned_url` 是纯SDK端加密签名，不连COS服务器——哪台机有密钥就在哪台跑。广州机 `.env` 的 COS 密钥被注释掉了（`#COS_SECRET_ID=...`），SSH过去 `KeyError: 'COS_SECRET_ID'`。本机 `~/.hermes/.env` 有完整密钥，直接本机跑 `qcloud_cos` 即可。区分原则：upload/download/list/delete 等真正打COS API的操作才走广州机内网加速；`get_presigned_url` 只是数学运算，本机秒出。
13. **新加坡机临时 HTTP 文件服务需要腾讯云安全组放行**（0814 实测）：UFW 放行 + python http.server 起来后，公网 `curl <SG_HOST>:<port>` 仍是 000——云安全组默认不放行新端口，只能控制台改。安全组不放行时临时文件服务对用户不可达，别浪费时间。
14. **私有桶交付链接 = get_presigned_url 预签名 URL**（0814 实测）：COS 桶私有读，直接拼链接访问会被拒（403/404）——上传后给用户链接必须生成预签名 URL：`client.get_presigned_url(Method='GET', Bucket='<桶名>', Key='<cos路径>', Expired=7200)`（Expired 单位秒，2 小时常用）。链接含 `q-sign-*` 签名参数，发给用户可直接下载；签名里的 q-ak 是 SecretId（内部可发，SecretKey 才是绝密）。结合 #9/#10：反隧断时的新加坡机交付路径 = 加速域名上传（桶开加速）→ 预签名 URL 发微信文本链接（微信发不了 docx 文件，见 #10）。注意：预签名URL生成本机跑，别走广州机（见 #12）。

## 模板素材永久存档（0904用户定案）

**模板复用的参考图、成片、场景图等素材禁止只放 /tmp/。** Ubuntu 会定期清理 /tmp，导致模板素材丢失。模板素材必须上传到 COS 素材桶永久存档。

### 火龙漫剧模板素材存储路径

| 模板 | COS路径前缀 | 内容 |
|:---|:---|:---|
| 办公室版（混合通道H段） | `sc-1447774428/huolong/office-template/` | boss_threeview.png / sub_female_threeview.png / office_scene.png |
| 夜店网赚版v15 | `sc-1447774428/huolong/nightclub-template/` | （待补传，当前只在本地项目目录） |
| 通用口播版v14 | `sc-1447774428/huolong/general-template/` | （待补传） |

### 生成预签名URL给视频API用

模板素材存COS后，生成预签名URL（Expired=2592000即30天）给快乐马/wan3.0做参考图URL。

**🔴 关键：预签名URL生成是纯本地加密操作（SDK端签名），不连接COS服务器——直接在本机跑，不要SSH到广州机。** 广州机 `.env` 的 COS 密钥被注释掉了（`#COS_SECRET_ID=...`），SSH过去会 KeyError。本机 `~/.hermes/.env` 有完整密钥。

区分：只有真正连COS服务器的操作（upload/download/list/delete）才需要走广州机内网加速；`get_presigned_url` 只是数学运算，哪台机有密钥就在哪台跑。

```python
# 在本机直接执行（本机 .env 有完整 COS 密钥）
import os
from qcloud_cos import CosConfig, CosS3Client

env = {}
with open(os.path.expanduser('~/.hermes/.env')) as f:
    for line in f:
        line = line.strip()
        if line.startswith('export '): line = line[7:]
        if '=' in line and not line.startswith('#'):
            k,v = line.split('=',1)
            env[k.strip()] = v.strip().strip('"').strip("'")

config = CosConfig(Region=env['COS_REGION'], SecretId=env['COS_SECRET_ID'], SecretKey=env['COS_SECRET_KEY'], Scheme='https')
client = CosS3Client(config)

url = client.get_presigned_url(Method='GET', Bucket='sc-1447774428', Key='huolong/office-template/boss_threeview.png', Expired=2592000)
print(url)
```

### 教训（0904）

- 办公室版参考图原放 `/tmp/huolong_boss_drama/`，被系统清空丢失
- 改skill时自作主张换了人物和场景（老板→周哥，女下属→芳姐，办公室→客餐厅），参考图也跟着换成了客餐厅版，原版办公室图没有COS备份
- 混合通道v2项目目录 `huolong_mixed/assets/` 的 characters/scenes/bgm 三个子目录全是空的
- **模板素材必须传COS，项目目录只放当前工作副本**

## 相关

- linux-disk-maintenance：磁盘清理清单（COS 是卸载大文件的去处）
- claude-code-ops / codex-cli-ops：AI 执行器运维
- dashscope-video-generation：快乐马/wan3.0视频生成（模板素材存COS后生成预签名URL做参考图）
