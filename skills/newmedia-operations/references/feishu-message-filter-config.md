# 飞书机器人系统消息屏蔽配置

## 配置项（已应用到config.yaml）

### display配置（关掉AI生成层的消息）
background_process_notifications: off    # 后台进程通知
busy_ack_detail: false                   # 忙碌确认详情
interim_assistant_messages: false        # 中间助手消息
long_running_notifications: false        # 长时间运行通知
tool_progress: off                       # 工具执行进度
approvals.mode: off                      # 审批弹窗

### SOUL.md约束（已加）
顶部加了一条：仅输出用户提问对应的业务回答，不附加任何前置/后置系统说明

### 消息关键词过滤（config.yaml platforms.feishu下）
message_filters:
  enabled: true
  keyword_blacklist:
    - Gateway shutting down
    - Self-improvement
    - 心跳检测
    - 启动成功
    - 审批请求
    - 任务被中断
