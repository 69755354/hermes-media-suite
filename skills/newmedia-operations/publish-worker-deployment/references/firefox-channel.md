# 火狐通道（已淘汰，2026-10-14）

> **本文件已作废**。火狐通道实测 3 次成 1 次（上传页 1/3 不稳、`Page.goto` 45s 超时），判定为不合格生产通道；Firefox 应用本体 + Playwright 火狐已删除（`~/.Trash/_firefox_removed/`，profile 备份 `profiles/_deleted/douyin-firefox-20261014_1926.tgz`）。
>
> 现役通道：一号 Chrome、二号 WebKit（苹果内核）。固定规则见 `references/publish-ops-rules-20261014.md`。
>
> 保留原因：万一要复建火狐通道，历史排查结论（禁 IPv6 / 关 DoH / 关 http3 均无效）仍有参考价值；但**不要**再拿它当发布通道。
