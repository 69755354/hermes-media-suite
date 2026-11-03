# 角色资产与数字人资产管理

## 资产目录结构

角色资产统一存放在 `/home/ubuntu/assets/characters/` 下。
门店信息存放在 `~/wiki/assets/shops/` 下（原 `~/wiki/shop-info/` 已迁移）。
数字人资产存放在 `~/wiki/assets/digital-humans/` 下。

## 角色命名规范

`{角色名拼音}_{风格}.{扩展名}`

| 文件 | 说明 |
|:----|:------|
| `xiaolu_caiqian.png` / `.b64` | 彩铅三视图（火山通道用） |
| `xiaolu_real.png` / `.b64` | 真人写实三视图（婵镜通道用） |
| `guoxiang_caiqian.png` / `.b64` | 彩铅三视图（火山通道用） |
| `guoxiang_real.png` / `.b64` | 真人写实三视图（婵镜通道用） |

## 门店资产规范

`~/wiki/assets/shops/<客户名>.md`，含门店信息、套餐价格、合规红线。

## 数字人资产规范

`~/wiki/assets/digital-humans/<人物名>.md`，含数字人ID、声纹ID、参数模板。

## 保存规则

1. 新角色：保存 `.png` + `.b64` 到 `assets/characters/`
2. 新门店：写入 `wiki/assets/shops/`
3. 新数字人：写入 `wiki/assets/digital-humans/`
4. 不要在根层 `wiki/shop-info/` 存放（已废弃）
