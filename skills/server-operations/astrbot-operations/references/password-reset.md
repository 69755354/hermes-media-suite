# AstrBot WebUI 密码重置

当忘记 AstrBot 管理面板密码时（登录提示「用户名或密码错误」）。

## 前提

配置文件路径：
```
<data_dir>/cmd_config.json
```
数据目录默认为 `/home/ubuntu/AstrBot/data`，通过 Docker volume 挂载到容器内 `/AstrBot/data`。

**该文件使用 UTF-8 BOM 编码**，Python 读取时必须指定 `encoding='utf-8-sig'`，否则 json 解码报错。

## 方法一：删除密码字段让系统自动生成（推荐）

1. 读取配置，删除 `dashboard.password` 和 `dashboard.pbkdf2_password` 字段

```python
import json
path = '/home/ubuntu/AstrBot/data/cmd_config.json'
data = open(path, 'r', encoding='utf-8-sig').read()
d = json.loads(data)
d['dashboard'].pop('password', None)
d['dashboard'].pop('pbkdf2_password', None)
d['dashboard'].pop('password_storage_upgraded', None)
d['dashboard']['password_change_required'] = True
out = json.dumps(d, indent=2, ensure_ascii=False)
open(path, 'w', encoding='utf-8-sig').write('\ufeff' + out)
```

2. 重启 AstrBot 容器

```bash
docker restart astrbot
```

3. 从启动日志获取新密码

```bash
docker logs astrbot 2>&1 | grep "Initial password"
```

日志会输出多行，**取最后一行**为当前生效密码。

## 方法二：直接写入已知密码（MD5）

直接用已知密码的 MD5 值写进去：

```python
import hashlib, json
plain = 'astrbot123'
md5 = hashlib.md5(plain.encode()).hexdigest()
path = '/home/ubuntu/AstrBot/data/cmd_config.json'
data = open(path, 'r', encoding='utf-8-sig').read()
d = json.loads(data)
d['dashboard']['password'] = md5
d['dashboard'].pop('pbkdf2_password', None)
d['dashboard'].pop('password_storage_upgraded', None)
d['dashboard']['password_change_required'] = False
out = json.dumps(d, indent=2, ensure_ascii=False)
open(path, 'w', encoding='utf-8-sig').write('\ufeff' + out)
```

然后重启 AstrBot。

## 踩坑记录

| 坑 | 说明 |
|:---|:------|
| **BOM 编码** | 文件开头有 `\ufeff`，json.loads 必须用 `utf-8-sig` |
| **权限** | 文件属主可能为 root，无需 sudo 会报 Permission denied |
| **多行 Initial password** | 每次重启生成一个新密码，日志里旧的还在。取最后一行 |
| **ASTRBOT_RESET_DASHBOARD_PASSWORD=1** | 环境变量设了这个会在启动时强制重置密码 |
| **pbkdf2_password 优先级可能高于 password** | 两个字段都删掉最稳妥 |
