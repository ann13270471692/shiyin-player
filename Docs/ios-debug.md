# 在 Windows 上调试这个 iOS App（无 Mac）

## 结论先说

- **xtool 不能在这台机器上编译本工程。** xtool 1.22.2 的 release 只有 Linux AppImage 和 macOS .app，没有 Windows 版；
  它靠 `xtool sdk install <Xcode.xip | Xcode.app | darwin.xtoolsdk>` 装 Darwin/iOS SDK——**SDK 必须从装过 Xcode 的机器提取**，
  Linux/WSL 上没有可下载的 iOS SDK。WSL 里连 Swift 工具链都要 `sudo apt install swiftlang`（535 MB），装完也仍然没有 UIKit 可用。
- **xtool 也不能在 iOS 17+ 上启动/调试 App**（上游 issue #44 未修：libimobiledevice 缺 RemoteXPC 通道），
  官方建议改用 pymobiledevice3。所以「xtool 联机调试」这条路目前是断的。
- **能用的联机诊断是 pymobiledevice3**（已装好，iPhone 16 / iOS 18.5 实测通过）：日志、崩溃报告、App 列表不需要管理员；
  真·断点调试需要管理员开 RemoteXPC 隧道 + 手机打开发者模式。

## 1. App 内「诊断日志」（1.0.13 起）

1. 电脑跑同步服务器（已带 `/devlog` 接收端）：
   `python SyncServer\sync_server.py "F:\DeepSeek Workspace\时事分析\音乐集合" 8450`
2. 手机装 1.0.13（`build\iOS-1.0.13.ipa`，Sideloadly 侧载）。
3. 导入页 → 已连接状态条上点 **「诊断」** → 日志（最近 5000 行环形缓冲）POST 到电脑，
   落在 `SyncServer\devlog\<设备名>-v<版本>-<时间>.txt`。
4. 已埋的点：`manifest ok/FAIL`（列表读取）、`download begin/end`、`dl FAIL <文件名>`（单首 4 次重试后失败）。
   以后加一行只要 `DebugLog.shared.log("...")`，同时进 os_log / 沙盒文件 / 环形缓冲。
5. 电脑端读日志：`Get-ChildItem SyncServer\devlog | Sort LastWriteTime | Select -Last 1 | %{ Get-Content $_.FullName -Tail 60 }`

## 2. 系统日志 / 崩溃报告（不需要管理员）

助手脚本 `F:\Temp\iosdiag.ps1`（`$bid` 要写手机上真实的 bundle id，Sideloadly 会加团队后缀，
如 `com.shiyin.player.KT8LK3M78B`）：

```powershell
& F:\Temp\iosdiag.ps1 list      # 确认连着机（usbmux list）
& F:\Temp\iosdiag.ps1 apps      # 列 App，拿真实 bundle id
& F:\Temp\iosdiag.ps1 logs      # syslog live，复现问题的同时看实时日志
& F:\Temp\iosdiag.ps1 crashes   # 拉崩溃报告到 F:\Temp\ios-crash
python F:\Temp\ipsparse.py <那个 .ips>   # 解析异常/终止原因/崩溃线程栈
```

底层就是 `C:\Program Files\Python313\python.exe -m pymobiledevice3 …`（3.14 装不上，必须用 3.13）。

## 3. 真·联机调试（需要管理员，你自己开一个管理员 PowerShell）

```powershell
# 1) 手机：设置 → 隐私与安全性 → 开发者模式 → 打开（重启后保持连接）
# 2) 管理员 PowerShell：起 RemoteXPC 隧道（会弹 UAC）
& 'C:\Program Files\Python313\python.exe' -m pymobiledevice3 remote start-tunnel
#   它会打印类似 rd0 iface 和 IPv6 地址，记下
# 3) 普通 PowerShell：用隧道地址做 DVT 操作
& 'C:\Program Files\Python313\python.exe' -m pymobiledevice3 developer dvt launch com.shiyin.player.KT8LK3M78B --attach-stdout
# 断点级调试：debugserver + lldb（lldb 随 Swift for Windows 工具链安装）
& 'C:\Program Files\Python313\python.exe' -m pymobiledevice3 developer debugserver start-server --path /var/containers/Bundle/Application/…/Shiyin.app/Shiyin
```

前提：App 要有 `get-task-allow`（Sideloadly 重签默认会加）。

## 4. usbipd-win（可选，把 iPhone 直通进 WSL）

只有当你想在 WSL 里跑 libimobiledevice/usbmuxd 才需要；对 xtool 没帮助（缺 SDK）。

```powershell
winget install usbipd
usbipd list                       # 找到 Apple USB Devices 的 BUSID
usbipd bind --busid <BUSID>       # 管理员
usbipd attach --wsl --busid <BUSID>
```
WSL 内再 `sudo apt install usbmuxd libimobiledevice-utils`，`idevice_id -l` 应能看到 UDID。

## 5. 已知崩溃（1.0.7 报告，1.0.13 未改）

`Shiyin-2026-10-14-082000.ips`：`EXC_CRASH/SIGKILL`，`0x8BADF00D`，
`scene-update watchdog transgression … exhausted real (wall clock) time allowance of 10.00 s`。
栈在 `CoreText TStorageRange::GetNextUnmappedGlyphRange ← CTLineCreateWithAttributedString ←
SwiftUI ResolvedStyledText.StringDrawing.draw ← CA::Transaction::commit ←
-[UIApplication _createSnapshotContextForScene:]`——**切后台/多任务快照时主线程排版超 10 秒被系统杀掉**，
不是代码逻辑崩溃。诱因是导入页一次渲染上万行长文本。可选修法：导入列表分页（每次 300 行 + 「加载更多」）、
行内文本 `lineLimit(1)` 已有、必要时给列表行加 `.id` 稳定复用。
