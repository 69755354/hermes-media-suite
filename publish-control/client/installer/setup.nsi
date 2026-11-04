Unicode true
!ifndef PAYLOAD
  !error "PAYLOAD required"
!endif
!ifndef OUTPUT
  !error "OUTPUT required"
!endif
Name "漫剧发布助手"
OutFile "${OUTPUT}"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\Programs\HuolongAgent\publish-assistant-1.2.33"
SilentInstall normal
AutoCloseWindow true
Page instfiles
ShowInstDetails show
SetCompressor /SOLID lzma
Section
  DetailPrint "正在展开漫剧发布助手，请稍候。"
  ClearErrors
  SetOutPath "$INSTDIR"
  IfErrors extract_failed
  File /r "${PAYLOAD}\*"
  IfErrors extract_failed
  DetailPrint "正在完成安装与自动授权，请查看安装窗口。"
  ExecWait '"$SYSDIR\cmd.exe" /d /c ""$INSTDIR\bootstrap.bat""' $0
  IfErrors launch_failed
  IntCmp $0 0 done failed failed
extract_failed:
  System::Call 'kernel32::GetLastError() i .r1'
  MessageBox MB_OK|MB_ICONSTOP "文件展开失败（系统错误 $1）。目标：$INSTDIR。请检查剩余空间、写入权限或文件占用后重试。"
  SetErrorLevel 5
  Quit
launch_failed:
  System::Call 'kernel32::GetLastError() i .r1'
  MessageBox MB_OK|MB_ICONSTOP "无法启动安装窗口（系统错误 $1）。程序：$SYSDIR\cmd.exe；入口：$INSTDIR\bootstrap.bat。请联系服务商。"
  SetErrorLevel 5
  Quit
failed:
  MessageBox MB_OK|MB_ICONSTOP "安装未完成。请保留安装窗口中的原因并联系服务商。日志位于 $LOCALAPPDATA\HuolongAgent\publish-worker\logs\install.log。"
  SetErrorLevel 5
  Quit
done:
  SetErrorLevel 0
SectionEnd
