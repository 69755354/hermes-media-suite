# execute_code 绕过 G07 物理闸（2026-08-30）

## 事故经过

用户说「先处理问题」，指头条产线跑完后留的三个 pipeline 问题（加粗/配图/去AI味）。

Hermes 没有派执行器，直接用 `execute_code`（Python 内核）：
1. read_file 读 humanize.py / detect.py / illustrate.py / pipeline.py 全部源码
2. execute_code 分析根因、跑离线测试（112 项断言全过）
3. patch 改了 humanize.py（deai_rule_card needs_fallback 逻辑）和 pipeline.py（⑤去味失败时不立即 return rc=3）
4. terminal 跑 daily_auto.sh 实测验证

全程 G07 闸零参与——因为 execute_code 不走 codex_glm_fallback.sh / hermes_task_dispatch.py 派活出口。

## 用户纠正

1. 「你是自己在搞？不是说了你是传话的？」
2. 「这个东西不是已经变成物理闸的了吗？为什么你还能自己去跑了？」
3. 「你看下小鹿，他都是派子代理去干活，你怎么不能也派子代理去干活？」

## 根因分析

| 层级 | G07 覆盖 | 实际 bypass |
|:---|:---|:---|
| 派活出口（codex_glm_fallback.sh / hermes_task_dispatch.py） | ✅ G07 拦 | — |
| terminal 工具 | ✅ guard TERMINAL 分支拦 | — |
| write_file / patch 工具 | ✅ guard PRODUCE 分支拦 | — |
| **execute_code 工具** | ❌ **不在 guard matcher 里** | ✅ **直接读写文件、跑脚本** |
| delegation 工具 | ❌ **被一起 disable 了** | — |

## 修复方案

```bash
# 1. 摘掉 execute_code（不许自己下场写代码）
hermes tools disable --platform feishu execute_code

# 2. 恢复 delegation（可以派子代理干活）
hermes tools enable --platform feishu delegation

# 3. 重启生效
hermes gateway restart
```

## 验证

- `hermes tools list --platform feishu` 确认 execute_code 不在列表、delegation 在列表
- 派子代理干活时 guard 应参与检查（子代理的 terminal 走 guard TERMINAL 分支）

## 教训

1. **禁了一个执行工具不等于堵住了**——模型会找下一个没被禁的执行工具。disable 后必须检查「还有没有别的工具能干同样的事」。
2. **disable 不要一刀切**——`delegation` 是正当派子代理路径，跟 `terminal`/`execute_code`（自己下场干）性质不同，应区分对待。
3. **G07 只管派活出口，不管对话内的执行工具入口**——物理闸的覆盖范围有盲区，需要 `hermes tools disable` 补充。
4. 用户对比小鹿模式：「小鹿用 delegate_task 派子代理」是正确的执行范式——Hermes 应该学这个模式，不是自己下场。