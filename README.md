# 拾音（Shiyin）— iPhone 本地音乐播放器

个人自用的本地音乐播放器：MP3 存手机、滚动 LRC 歌词、锁屏控制、局域网从电脑一键拉歌。

**无 Mac 开发**：代码在 Windows 编写 → GitHub Actions（macOS 机器）编译 → Sideloadly 在 Windows 签名安装。

## 目录结构

```
project.yml                 XcodeGen 工程定义（不提交 .xcodeproj，CI 上生成）
Sources/                    Swift 源码
SyncServer/sync_server.py   Windows 电脑上的音乐推流服务器（M3）
.github/workflows/build.yml CI：编译出未签名 Shiyin.ipa
```

## 首次上手（M0 安装链路）

### 1. 建 GitHub 仓库并推送
仓库已在本地提交完毕（main 分支，多个里程碑提交），只需：
```powershell
cd "F:\DeepSeek Workspace\时事分析\shiyin-player"
# 在 github.com 新建一个 public 仓库（public 的 macOS 编译分钟数免费），例如 shiyin-player
git remote add origin https://github.com/<你的用户名>/shiyin-player.git
git push -u origin main
```
首次 push 会弹出 Git 登录窗口（浏览器授权），按提示登录即可。

#### 推送排障（大陆网络常见）
| 现象 | 处理 |
|---|---|
| `Recv failure / Timed out` 连接超时 | 重试 2–3 次；有代理则 `git -c http.proxy=http://127.0.0.1:7890 push -u origin main`（端口换成你的） |
| `403 / Support for password authentication was removed` | GitHub 网页 → Settings → Developer settings → Personal access tokens → **Tokens (classic)** 勾选 `repo` 生成；push 时密码栏粘贴该 token |
| 登录窗口打不开 | 改用 SSH：网页生成 SSH key 后 `git remote set-url origin git@github.com:<用户名>/shiyin-player.git` |

### 2. 等编译完成，下载 IPA
仓库页 → **Actions** → 最新一次运行（绿色 ✓）→ Artifacts 里下载 **Shiyin-unsigned**（解压得到 `Shiyin.ipa`）。

### 3. Sideloadly 签名安装（Windows）
1. 下载安装 [Sideloadly](https://sideloadly.io)；同时安装 Apple「Apple 设备」应用或 iTunes（提供 iPhone USB 驱动）
2. iPhone：设置 → 隐私与安全性 → **开发者模式** 打开；用数据线连电脑并"信任此电脑"
3. Sideloadly 拖入 `Shiyin.ipa` → 填你的 **Apple ID**（就是手机上登录那个）→ Start → 等它签名+安装
4. 手机桌面出现「拾音」，点开即可

### 4. 7 天续期（免费 Apple ID 的限制）
免费账号签名有效期 7 天，到期 App 打不开：**重开 Sideloadly，用同一个 .ipa 再 Start 一次**（1 分钟，App 内已下载的音乐不会丢）。以后可考虑 $99/年 开发者账号，签名一年有效。

## 局域网拉歌（M3）
1. 电脑：`pip install zeroconf`，双击 `SyncServer\启动同步服务器.bat`（首次弹防火墙 → 专用网络允许）
2. 手机与电脑同一 WiFi → App「导入」页自动发现电脑 → 读取列表 → 勾选 → 下载
3. 发现不了就在导入页手动输入服务器窗口里显示的 IP（如 192.168.x.x）

## 开发节奏
- M0 安装链路（本阶段）→ M1 曲库+播放 → M2 滚动歌词 → M3 局域网导入 → M4 打磨
- 每完成一个里程碑：push → CI 出新 IPA → Sideloadly 重装（覆盖安装，数据保留）
