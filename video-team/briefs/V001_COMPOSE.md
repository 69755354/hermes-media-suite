# 任务书 V001 · 合成

- 片名：测试片
- 批次：-   账号：-
- 承接：视频组（独立执行器（Codex/DS 壳 + 出片脚本））
- 交付物：成片mp4

## 上游输入
- 生成：/home/ubuntu/build/hermes-media-suite/video-team/work/V001/MEDIA/MEDIA_artifact.txt（dispatch 0.0s）

## 验收标准（逐条可判定，缺一不可）
1. 分辨率 720x1280、帧率与素材一致
2. 字幕不压脸、不超安全区
3. 音轨与画面时长对齐误差 < 100ms

## 流程约束
1. 本阶段只交付「成片mp4」，不越界做下游的事
2. 本阶段禁止任何付费生成与对外发布动作
3. 产出物写到 /home/ubuntu/build/hermes-media-suite/video-team/work/V001/COMPOSE，结尾一行 OUTPUT: <绝对路径>
4. 缺信息输出 NEED_INFO（列待确认项，不阻塞交付），不合规输出 COMPLIANCE，做不了输出 BLOCKED 并写明原因与下一处理者
5. 不要直接向用户汇报，结果交回团长

## 待确认项
- 交付时列出；没有则写「无」
