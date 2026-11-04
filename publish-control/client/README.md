# 漫剧发布助手 Windows

发布成功以本次平台创建接口的 HTTP 200、业务状态成功和有效作品 ID 为准；页面历史文字不作为成功依据。页面出现明确失败信号时，失败优先于没有作品 ID 的成功信号。提交请求与本次上传的 creation_id/video_id 不一致时保持未知并冻结，不记发布成功。

安装包不包含任何私钥、会话凭据或中继登录密钥。远程支持只有在服务商于部署阶段把本机专属的受限密钥与连接配置导入本地数据目录后才会启用；未导入时显示“远程支持未启用”，发布、授权和本地面板均照常工作。

安装入口 `bootstrap.bat`；机器码 `show-machine-code.bat`；授权 `import-license.bat`；自检 `selftest.bat`。未安装 Chrome 时，可双击包内 `chrome-offline/ChromeStandaloneSetup64.exe` 安装官方原版。
