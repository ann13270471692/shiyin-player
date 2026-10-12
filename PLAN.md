# 「拾音」iPhone 本地音乐播放器 — 开发规划

> 个人自用 ｜ iPhone 16 (iOS 18) ｜ SwiftUI 原生 ｜ 无 Mac 开发环境
> 状态：**规划已确认，待开始 M0**

## 1. 产品定义（MVP 范围）

| 模块 | 内容 | 优先级 |
|------|------|--------|
| 曲库 | 扫描 App 内 `Documents/Music/` 下的 MP3/M4A/FLAC；列表展示（标题/歌手/时长）；搜索；按标题/歌手/时长排序 | P0 |
| 播放 | 播放/暂停/上一首/下一首、随机、单曲循环/列表循环、进度条拖动；断点续播（每首记住上次位置） | P0 |
| 锁屏控制 | 锁屏与控制中心显示曲名/歌手/封面，支持播放暂停切歌（MPNowPlayingInfoCenter + MPRemoteCommandCenter）；后台播放 | P0 |
| 滚动歌词 | 卡拉OK式逐行高亮滚动，当前行居中放大，点击任意行跳转进度；无 LRC 时显示"暂无歌词" | P0 |
| 局域网导入 | App 内自动发现电脑上运行的同步服务器，列出音乐集合，勾选下载到手机（带进度、断点续传、已存在跳过）；无需数据线 | P0 |
| 备用导入 | 开启 iTunes 文件共享，Windows 上用「Apple 设备」/iTunes 直接拖文件进 App（离线兜底） | P1 |
| 暂缓 | 歌单、收藏、睡眠定时、变速、均衡器、封面墙 | 以后加 |

歌词数据源（我们已备齐）：优先读同名 `.lrc` 侧车文件；没有则解析 MP3 内嵌 ID3 USLT（19 首两种都有）。

## 2. 技术架构

### 2.1 App 端（SwiftUI, iOS 17+ 部署目标, arm64）
```
shiyin-player/
├── project.yml                  # XcodeGen 配置（CI 上生成 .xcodeproj，不手写 pbxproj）
├── Info.plist                   # 后台音频、本地网络权限、Bonjour、ATS 局域网放行
├── Sources/
│   ├── App/ShiyinApp.swift      # 入口，TabView：曲库 / 播放 / 导入
│   ├── Models/Track.swift       # 曲目元数据 + JSON 缓存（Codable）
│   ├── Library/LibraryStore.swift    # 扫描 Documents/Music，mtime 增量刷新
│   ├── Library/ID3Parser.swift  # 迷你 ID3v2 解析器（USLT 歌词 / TIT2/TPE1 / APIC 封面）
│   ├── Lyrics/LRCParser.swift   # LRC 解析（含毫秒、多时间戳标签）
│   ├── Playback/PlayerEngine.swift  # AVPlayer 封装 + AVAudioSession + 远程命令 + 队列
│   ├── Views/LibraryView.swift  # 列表/搜索/排序
│   ├── Views/NowPlayingView.swift   # 封面+进度+控制
│   ├── Views/LyricsView.swift   # 滚动歌词（ScrollView + TimeObserver 驱动）
│   └── Sync/SyncBrowser.swift   # NetServiceBrowser 发现 _shiyin._tcp
│       Sync/SyncDownloader.swift # URLSession 下载队列（Range 续传、进度）
├── SyncServer/sync_server.py    # Windows 电脑上运行的音乐推流服务器
└── .github/workflows/build.yml  # macOS runner 编译 → 未签名 .ipa artifact
```

关键决策：
- **存储**：`Documents/Music/`，`UIFileSharingEnabled=YES` + `LSSupportsOpeningDocumentsInPlace=YES` → 局域网下载和 iTunes 拖拽写同一目录，App 扫描同一目录。
- **元数据**：AVFoundation 读 title/artist/封面；读不到时按 `NN - 歌手 - 标题` 文件名规则解析（我们的命名正好符合）。
- **歌词同步**：`addPeriodicTimeObserver(0.25s)` 驱动当前行索引；SwiftUI 用 `ScrollViewReader.scrollTo` 居中，当前行放大+主色，其余渐隐。
- **后台播放**：`UIBackgroundModes=audio` + `AVAudioSession(.playback)`；处理中断（来电）与耳机拔出。
- **局域网发现**：mDNS/Bonjour。Info.plist 声明 `NSBonjourServices=[_shiyin._tcp]` + `NSLocalNetworkUsageDescription`；ATS 加 `NSAllowsLocalNetworking`（局域网明文 HTTP 放行）。发现失败可手动输 IP 兜底。

### 2.2 电脑端同步服务器（sync_server.py，Windows 上跑）
- Python 标准库 http.server + zeroconf（pip 装一个包）广播 `_shiyin._tcp:8450`
- `GET /manifest.json` → `[{name, size, mtime, sha256}]`（含 .mp3 与 .lrc）
- `GET /file/<name>` → 文件字节，支持 `Range` 断点续传
- 启动：`python sync_server.py "F:\DeepSeek Workspace\时事分析\音乐集合"`（双击 .bat 也行）

### 2.3 编译与安装链路（无 Mac）
```
Windows 写代码 → git push → GitHub Actions (macos-14)
  → xcodegen 生成工程 → xcodebuild Release arm64（不签名）→ 打包 .ipa → artifact 下载
→ Windows: Sideloadly 用免费 Apple ID 签名 → USB 安装到 iPhone
```
- 免费 Apple ID 限制：**证书 7 天有效**（过期后 App 打不开，用 Sideloadly 对同一 .ipa 重签一次即恢复，Documents 数据不丢）；同时侧载 App ≤3 个。
- 仓库用 **public** 则 macOS runner 分钟数免费（fair use）；private 仓库 2000 分钟/月额度按 10x 扣，个人也够用。
- 备选（以后）：付费开发者账号 $99/年 → 证书 1 年有效，省去每周重签。

## 3. 里程碑

| 里程碑 | 内容 | 验收标准 |
|--------|------|----------|
| **M0 链路打通**（先做！） | Hello-World App + project.yml + CI workflow + artifact 下载 + Sideloadly 装机 | iPhone 上能看到 App 图标并打开 |
| M1 曲库+播放 | 扫描、列表、AVPlayer 播放、锁屏控制、断点续播 | 手动塞 2 首歌进 Documents 能完整播放控制 |
| M2 歌词 | LRC/USLT 解析 + 滚动歌词页 + 点击跳转 | 19 首全部显示同步歌词 |
| M3 局域网导入 | sync_server.py + App 发现/下载/进度/续传 | 手机 WiFi 下一键拉取 19 首 |
| M4 打磨 | 封面、搜索排序、深色模式、空状态、图标 | 日常可用 |

**M0 先行**的原因：编译→签名→装机是本项目唯一的外部依赖链，先用最小 App 验证全链路，避免功能写完后才发现装不上。

## 4. 你需要准备的东西
1. GitHub 账号（我生成仓库文件，你创建仓库并 push）
2. iPhone 上登录的那个 Apple ID（Sideloadly 签名用；不需要付费开发者账号）
3. Windows 装 Sideloadly（免费）+ Apple「Apple 设备」/iTunes（提供 iPhone USB 驱动）
4. 一根 USB 数据线；iPhone 打开开发者模式（设置→隐私与安全性→开发者模式）
5. 家里 WiFi（电脑和手机同一网段；路由器别开 AP 隔离）

## 5. 风险与对策
| 风险 | 对策 |
|------|------|
| 7 天证书过期 App 闪退 | 每周 Sideloadly 重签一次（1 分钟）；或以后 $99 开发者账号 |
| GitHub Actions macOS 排队慢 | 个人增量构建每次 ~5-8 分钟，可接受 |
| 路由器 AP 隔离导致发现不了电脑 | App 内提供手动输入 IP 兜底 |
| iOS 本地网络权限被拒 | 首次弹窗说明用途；被拒后设置里可重开 |
| 免费 ID 3 个 App 上限 | 个人自用一般不冲突 |
