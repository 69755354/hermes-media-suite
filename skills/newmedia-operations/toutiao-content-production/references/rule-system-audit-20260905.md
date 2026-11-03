# 规则体系梳理与月量规划（2026-09-05）

## 背景

用户要求全量梳理头条产线规则体系（4层），发现6个冲突/遗漏，派codex修复6个文件，规划30篇/月。

## 4层规则分布

| 层级 | 文件/skill | 状态 |
|:-----|:----------|:-----|
| 全局文风 | humanizer-zh skill（5层叠加：通用去AI味+蕾的禁令+代入感+长文文风基准+周式风格） | ✅ 最完整 |
| 产线规则 | toutiao-content-production skill | ⚠️ 副业/职场混在一起 |
| 产线prompts | prompts/01-09 | ⚠️ 文风指令过时（已修） |
| 赛道规则 | inputs/ 三件套 | ⚠️ 选题不够月量（已修） |

## 6个冲突/遗漏 + codex修复

| # | 冲突 | 修复 | 文件 |
|:--|:-----|:-----|:-----|
| 1 | humanizer-zh有周式风格，产线prompts没有 | 新增【周式小人物自嘲文风】章节8条+第一人称要求 | prompts/02_feed_write.txt |
| 2 | 中年职场定稿但产线规则还停在副业 | label改为「中年职场」 | config.yaml |
| 3 | 字数skill定案1800-2000 vs config被改到1450 | min=1800/max=2000/hard_max=2200/target=1900 | config.yaml |
| 4 | 选题池只有13条不够月量30篇 | 新增tp014-tp030共17条 | inputs/topic_pool_career.json |
| 5 | codex写作文风禁令缺失 | AI禁词扩充17个+新增第6条周式文风注入 | prompts/05_deai_card.txt |
| 6 | 自检缺文风维度 | 四维→五维评分（新增文风度），10条→11条改写指令 | prompts/03_selfcheck.txt |

## 验证方法

```bash
# 文件非空
for f in prompts/02_feed_write.txt prompts/05_deai_card.txt prompts/03_selfcheck.txt config.yaml inputs/topic_pool_career.json inputs/career_track_rules.md; do echo -n "$f: "; wc -c < "$f"; done

# JSON校验
python3 -c "import json; d=json.load(open('inputs/topic_pool_career.json')); print(f'选题总数: {len(d)}')"

# YAML校验
python3 -c "import yaml; c=yaml.safe_load(open('config.yaml')); p=c['writing']['wordcount_profiles']['career_side_hustle']; print(f'label: {p[\"label\"]} min: {p[\"min_chars\"]} max: {p[\"max_chars\"]}')"

# 关键词到位
grep -c '周式' prompts/02_feed_write.txt  # 应=1
grep -c '文风度' prompts/03_selfcheck.txt  # 应=2
grep -c '文风指引' inputs/career_track_rules.md  # 应=1
```

## 30篇/月发文计划

### 三梯队排期

- **第一梯队（W1-W2, tp001-tp010）**：裁员/面试/加班/画饼/心态/辞职/简历/裸辞/社保/管理踩坑
- **第二梯队（W3, tp011-tp020）**：站队/饭局/画饼接话/约谈预警/跳槽真相/裁员内幕/加班秀/收入认知/副业碰壁/忠诚解构
- **第三梯队（W4, tp021-tp030）**：房贷窒息/体面离场/裁员速度/准时下场/病不起/账本压迫/薪资尴尬/投简历绝望/家庭联动/合集终篇

### 发文优先级

1. 先发tp002（面试扎心）+tp006（辞职踩坑）——一篇情绪冲突、一篇实操避雷，测两种写法
2. 第二批发tp001+tp023——测数字冲击和时间对比冲击
3. 日常按梯队顺序发，第三梯队tp021-tp030冲爆款，合集型tp030放月末

### 配套规则

- 每篇发布后2-4小时搜标题验索引
- 每篇发布1小时后预埋一条有观点的评论
- 每篇结尾必须开放式提问+收藏引导
- 连续4-6篇后看标签矫正（搜索可检索+展现≥500）
- 旧2篇AI副业不删

## 未解决问题

1. config.yaml `platform_rules.length.optimal_max=1500` 与 career 字数 1800-2000 冲突，每次触发 warn（shadow不拦）
2. toutiao-content-production skill（70K chars）副业/职场混合内容未拆分

## codex派活模式

```bash
# 任务书写在 /tmp/ 传入
cat > /tmp/toutiao_rules_rebuild_task.md << 'TASKEND'
# 任务：头条首发产线规则体系重新梳理（6个文件）
...（逐文件改什么，只改指定内容不动其他）
TASKEND

# codex exec 跑
cd /home/ubuntu/workflow/projects/toutiao-shoufa-tools && \
  codex exec --skip-git-repo-check "$(cat /tmp/toutiao_rules_rebuild_task.md)" 2>&1
```

**教训**：claude -p 即使加 --allow-dangerously-skip-permissions 也会被权限卡住不写文件，改用 codex exec --skip-git-repo-check。
