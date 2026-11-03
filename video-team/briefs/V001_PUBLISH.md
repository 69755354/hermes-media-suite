# 任务书 V001 · 发布

- 片名：测试片
- 批次：-   账号：-
- 承接：发布组（发布助手（独立进程））
- 交付物：发布回执

## 上游输入
- 合规：/home/ubuntu/build/hermes-media-suite/video-team/work/V001/COMPLIANCE/verdict.txt（dispatch 0.0s）

## 验收标准（逐条可判定，缺一不可）
1. 发布后回读作品列表，标题+时间命中才算成功
2. 未回读命中一律报未确认，不许说已发
3. 账号必须与任务指定一致

## 流程约束
1. 本阶段只交付「发布回执」，不越界做下游的事
2. 本阶段禁止任何付费生成与对外发布动作
3. 产出物写到 /home/ubuntu/build/hermes-media-suite/video-team/work/V001/PUBLISH，结尾一行 OUTPUT: <绝对路径>
4. 缺信息输出 NEED_INFO（列待确认项，不阻塞交付），不合规输出 COMPLIANCE，做不了输出 BLOCKED 并写明原因与下一处理者
5. 不要直接向用户汇报，结果交回团长

## 待确认项
- 交付时列出；没有则写「无」
