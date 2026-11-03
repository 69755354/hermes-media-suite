# 婵镜凭证管理（双APP_ID + 阻塞锁）

## 已知凭证

| APP_ID | Secret Key | 用途 | 数字人资产 |
|:-------|:-----------|:------|:-----------|
| `d01ef4c6` | <CHANJING_SECRET> | 杨荟数字人原始账号 | 杨荟数字人 + 声纹 + 公共音色 |
| `d6fda3b0` | <CHANJING_SECRET_2> | 当前主密钥（新账号） | 无数字人资产 |

## source 参数

- `source=0` — API端创建的数字人/资源
- `source=1` — Web端创建的数字人/资源

杨荟数字人 `C-847f4770c2914b2cb91cb7658eabee7f` 在APP_ID `d01ef4c6` 下，需用 `source=0` 调用。

## 通道隔离

- 婵镜通道（shuziren）：三重校验 → 阻塞锁 → 解锁后才渲染
- Seedance通道（huoshan）：跳过所有数字人校验，无锁直出

## 公共音色（APP_ID: d01ef4c6）

| 名称 | ID | 性别 |
|:-----|:---|:----:|
| 带货小芸 | f9248f3b1b42447fb9282829321cfcf2 | female |
| 方言口音老奶奶 | f5e69c1bbe414bec860d... | female |
| 直爽小哥 | f4ca217d61f247fbbe0b... | male |
| 科普女声 | c4fcaa1d583349178981 | female |
| 激动女声 | C-CASE-ef449e20271e4... | female |

## 阻塞锁

| 锁标识 | 触发条件 | 解锁关键词 |
|:-------|:---------|:-----------|
| render_block_account_mismatch | APP_ID不匹配 | 选1、切换原密钥、方案1 |
| render_block_no_human | 无数字人ID | 选1克隆、选2公共数字人 |

锁标记=1时终止API请求，不计费。仅显性关键词解锁，反问/质疑不解锁。
