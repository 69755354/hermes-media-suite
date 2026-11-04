@echo off
chcp 936 >nul
echo 正在关闭息屏、睡眠和屏幕保护...
powercfg /change monitor-timeout-ac 0
powercfg /change monitor-timeout-dc 0
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change hibernate-timeout-ac 0
powercfg /change hibernate-timeout-dc 0
reg add "HKCU\Control Panel\Desktop" /v ScreenSaveActive /t REG_SZ /d 0 /f >nul
reg add "HKCU\Control Panel\Desktop" /v ScreenSaveTimeOut /t REG_SZ /d 0 /f >nul
echo.
echo 完成：这台电脑不会再自动黑屏或睡眠。
echo 如果屏幕仍然黑，检查显示器和视频线，或把 logs 文件夹发给我们。
pause
