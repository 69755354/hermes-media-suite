# Claude Code 远程通道（广州机小鹿审查架构用）

> 2026-08-10：小鹿（广州机）需要远程调用新加坡机 Claude Code 做**架构审查**（独立于 codex 的第二意见）。
> Claude Code 不是 codex 替代，是**补充通道**——codex 写架构，Claude 审架构。

## 安装（新加坡机已完成）

```bash
npm config set prefix ~/.npm-global   # 全局装到用户目录（/usr/lib 无权限）
npm install -g @anthropic-ai/claude-code
export PATH="$HOME/.npm-global/bin:$PATH"   # 已写入 ~/.bashrc
claude --version   # 2.1.226
```

## Bedrock 认证配置（AWS Bedrock API key 方式，官方文档确认）

**关键发现**：Claude Code 默认连 api.anthropic.com 只认 Anthropic 直连 key；**Bedrock API key 必须用官方 Bedrock 集成环境变量**：

```bash
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_REGION=us-east-1                    # region 待确认（key 对应 region）
export AWS_BEARER_TOKEN_BEDROCK=<bedrock-api-key>
```

来源：https://code.claude.com/docs/en/amazon-bedrock 的 "Option E: Amazon Bedrock API keys" 段。

其他 Bedrock 认证方式（官方文档）：IAM 凭证（默认 credential chain）/ AWS SSO（`aws login`）/ Mantle 端点（`CLAUDE_CODE_USE_MANTLE=1`，可 `ANTHROPIC_BEDROCK_MANTLE_BASE_URL` 覆盖）。

## 远程调用包装（~/.hermes/scripts/claude_remote_wrapper.sh）

```bash
# 广州机侧：ssh ubuntu@<新加坡IP> "bash ~/.hermes/scripts/claude_remote_wrapper.sh '<任务>'"
# 依赖：key 存 ~/.hermes/claude_bedrock_key（0600，不落盘明文到脚本/env 文件）
# region 存 ~/.hermes/claude_bedrock_region（默认 us-east-1）
# 与 codex 共用 flock /tmp/codex.lock（防 OOM）
flock /tmp/codex.lock bash -c "
    cd \"$WORKDIR\" && CLAUDE_CODE_USE_BEDROCK=1 AWS_REGION=$REGION AWS_BEARER_TOKEN_BEDROCK=$KEY \
    claude -p \"$PROMPT\" --output-format text 2>&1
"
```

## 踩坑（2026-08-10 实测）

1. **`claude` 不认识 `-C` 参数**（那是 codex 的）——用 `cd $WORKDIR` 代替
2. **key 是 base64 编码的**（用户发来的），解码后带 null 字节污染——用 python `re.search(r'BedrockAPIKey.*', s)` 截干净（别用 shell base64 -d + strip）
3. **BedrockAPIKey-tlcl-at- 前缀不被官方 Bedrock Runtime 认**（`Invalid API Key format: Must start with pre-defined prefix`）——tlcl-at 可能是内部/第三方网关格式；若官方端点持续报错，需确认 key 来源的 region/网关（**此坑 2026-08-10 未最终解决，region 待用户确认**）
4. **`Execution error` 无细节**：claude 的 Bedrock 请求失败时只给「Execution error」——查 ~/.claude/projects/-home-ubuntu-workflow/*.jsonl 的 session 日志也未必有 API 错误细节，直接验证 region/模型访问权限
5. 安装后当前 shell 要用全路径 `~/.npm-global/bin/claude`（bashrc 只对新 shell 生效）

## 配置就绪状态（2026-08-10）

- ✅ Claude Code v2.1.226 安装
- ✅ claude_bedrock.env / claude_bedrock_key（0600）/ claude_remote_wrapper.sh 就位
- ⚠️ **key 在 Bedrock 上验证未通过**（region/前缀问题）——待用户确认 key 来源后配置 AWS_REGION 或网关端点
- ⚠️ 未解决前不要当作可用通道汇报「Claude 已能审架构」
