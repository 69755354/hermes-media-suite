# 「A 模型跟 B 模型哪个厉害」怎么答（实测法）

用户问编程/写作/分析能力谁强时：**先查可测的接口、再实测同题、最后分层报来源**。禁凭文档断言，禁凭印象。

## 1. 先摸清两台机器的可用模型清单（别假设）

```python
import yaml,json,urllib.request
cfg=yaml.safe_load(open('/home/ubuntu/.hermes/config.yaml'));P=cfg['providers']
for n,p in P.items():
    k=p.get('api_key') or ''
    if not k: continue
    try:
        d=json.loads(urllib.request.urlopen(urllib.request.Request(
          p['base_url'].rstrip('/')+'/models',headers={'Authorization':'Bearer '+k}),timeout=25).read())
        print(n,p['base_url'],[m['id'] for m in d.get('data',[])])
    except Exception as e: print(n,'ERR',e)
```

已知布局：
- `custom_custom` → DeepSeek 官方 `https://api.deepseek.com/v1`，只有 `deepseek-flash` / `deepseek-v4-pro`
- `custom_glm` → 本机 MaaS 网关 `http://127.0.0.1:18890/v1`，**几百个模型**（glm-5.2/glm-5.3/deepseek-v4.1-flash/qwen3.8-max/kimi-k3…）——多个厂商的模型都能从这里调，**做 A/B 对比必须走同一网关才公平**
- 官方文档核对：DeepSeek 2026-09-10 起 `deepseek-flash` 即 V4.1 Flash，`deepseek-v4-pro` 也路由到它（旧 V4 Flash 已下线）。**改模型名前先去 api-docs.deepseek.com/zh-cn/updates 核实**，别按记忆里的旧名字报。

## 2. 同题实测（可判对的题才叫测试）

要点：
1. **两家同题 + temperature=0 + 同 max_tokens + 同一网关**，否则不算对比
2. 题目必须**可客观判分**：给隐藏测试用例，而不是看谁写得“好看”。好题例：RFC4180 CSV 解析、`posixpath.normpath` 等价实现（拿标准库当答案对）、埋 bug 求和函数
3. **`reasoning_content` 陷阱**：重思考模型会把 `content` 留空、把额度烧在 reasoning 上（实测 deepseek-v4.1-flash 在一道 CSV 题上 8000 token 全是 reasoning、`text_tokens: 0`、零输出）。跑测试要么给 20000+ 预算，要么显式 `"enable_thinking": false`（网关支持，实测让两家都在 1.6–3.1 秒回代码）
4. 看 `usage.completion_tokens_details.reasoning_tokens` 才知道它是真的在思考还是跑飞了
5. 题不能太简单——太简单两家都满分、区分不出来（埋 bug 题两家都秒修）。要加一道有冷门边界的题

## 3. 报结论必须分层（用户明确要求）

| 层 | 写什么 |
|:--|:--|
| 我们实测 | 同网关同题得分/耗时/token，含双方都错的那一题 |
| 厂商自报 | 各自发布会表格（互相吹，**只在自家表里领先**）——标明是自报 |
| 独立评测 | Artificial Analysis 智能指数等；注明该模型**有没有**公开总分 |
| 版本陷阱 | 同名 benchmark 跨版本不可比（DeepSWE v1.0 vs v1.1）、脚手架不同结论就不同（“harness is the benchmark”）|

## 4. 2026-09 实测存档（GLM-5.2 vs DeepSeek V4.1 Flash）

同网关、同题、temp=0、关思考：
- CSV 解析 10 例：**各 10/10 打平**
- 路径规范化 12 例：**各 11/12 打平**（双方都错同一个 `//a//b` → POSIX 保留双斜杠的冷门规则）
- 耗时：DS 1.6–2.0s / GLM 2.8–3.1s；埋 bug 题两家都秒修且改法相同
- 默认思考模式下：DS 在同一道 CSV 题跑满 8000 token 全思考、零输出（59s）；GLM 把 2500 预算全花在思考上

文档层：GLM-5.2 SWE-bench Pro 62.1 / Terminal-Bench 2.1 81.0 / AA 智能指数 51；DeepSeek V4 Flash(0731) AA 50，但 DS 自家表全面压 GLM-5.2（Terminal-Bench 82.7、DeepSWE 54.4 vs 46.2）；V4.1 Flash 官方只报 DeepSWE v1.1 74.2、AA 无总分。**结论：同一档，DS 略强且便宜 3–6 倍；要 GLM 就用 glm-5.3（AA 57）而不是 5.2。**
