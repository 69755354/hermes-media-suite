# BGM 混音实测（2026-08-24 火龙 v17）

## 结论：推广/口播类 BGM 音量按用户听感调，嫌小 = 提音量 + 侧链压缩保人声

老板对 BGM 感知偏响（抖音投放受众习惯明显 BGM）：
- 0.13（bgm-library 推荐「探店口播 0.12-0.15」）→ 老板「bgm声音太小了」
- 0.22（快节奏档 0.2-0.25）→ 老板「还是太小」
- **最终 0.3 + sidechaincompress（ducking）通过**：BGM 明显可闻，转写抽查人声仍清晰（句2/句16/句28 全听清）

## 最终混音写法（ffmpeg filter_complex）

```
[1:a]atrim=start=0:end=${DUR},asetpts=PTS-STARTPTS,volume=0.30[bed];
[0:a][bed]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=500:makeup=1[ducked];
[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[aout]
```

原理：sidechaincompress 用主音轨（人声）作侧链，人声出现时 BGM 自动压下去（ratio=6），人声间隙 BGM 回到 0.30——比「只调 volume」多一层动态保护，BGM 响但不糊人声。

## BGM 库位置（2026-08-26 发现）

**广州机**：`/home/ubuntu/assets/bgm/`（29 首 MP3，mixkit 系列 + codex_Carefree + codex_EasyLemon + SoundHelix-Song-1）
拉到本机：`scp -P 2222 -o ConnectTimeout=10 ubuntu@127.0.0.1:/home/ubuntu/assets/bgm/<file> /tmp/`

**推荐选曲**：
- `mixkit_834.mp3`（52s，mean=-15.6dB，适合短视频推广广告，2026-08-26 火龙V15定版使用）
- `codex_Carefree.mp3`（25s，mean=-22.6dB，偏短需 loop 或只覆盖部分）
- SoundHelix-Song-1.mp3（备选，需联网下载）

**混音参数（V15定版）**：`volume=1.5,alimiter=limit=0.95` + `amix=inputs=2:duration=first:dropout_transition=0:normalize=0:weights='2 1'`（人声权重2:BGM权重1）

## 教训（2026-08-26 火龙 V9-V15 实测，血泪）

1. **不能靠拉 volume 救静音 BGM**：`环境音与轻BGM_43s.wav` mean=-44.9dB，volume=50 放大后底噪一起放大变成噪音，用户「不知道什么东西跟噪音一样」——**静音 BGM 直接换源，不拉 volume**
2. **不能从成片减人声提取 BGM**：V19_BGM 减去 V19 原版想得纯 BGM，但两版人声文案不同，减出来混了人声，用户「傻逼把配音给提取了」——**不同文案版本不能相减**
3. **BGM 库在广州机不在本机**：用户问「不是有BGM库？」时先查广州机 `/home/ubuntu/assets/bgm/`，不要在新加坡机本地找不到就说没有
4. **amix weights 控制比例**：`weights='2 1'` = 人声是BGM的2倍，BGM在背景不盖人声；`normalize=0` 防止 amix 自动压低音量

## 选曲（2026-08-26 更新）

- **首选：广州机 BGM 库** `/home/ubuntu/assets/bgm/`（29首 mixkit MP3，scp 拉到本机即可用，推荐 mixkit_834）
- 免费商用备选：SoundHelix（curl 直下无限制）：`curl -sL -o bgm_raw.mp3 https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3`
- 推广/快节奏广告 = 轻快吉他 Song-1/6；情感类 = 舒缓钢琴 Song-2/7（分类见 wiki/concepts/bgm-library.md）
- 截取 + 淡入淡出：`ffmpeg -i bgm_raw.mp3 -t 43.8 -af "afade=t=out:st=38.8:d=5" -ac 2 -ar 48000 bgm_43s.m4a`（长度按成片 DUR，fade 终点 ≈ DUR-5）
- 使用前 volumedetect 验证有声（旧项目 BGM 素材 `环境音与轻BGM_43s.wav` 全程 -44.9dB 是哑的，不能用）

## 验证

- 成片整体响度：mean ≈ -13 dB / max ≈ 0 dB（0.3+ducking 实测 -13.1 dB）
- 人声清晰度：faster-whisper medium 转写抽查首/中/尾三句，全通顺 = BGM 没压人声
- 只提音量不压人声（0.13→0.22 都过了转写，但用户听感不够响）——用户听感 > 转写通过
