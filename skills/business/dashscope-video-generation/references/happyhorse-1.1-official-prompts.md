# HappyHorse 1.1 官方创作教程提示词模板

> 来源：快乐小马官网创作教程（happyhorse.cn → 创作教程）
> 教程地址：钉钉文档「HappyHorse 1.1：更强动态表现力、更高生成一致性、更优视觉质感」
> 抓取日期：2026-08-26
> 文档总字数：4622字，作者：诗茵（ATH事业群-Token Foundry），最后编辑：08-13

## 一、HappyHorse 1.1 能力升级要点

自4月27日发布以来，HappyHorse 1.0 已广泛应用于短剧制作、电商广告、品牌营销、游戏CG等核心内容生产场景。HappyHorse 1.1 围绕以下维度系统升级：
- **动态表现力**：运动建模与时序一致性优化，复杂动作场景更流畅自然
- **主体一致性**：跨镜头角色/物体保持更稳定
- **指令遵循**：提示词理解更精准
- **视觉呈现质量**：画质提升
- **音频表达能力**：声音生成改进

## 二、三种创作模式

| 模式 | 说明 | 对应API模型 |
|:---|:---|:---|
| 参考生视频 | 上传1-9张图，@图片引用，自由组合元素 | happyhorse-1.1-r2v |
| 首帧生视频 | 1张首帧图+文本描述 | happyhorse-1.1-i2v |
| 视频编辑 | 对已有视频二次编辑 | happyhorse-1.0-video-edit |

## 三、平台输入框引导文案

> 上传1-9张图片，自由组合元素，定义精彩互动。
> 例如：参考 @图片1 中的角色形象，她走进了 @图片2 中场景

- 最大输入：5000字符
- 引用语法：`@图片1` `@图片2`（平台UI用@，API用`[Image 1]`）

## 四、平台参数选项

| 参数 | 可选值 |
|:---|:---|
| 模型版本 | HH 1.1（New）/ HH 1.0 |
| 画幅 | 16:9 / 9:16 / 4:3 / 3:4 / 21:9 / 1:1 / 4:5 / 5:4 |
| 分辨率 | 720P / 1080P（V标识=付费） |
| 时长 | 3-15秒（滑块） |
| 生成数量 | 1 / 2 / 3 / 4（2-4需付费） |

## 五、官方提示词模板（三组）

### ① R2V Prompt — 动作因果链写法

> 适用于参考生视频（r2v），强调动作因果和物理逻辑

```
【Core Logic: Cause & Effect Chain】
1. Initiation: Protagonist (Female Student) is cornered. Opponent 1 lunges with a right punch.
2. Reaction & Momentum: Protagonist does NOT just dodge; she uses the opponent's momentum. She sidesteps left, grabbing Opponent 1's wrist to pull him off-balance. Her body rotates with the pull, using centrifugal force.
3. Environmental Interaction: As she spins, her foot kicks a loose chair leg. The chair slides across the floor (friction visible), tripping Opponent 2 who was rushing in.
4. Flow Transition: The spin continues. She releases Opponent 1, who crashes into a desk (wood splinters, papers fly). Her momentum carries her forward over the desk surface (parkour vault).
5. Landing & Reset: She lands on the other side of the desk in a crouch, absorbing impact. Opponent 3 hesitates. She rises smoothly, ready for the next engagement.
Note: Every movement must have a clear physical cause. No floating, no sudden stops without deceleration.

【Visual Style & Camera Sync】
Style: Gritty Realism, High-Budget Action Cinema. Natural light, dust motes, sweat, worn textures.
Camera: "Physical Participant" perspective.
- When she pulls Opponent 1, camera whips LEFT to follow the rotation.
- When the chair slides, camera tilts DOWN to track the obstacle.
- When she vaults, camera BOOMS UP rapidly to match her vertical leap.
- Handheld shake matches the intensity of impacts.
- Foreground obstruction: Desks and arms frequently block the lens briefly to enhance depth and chaos.

【Character & Environment Details】
Protagonist: Agile, wearing standard Japanese high school uniform (blazer/skirt or tracksuit), hair tied back but loosening. Movements are grounded, feet always interacting with floor friction.
Opponents: Three aggressive males, reacting realistically to pain and balance loss (stumbling, flailing arms).
Environment: Cluttered classroom. Desks are heavy (don't fly like cardboard). Papers swirl in turbulent air currents caused by movement. Sunlight creates dynamic shadows that move with the characters.

【Negative Prompts - Logic Specific】
No teleporting, no instant direction changes without weight shift, no floating limbs, no enemies standing still after being hit, no magical effects, no slow-motion unless specified, no static background, no repetitive loops, no distorted anatomy during rapid motion, no clipping through objects.
```

**结构拆解：**
1. 因果链（Cause & Effect Chain）：每步动作有物理原因，initiation→reaction→environment interaction→flow transition→landing
2. 视觉风格+摄像机同步：定义风格 + 摄像机跟随动作的运镜方式
3. 角色与环境细节：人物穿着/动作质感 + 环境物理属性
4. 负面提示词：按逻辑维度排除不合理现象

### ② I2V Prompt — 水墨武侠多镜分镜写法

> 适用于图生视频（i2v），按镜头号写分镜，每镜含画面/构图/动作/风格

```
白衣女侠竹林激战，水墨武侠巅峰对决 白衣女侠VS黑衣人

【镜1：远景·起风】
画面：远山淡墨晕染，万亩翠竹横斜，风过竹梢，竹叶翻卷如浪，天地间只剩青黑两色。
构图：高远留白，竹枝占画面2/3，底部空寂。
动作/氛围：静中藏杀，风动预示杀机。
字幕/音效：竹叶簌簌，风声渐紧。

【镜2：中景·侠影入林】
画面：白衣女侠踏竹而来，衣袂翻飞如白鹤掠影，剑尖轻点竹尖，墨线勾勒身形，发丝随风扬。
构图：侧影入画，人与竹交错，线条利落飘逸。
动作：脚尖点竹，轻身落地。
风格：白衫为留白，竹为淡墨，对比干净。

【镜3：近景·杀机现】
画面：一道黑影从竹影深处窜出，黑袍如墨，只露一双冷目，手中短刀寒芒一闪（极简留白）。
构图：黑影藏于竹荫，半遮半掩，压迫感强。
动作：黑衣人突袭，刀风破风。

【镜4：特写·剑刃相交】
画面：女侠长剑横挡，黑衣人短刀劈下，兵刃相撞，溅出一缕淡墨气劲（无金属光，以墨晕代火花）。
构图：特写两刃交错，画面居中，张力拉满。
风格：浓墨刀、淡墨剑，线条硬挺。

【镜5：中景·腾挪闪避】
画面：女侠旋身退开，竹枝被刀风斩断，断竹斜飞，她足尖踩断竹梢，身形凌空。
构图：动态斜线，打破平衡，水墨飞白表现速度。
动作：凌空回身，剑指黑衣人咽喉。

【镜6：俯镜·竹林围杀】
画面：自上而下俯瞰，翠竹如墨线交织，白衣一点，黑衣人环伺成围，黑白对峙。
构图：对称压迫，留白与密竹形成呼吸感。

【镜7：近景·女侠出剑】
画面：女侠眼神清冷，墨线勾勒眉眼，无多余表情，手腕一转，剑如白蛇出洞，直刺黑影。
构图：面部特写+剑势延伸，写意不写实。

【镜8：动态·竹雨纷飞】
画面：双人格斗，竹叶被气劲掀起，漫天竹叶如墨雨纷飞，人影在竹雨中虚实交错。
构图：模糊边缘，重意不重形，水墨晕染动感。
风格：动静合一，似舞似战。

【镜9：定格·胜负分】
画面：女侠剑尖停在黑衣人咽喉前，黑衣人定身不动，风停，竹叶缓缓飘落。
构图：静态对峙，留白充足，侠气尽显。
收尾：墨色渐淡，余韵悠长。
```

**结构拆解：**
- 镜号+景别+标题
- 每镜四要素：画面 / 构图 / 动作 / 风格
- 从远景起势→中景入画→近景杀机→特写交锋→中景闪避→俯镜全览→近景出剑→动态混战→定格收尾

### ③ T2V Prompt — 纯文本英文一段式

> 适用于文生视频（t2v），一段式描述

```
A professional ballet dancer performs a powerful grand jeté leap across a dimly lit stage, arms outstretched, legs split perfectly in mid-air. The camera follows her in slow motion as she spins into a series of rapid fouettés, tutu flowing dramatically. Spotlights cast long shadows. Cinematic, full-body shot, 10 seconds, ultra HD, dynamic motion blur.
```

**结构拆解：**
主体（ballet dancer）+ 动作（grand jeté leap + fouettés）+ 运镜（slow motion follows）+ 环境（dimly lit stage, spotlights）+ 规格（Cinematic, full-body shot, 10 seconds, ultra HD, dynamic motion blur）

## 六、提示词写法总结

| 维度 | R2V（参考生） | I2V（图生） | T2V（文生） |
|:---|:---|:---|:---|
| 核心结构 | 因果链+视觉风格+角色环境+负面词 | 镜号+画面+构图+动作+风格 | 主体+场景+运动+运镜+规格 |
| 语言 | 英文 | 中文 | 英文 |
| 复杂度 | 最高（5段式） | 中（分镜式） | 最低（一段式） |
| 适用场景 | 复杂动作/打斗/物理交互 | 多镜头叙事/风格化创作 | 简单纯粹的运动/表演 |
| 摄像机 | 需写明跟拍/俯拍/boom等运镜 | 每镜写景别即可 | 写明运镜方式 |

## 七、平台商业模式

- 新人特惠：¥6.6 = 200积分 = 11次视频生成
- 积分制付费
- 虎鲸文娱集团旗下产品
- 有「HH全球AI影像创作大赛」百万商单+30万奖金+张纪中共创
- 平台URL: https://www.happyhorse.cn/
- API接入: https://bailian.console.aliyun.com/
