# 四视图/展示图生成（人物参考卡）

## 两个版本

| 版本 | 模板文件 | 用途 |
|:----|:---------|:-----|
| 小鹿专用 | `templates/character-sheet-xiaolu.md` | 带固定穿搭（白色细吊带+碎花短裙+裸色凉鞋） |
| 通用版 | `templates/character-sheet-generic.md` | 无固定服装描述，男女通用，自动继承参考图穿搭 |

## 使用方式

1. 上传参考图到ARK拿file ID：POST /api/v3/files → purpose=user_data
2. 图生图：--ref_url "file-xxx" 模式 + 对应模板的正向/负向prompt
3. 尺寸：2560x1440（16:9，需满足最低368.64万像素）
4. **负向词必须同步传**（用户2026-07-21纠正）

## 已知坑点

- Seedream 4.5 图生图锁不住穿搭/发型细节，即使prompt写了全套穿搭，输出仍可能跑偏
- 重绘幅度0.28~0.32是即梦等工具的参数，Seedream API无此参数
- 每次换参考图前先问用户，不要擅自换图重试
