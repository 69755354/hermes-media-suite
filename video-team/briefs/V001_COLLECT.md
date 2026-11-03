# 任务书 V001 · 取数

- 片名：测试片
- 批次：-   账号：-
- 承接：数据组（发布助手 + 数据脚本）
- 交付物：数据表

## 上游输入
- 发布：/home/ubuntu/build/hermes-media-suite/video-team/work/V001/PUBLISH/receipt.txt（dispatch 0.0s）

## 验收标准（逐条可判定，缺一不可）
1. 两个号分别取数，缺号跳过并说明
2. 20 列老板表格式
3. 数字来自后台原始数据，不许估算

## 流程约束
1. 本阶段只交付「数据表」，不越界做下游的事
2. 本阶段禁止任何付费生成与对外发布动作
3. 产出物写到 /home/ubuntu/build/hermes-media-suite/video-team/work/V001/COLLECT，结尾一行 OUTPUT: <绝对路径>
4. 缺信息输出 NEED_INFO（列待确认项，不阻塞交付），不合规输出 COMPLIANCE，做不了输出 BLOCKED 并写明原因与下一处理者
5. 不要直接向用户汇报，结果交回团长

## 待确认项
- 交付时列出；没有则写「无」
