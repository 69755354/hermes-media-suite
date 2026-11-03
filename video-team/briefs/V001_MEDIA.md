# 任务书 V001 · 生成

- 片名：测试片
- 批次：-   账号：-
- 承接：视频组（独立执行器（Codex/DS 壳 + 出片脚本））
- 交付物：素材/片段

## 上游输入
- 分镜：/home/ubuntu/build/hermes-media-suite/video-team/work/V001/STORYBOARD/STORYBOARD_artifact.txt（dispatch 0.0s）

## 验收标准（逐条可判定，缺一不可）
1. 按分镜逐镜生成，不缺镜、不重复镜
2. 人物外观跨镜一致
3. 单镜失败只重生成该镜，不重跑全片

## 流程约束
1. 本阶段只交付「素材/片段」，不越界做下游的事
2. 本阶段允许付费生成，上限 6 次，超出即停并挂 blocked
3. 产出物写到 /home/ubuntu/build/hermes-media-suite/video-team/work/V001/MEDIA，结尾一行 OUTPUT: <绝对路径>
4. 缺信息输出 NEED_INFO（列待确认项，不阻塞交付），不合规输出 COMPLIANCE，做不了输出 BLOCKED 并写明原因与下一处理者
5. 不要直接向用户汇报，结果交回团长

## 待确认项
- 交付时列出；没有则写「无」
