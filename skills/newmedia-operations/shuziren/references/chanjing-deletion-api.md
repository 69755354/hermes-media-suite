# 婵镜删除API参考

## 删除数字人形象

```
POST /open/v1/delete_customised_person
```

**参数：**
```json
{
  "id": "数字人ID",
  "source": 0
}
```

- `source: 0` = API端创建的数字人
- `source: 1` = Web端创建的数字人

**验证返回（2026-07-15）：**
```json
{
  "trace_id": "b6ddf5971d07e66afcde13a2cc5536f9",
  "code": 0,
  "msg": "success",
  "data": "C-22494d1415e14c81bf8d49187a1083b4"
}
```

---

## 删除声纹/声音

```
POST /open/v1/delete_customised_audio
```

**参数：**
```json
{
  "id": "声纹ID"
}
```

**注意：** 如果声纹ID已经被禁用或不存在，返回：
```json
{
  "code": 50000,
  "msg": "该AI语音被禁用或者不存在"
}
```

不会报系统错误，属于正常状态。

---

## 使用场景

**重新克隆前清理旧资产：**
1. 先 `delete_customised_person` 删旧的数字人ID
2. 再 `delete_customised_audio` 删旧的声纹ID（可能已失效，50000 是正常返回）
3. 走完整克隆流程（上传素材→提交训练→等人脸审核）
