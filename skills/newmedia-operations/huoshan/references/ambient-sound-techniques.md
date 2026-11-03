# 环境音制作方案

## 背景

Seedance 2.0 Mini 不渲染环境音（只处理人声）。节点11必须手动叠加环境音轨。本节记录已验证过的环境音获取和生成方案，适用于国内网络环境（Google/YouTube受限）。

## 方案A：ffmpeg粉红噪音+免费鸟鸣混合（本会话已验证 ✅）

### 鸟鸣音源：康奈尔实验室免费鸟鸣包

**下载地址：** https://dl.allaboutbirds.org/hubfs/Voices%20of%20Eastern%20Backyard%20Birds2.zip

**选曲建议（适合茶馆/庭院氛围）：**
- `01 Eastern Backyard Birds.mp3` — 综合鸟鸣汇编，12秒长
- `02 Mourning Dove Song.mp3` — 斑鸠，柔和低沉，28秒长
- `11 Black-capped Chickadee Song.mp3` — 山雀，轻快鸟鸣，16秒长

**快速下载命令：**
```bash
curl -L -o bird_sounds.zip "https://dl.allaboutbirds.org/hubfs/Voices%20of%20Eastern%20Backyard%20Birds2.zip" --max-time 60
unzip bird_sounds.zip -d bird_sounds/
```

### ffmpeg混合脚本

```bash
ffmpeg -f lavfi -i "anoisesrc=color=pink:duration=36:seed=42" \
  -i "bird_sounds/Voices of Eastern Backyard Birds/01 Eastern Backyard Birds.mp3" \
  -i "bird_sounds/Voices of Eastern Backyard Birds/02 Mourning Dove Song.mp3" \
  -i "bird_sounds/Voices of Eastern Backyard Birds/11 Black-capped Chickadee Song.mp3" \
  -filter_complex "\
    [0:a]volume=0.15[a_base];\
    [1:a]adelay=2000|2000,volume=0.12[a_bird1];\
    [2:a]adelay=12000|12000,volume=0.10[a_bird2];\
    [3:a]adelay=22000|22000,volume=0.08[a_bird3];\
    [a_base][a_bird1][a_bird2][a_bird3]amix=inputs=4:duration=first:dropout_transition=2[a_out]" \
  -map "[a_out]" -ac 2 -ar 44100 ambient_36s.mp3 -y
```

### 参数说明

| 参数 | 值 | 说明 |
|:----|:---|:-----|
| anoisesrc color | pink | 粉红噪音，比白噪音更柔和，像微风/自然环境 |
| volume (base) | 0.15 | 底噪音量，背景层 |
| adelay | 2000/12000/22000 | 鸟鸣分别在2秒/12秒/22秒后出现，营造自然交错感 |
| volume (birds) | 0.12/0.10/0.08 | 多只鸟混合，音量递减避免叠加过响 |
| amix dropout_transition | 2 | 音轨结束后2秒淡出过渡 |

## 方案B：Pixabay免费音效（需有代理）

国内网络环境可能被屏蔽（返回403），有代理时可使用。

**URL：** https://pixabay.com/sound-effects/search/garden/

搜索关键词建议：`garden ambience`、`outdoor cafe`、`birds nature`、`garden restaurant`

## 方案C：其他免费音源

| 站点 | URL | 说明 |
|:----|:----|:-----|
| Mixkit | https://mixkit.co/free-sound-effects/nature/ | CDN直链被防（403），需带Referer或下载工具 |
| FreeSoundLibrary | https://www.freesoundslibrary.com/ | 免费，JS渲染需手工操作 |
| BigSoundBank | https://bigsoundbank.com/ | 免费，JS渲染 |

## 环境音类型与场景匹配

| 场景 | 环境音类型 | 建议方案 |
|:----|:----------|:---------|
| 户外庭院/茶馆 | 鸟鸣+微风底噪 | 方案A（粉红噪音+鸟鸣） |
| 室内茶馆/包间 | 人声嗡嗡+煮水声 | 方案A底噪+低频叠加 |
| 街边门头 | 远处车声+脚步声 | 粉红噪音+低频滤波 |
| 安静品茶 | 茶盏轻碰+微风吹叶 | 粉红噪音极低音量 |

## 三轨混音比例速查

| 音轨 | 音量 | 说明 |
|:----|:----|:------|
| 视频人声（原音轨） | 1.0 (100%) | 保持原音量不变 |
| BGM | 0.15-0.20 | 低于人声，不抢戏 |
| 环境音 | 0.20-0.25 | 比BGM略大但低于人声 |
