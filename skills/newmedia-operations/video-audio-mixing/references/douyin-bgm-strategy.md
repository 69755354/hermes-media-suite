# 抖音发布端 BGM 适配方案

> 与 SKILL.md 第5节互补。本文件是完整策略细节，SKILL.md 是摘要。
> 生产端混音（TTS调参/BGM选曲/音轨替换）见 SKILL.md 第1-3节。

## 核心现实

抖音有自己的音乐库，但API/服务器自动化拿不到抖音曲库，只能本地预处理视频再上传抖音。

## 方案A：视频不带BGM，上传后抖音APP内加音乐（最推荐）

**优点：**
- 直接使用抖音正版曲库几十万首，完全没有版权风险，不会限流/下架/扣分
- 支持自动「人声增强、音乐闪避」——人说话时BGM自动变小，效果比FFmpeg侧链压缩好很多
- 不用囤积大量本地音乐文件，不会BGM重复

**缺点：**
- 不能完全服务器自动化，上传后需手动选曲，流水线断一步

**操作流程：**
1. Seedance输出原始带人声的视频
2. 质检完成（FFmpeg抽帧+vision检查人脸/字幕BUG）
3. 不叠加任何BGM直接导出mp4
4. 上传抖音
5. 发布页「添加音乐」选曲
6. 把音乐音量调到 **10-20**（必须压低，保证人声清晰）

**重点**：抖音里音乐音量不要超过20。很多人直接用默认音量，人物口播被BGM盖掉，完播率暴跌。

## 方案B：服务器本地提前混好BGM再上传（全自动，需把控版权）

**适合**：追求100%流水线跑完，导出成品直接上传。

**版权风险：**
- 抖音审核很严，网上随便扒的抖音音乐不能直接打包进视频
- 判定版权侵权：限流、视频下架、账号扣分

**安全可用的本地BGM来源（0826两轮实测）：**

| 来源 | 服务器可自动化 | 授权 | 备注 |
|:---|:---|:---|:---|
| Incompetech (Kevin MacLeod) | ✅ 直链 | CC BY 3.0（署名商用） | 已囤56首在COS |
| Internet Archive | ✅ 搜索API+下载 | CC BY 3.0/4.0 + CC0 | 已囤59首在COS |
| Pixabay / Pexels | ❌ Cloudflare/403 | CC0 | 服务器不可用，别浪费时间 |
| Bensound | ❌ 全变付费 | - | CDN直链也403 |
| FreePD | ❌ 关站 | CC0 | 已永久关闭 |
| FMA | ✅ 但无CC BY可商用 | 混合 | 850首cinematic全CC BY-NC/ND/SA |
| mixkit | ✅ 已囤本地 | 免费商用 | 29首在广州机 |
| 爱给网/曲多多 | 需买授权 | 商用授权 | 国内站从服务器超时 |

**禁止**：下载抖音别人视频的背景音乐扒出来复用，属于侵权。

**FFmpeg混音命令（沿用现有脚本）：**

```bash
ffmpeg -i 原视频.mp4 -stream_loop -1 -i bgm.mp3 \
  -filter_complex "[1:a]volume=0.18[a];[0:a][a]amix=inputs=2:duration=shortest[aout]" \
  -map 0:v -map "[aout]" -c:v copy out_with_bgm.mp4 -y
```

**参数对照（与SKILL.md第2节一致）：**
- `stream_loop -1`：BGM比视频短时循环
- `volume=0.15-0.18`：BGM音量压到15-18%
- `amix weights='2 1'`：人声权重2倍于BGM（更稳的写法）
- `normalize=0`：不做自动归一化（会压人声）

## 发抖音本地混BGM的坑

1. **不要带歌词！** 漫剧口播，带歌词BGM会和人声打架，听感很差；全部选纯音乐伴奏
2. **音量BGM一定要低**，15-20%，口播台词第一位
3. 即使是免费BGM，个别音乐抖音库没有收录，仍有小概率触发版权提示

## 最优工作流（兼顾自动化+抖音版权）

```
Seedance生成视频
    ↓
FFmpeg抽帧 + vision质检（人脸、字幕BUG）
    ↓
输出【无背景音乐】纯净人声版mp4
    ↓
上传抖音网页端/抖音开放平台API上传接口
    ↓
在抖音端选择平台正版BGM → 音量10-20 → 发布
```

如果追求100%全自动：用方案B，本地囤一批CC0无版权纯音乐（115首已传COS `sc/bgm/cc0/`）。但依然有极低概率版权命中。

## BGM库清单

| 库 | 位置 | 数量 | 风格 | 授权 |
|:---|:---|:---|:---|:---|
| Incompetech + IA CC0/CC BY | COS `sc/bgm/cc0/` | **115首** | 叙事/氛围/cinematic/悬疑/古典/电子 | CC BY 3.0/4.0 + CC0（署名商用） |
| mixkit | 广州机 `/home/ubuntu/assets/bgm/` | 29首 | 现代节奏/电子 | mixkit License（免费商用） |

### Incompetech 已下载曲目（56首）

the_descent, anguish, long_road_ahead, apprehension, anxiety, slow_burn, faceoff, achaidh_cheide, all_this, bama_country, bossa_antigua, chee_zee_beach, chee_zee_cave, chee_zee_jungle, chee_zee_lab, cool_vibes, floating_cities, future_gladiator, hard_boiled, heavy_heart, hitman, investigations, lobby_time, mystic_force, past_the_edge, rollin_at_5, royal_banana, sneaky_adventure, sneaky_snitch, sonatina, take_the_lead, the_builder, the_cannery, the_entertainer, the_path_of_the_goblin_king, thinking_music, wallpaper, whiskey_on_the_mississippi, dreamy_flashback, fluffing_a_duck, bittersweet, blown_away, corruption, despair_and_triumph, drums_of_the_deep, echoes_of_time, egmont_overture, ever_mindful, exotic_battle, finding_the_balance, folk_round, frost_waltz, interloper, jaunty_gumption, juniper, just_as_soon

### Internet Archive 已下载曲目（59首）

主要来自以下item：
- **CinematicMusicPackOne** (CC BY 3.0, Martin Oller): 80s Dramatic Synth Strings, A Hero Has Fallen, Ahaya, All Lies, Almost Alive, Another Place, Beauty of the Desert, Blade Running, Chase Them Down, Dark Strings Of Death, Dont Lose Hope, Dreams, Elves Will Defend Themselves, Harmless Dreaming, Hidden Secret, Holding On, In Hope Of Heroes, Legends, Let Go, Life Has Returned, Now We Are Free, Progressive Guitar Song, Remember You, Rise Again, So Cold, Soft Guitar Loop, Stay, System Intrusion A/B, The Gods Will Forgive Us, There Is Still Hope, They Found It On The Moon, Vanora's Theme, What Is The Same
- **FreeRoyaltyFreeMusic** (CC BY 3.0): Believe In Yourself, Confident Session, Epic Industrial Action Trailer, Epic Orchestra Soundtrack, Fast Energetic Story Stepper, Free And Lucky, Joker, Light As A Feather, Powerful Orchestra Score, Summertime Happiness, The Cute One, Think Positive, This Is Epic, War Trailer Intro A/B, Whats Up In The Club, Yes We Can Do That
- **DanielIvan** (CC BY 4.0): A fact, Be Alone, Calm as light, Two of them
- **Bonnot CC0**: 1312, 161, Aggression

下载日期：2026-08-26 | 全部ffprobe验证通过

## Internet Archive 下载方法详解

### 搜索API

```
https://archive.org/advancedsearch.php?q=collection:opensource_audio+AND+subject:cinematic&fl[]=identifier&fl[]=title&fl[]=licenseurl&sort[]=downloads+desc&output=json&rows=100
```

### 筛选可商用license

从返回的 `licenseurl` 字段判断：
- `creativecommons.org/licenses/by/` → CC BY ✅ 可商用
- `creativecommons.org/publicdomain/zero/` → CC0 ✅ 可商用
- `creativecommons.org/publicdomain/mark/` → 公有领域 ✅
- `creativecommons.org/licenses/by-nc/` → CC BY-NC ❌ 非商用
- `creativecommons.org/licenses/by-nd/` → CC BY-ND ❌ 不可演绎
- `creativecommons.org/licenses/by-sa/` → CC BY-SA ⚠️ 可商用但需相同协议

### 获取文件列表

```
curl https://archive.org/metadata/{identifier} → JSON.files[]
```

### 下载URL

```
https://archive.org/download/{identifier}/{filename}
```

**⚠️ 文件名必须URL encode**（`urllib.parse.quote`），含空格/括号不编码会返回0字节不报错。

### 已知的优质IA item

| identifier | 授权 | 曲数 | 说明 |
|:---|:---|:---|:---|
| CinematicMusicPackOne | CC BY 3.0 | 50(35完整版) | Martin Oller，名字即cinematic |
| Free-Royalty-Free-Music-For-Youtube-Videos | CC BY 3.0 | 18 | 适合视频BGM |
| DanielIvanFreeRoyaltyMusic | CC BY 4.0 | 4 | 短曲 |
| musiccollect (Bonnot) | CC0 | 265(选10) | 大量电子音乐 |
| hightechlowlife | 公有领域 | 17 | 赛博朋克风 |
| monster-in-the-closet | CC BY 4.0 | 1166 | 太多，需筛选 |
