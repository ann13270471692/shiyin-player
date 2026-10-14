import SwiftUI

struct ImportView: View {
    @StateObject private var browser = SyncBrowser()
    @EnvironmentObject var downloader: SyncDownloader
    @EnvironmentObject var library: LibraryStore
    @State private var selected: Set<String> = []
    // 列表按「一首歌」一行显示：mp3 与歌词合并，选一次两个都拉
    @State private var songs: [SongEntry] = []
    // 排序：默认已下载优先，可切 没下的优先 / 年份 / 歌手 / 影视
    @State private var sortMode: SongSort = .downloadedFirst
    // 连上以后把服务器卡片收起，位置留给歌曲列表；点「换电脑」再展开
    @State private var showServers: Bool = false
    @State private var dlCount: Int = 0
    // 手机上删过的歌数量；shown = 当前渲染到第几行（分页，防看门狗杀进程）
    @State private var delCount: Int = 0
    @State private var shown: Int = 300
    private let pageSize: Int = 300
    @State private var hint: String?
    @State private var lastServer: SyncServer?
    @State private var query: String = ""
    @FocusState private var ipFocused: Bool
    @FocusState private var searchFocused: Bool

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // 顶部：发现的电脑（固定，不随列表滚动）
                serverModule

                // 中间：选择与下载按钮（放在 List 外面，
                // List 的行级手势会吞掉行内裸文字按钮的点击）
                if !downloader.remoteFiles.isEmpty {
                    searchBar
                    sortBar
                    actionBar
                }

                Divider()

                // 底部：歌曲列表（只有它是滚动视图，底部安全区留给标签栏）
                List {
                    Section {
                        ForEach(visibleSongs) { s in
                            row(s)
                        }
                    } header: {
                        if !downloader.remoteFiles.isEmpty {
                            Text(query.isEmpty
                                 ? "排序：\(sortMode.label) · 显示前 \(visibleSongs.count) 行"
                                 : "匹配 \(filteredSongs.count) / 共 \(songs.count) 首")
                        }
                    } footer: {
                        if downloader.remoteFiles.isEmpty {
                            Text("连上电脑后这里会列出全部歌曲。")
                        } else if visibleSongs.isEmpty {
                            Text("没有匹配「\(query)」的歌曲。可以只输入歌名的一部分，或试拼音首字母（如 qt = 晴天）。")
                         } else if filteredSongs.count > visibleSongs.count {
                             Button("加载更多（已显示 \(visibleSongs.count) / \(filteredSongs.count) 首）") { shown += pageSize }
                        }
                    }

                    Section {
                        let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
                        let b = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"
                        Text("梦秋音乐 v\(v) (build \(b))")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
                .contentMargins(.bottom, 18, for: .scrollContent)
                .scrollDismissesKeyboard(.immediately)
                // 列表/本地状态/待更新状态任一变化，就重算「一行一首歌」
                .onChange(of: downloader.remoteFiles) { _ in rebuildSongs() }
                .onChange(of: downloader.staleNames) { _ in rebuildSongs() }
                .onChange(of: downloader.localNames) { _ in rebuildSongs() }
                .onChange(of: downloader.deletedNames) { _ in rebuildSongs() }
                .onChange(of: query) { _ in shown = pageSize }

                // 底部固定操作条：拇指够得着，下载状态也在这里看
                if !downloader.remoteFiles.isEmpty {
                    bottomBar
                }
            }
            .navigationTitle("导入")
            // 键盘上方一排「连接 / 完成」：键盘弹出时也能收起，
            // 收起后底部的 曲库/播放/导入 标签栏立刻恢复可点
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("连接") { connectManual() }
                        .fontWeight(.semibold)
                    Button("完成") { ipFocused = false; searchFocused = false }
                }
            }
            .onAppear {
                browser.start()
                downloader.rescanLocal()
                rebuildSongs()
            }
            .onDisappear { browser.stop() }
        }
    }

    private var isFailed: Bool {
        if case .failed = downloader.state { return true }
        return false
    }

    /// 按模糊查找过滤后的全部歌曲（匹配度高的排前面）
    private var filteredSongs: [SongEntry] {
        FuzzyMatch.filter(songs, name: { $0.movieName.isEmpty ? $0.key : $0.key + " " + $0.movieName }, query)
    }

    /// 一次只渲染一页：列表上万个行全建出来会被系统看门狗杀掉（1.0.7 的崩溃就是这个）
    private var visibleSongs: [SongEntry] {
        Array(filteredSongs.prefix(shown))
    }

    /// 文件列表 -> 歌曲列表：mp3 与同名歌词合并成一行，再按当前方式排序
    private func rebuildSongs() {
        var list = SongGroup.group(downloader.remoteFiles,
                                   local: downloader.localNames,
                                   stale: downloader.staleNames,
                                   deleted: downloader.deletedNames)
        SongGroup.sort(&list, sortMode)
        songs = list
        dlCount = list.reduce(0) { $0 + ($1.downloaded ? 1 : 0) }
        delCount = list.reduce(0) { $0 + ($1.deleted ? 1 : 0) }
        shown = pageSize
    }

    private func setSort(_ mode: SongSort) {
        sortMode = mode
        var list = songs
        SongGroup.sort(&list, mode)
        songs = list
    }

    // MARK: - 模糊查找

    private var searchBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 17))
                .foregroundStyle(.secondary)
            TextField("模糊查找：歌名 / 歌手 / 拼音（如 qt）", text: $query)
                .textFieldStyle(.plain)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .focused($searchFocused)
            if !query.isEmpty {
                Button {
                    query = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                        .font(.system(size: 17))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
        .padding(.horizontal, 14)
        .padding(.top, 10)
    }

    // MARK: - 顶部：发现的电脑

    @ViewBuilder
    private var serverModule: some View {
        if lastServer != nil && !isFailed && !showServers {
            // 已连接：只留一行状态，位置让给歌曲列表
            HStack(spacing: 10) {
                Label("已连接 \(lastServer?.displayName ?? "")", systemImage: "checkmark.circle.fill")
                    .font(.subheadline)
                    .foregroundStyle(.green)
                Spacer()
                Button("刷新") { if let s = lastServer { load(s) } }
                    .buttonStyle(.bordered)
                Button("换电脑") { showServers = true }
                    .buttonStyle(.bordered)
                Button("诊断") { sendDiag() }
                    .buttonStyle(.bordered)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(Color(.secondarySystemBackground))
        } else {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("发现的电脑").font(.subheadline.weight(.semibold))
                Spacer()
                if let s = lastServer, !isFailed {
                    Label("已连接 \(s.displayName)", systemImage: "checkmark.circle.fill")
                        .font(.caption)
                        .foregroundStyle(.green)
                }
            }

            if browser.servers.isEmpty {
                Text("自动搜索中… 请确认电脑上运行着「启动同步服务器.bat」，且手机与其在同一 WiFi")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            ForEach(browser.servers) { server in
                HStack(spacing: 10) {
                    Image(systemName: "desktopcomputer")
                        .font(.system(size: 18))
                        .foregroundStyle(.orange)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(server.displayName).font(.subheadline)
                        Text("\(server.host):\(server.port)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("读取列表") { load(server) }
                        .buttonStyle(.borderedProminent)
                        .tint(.orange)
                }
            }

            HStack(spacing: 10) {
                TextField("或手动输入电脑 IP", text: $browser.manualHost)
                    .textFieldStyle(.roundedBorder)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.decimalPad)
                    .focused($ipFocused)
                Button("连接") { connectManual() }
                    .buttonStyle(.bordered)
            }

            if case .failed(let msg) = downloader.state {
                Text(msg).font(.caption).foregroundStyle(.red)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(Color(.secondarySystemBackground))
        }
    }

    // MARK: - 中间：排序 / 选择 / 底部下载条

    private var sortBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Text("排序").font(.footnote).foregroundStyle(.tertiary)
                ForEach(SongSort.allCases, id: \.self) { m in
                    Button {
                        setSort(m)
                    } label: {
                        Text(m.label)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(sortMode == m ? Color.white : Color.primary)
                            .padding(.horizontal, 13)
                            .padding(.vertical, 7)
                            .background(sortMode == m ? Color.orange : Color(.secondarySystemBackground),
                                        in: Capsule())
                            .overlay(Capsule().strokeBorder(
                                sortMode == m ? Color.orange : Color(.systemGray4), lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
        }
    }

    private var actionBar: some View {
        HStack(spacing: 8) {
            Text(query.isEmpty
                 ? "共 \(songs.count) 首 · 已下载 \(dlCount) 首 · 已删除 \(delCount) 首 · 已选 \(selected.count) 首"
                 : "匹配 \(visibleSongs.count) / 共 \(songs.count) 首 · 已选 \(selected.count) 首")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Spacer(minLength: 4)
            chip("全选") { selectAll() }
            chip("清空") {
                selected = []
                hint = nil
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Color(.systemBackground))
    }

    private var bottomBar: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                if downloader.state == .running, let a = downloader.activeFile {
                    Text("正在下载：\(a)")
                        .font(.footnote)
                        .foregroundStyle(.orange)
                        .lineLimit(1)
                } else if let h = hint {
                    Text(h)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                } else {
                    Text("点一行选一首 · 没歌词的自动跳过")
                        .font(.footnote)
                        .foregroundStyle(.tertiary)
                }
            }
            Spacer(minLength: 6)
            Button {
                downloadOrStop()
            } label: {
                Text(downloader.state == .running ? "停止下载" : "下载 \(selected.count) 首")
                    .font(.body.weight(.semibold))
                    .padding(.horizontal, 6)
            }
            .buttonStyle(.borderedProminent)
            .tint(.orange)
            .controlSize(.large)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(.bar)
    }

    private func chip(_ title: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.primary)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color(.secondarySystemBackground), in: Capsule())
                .overlay(Capsule().strokeBorder(Color(.systemGray4), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    // MARK: - 歌曲行（一行 = 一首歌：mp3 与它的歌词一起下载）

    private func row(_ s: SongEntry) -> some View {
        let on = selected.contains(s.key)
        return HStack(spacing: 10) {
            // 勾选框只反映"选没选"，和下载状态分开，已下载的歌也能重新拉取
            Button {
                if on { selected.remove(s.key) }
                else { selected.insert(s.key) }
            } label: {
                Image(systemName: on ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(on ? Color.orange : Color.secondary)
                    .font(.system(size: 24))
                    .frame(width: 30, height: 30)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            // 主行歌名，副行歌手 · 年份（影视金曲带标记）
            VStack(alignment: .leading, spacing: 4) {
                Text(s.title).font(.body).lineLimit(1)
                HStack(spacing: 6) {
                    Text(s.artist.isEmpty ? "未知歌手" : s.artist)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    if s.year > 0 {
                        Text(String(s.year)).font(.footnote).foregroundStyle(.tertiary)
                    }
                    if s.movie {
                        // 有剧名就显示剧名（服务器 movie-meta.json），没有就只显示「影视」
                        Text(s.movieName.isEmpty ? "影视" : s.movieName)
                            .font(.caption)
                            .foregroundStyle(.orange)
                            .lineLimit(1)
                            .frame(maxWidth: 170)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.orange.opacity(0.15), in: Capsule())
                    }
                }
                if let p = songProgress(s) {
                    if p < 0 {
                        Text("下载失败，已自动重试仍未成功——再点一次下载按钮可续传")
                            .font(.caption).foregroundStyle(.red)
                    } else if p >= 1 {
                        Text("完成").font(.caption).foregroundStyle(.green)
                    } else {
                        HStack(spacing: 6) {
                            ProgressView(value: p).progressViewStyle(.linear)
                            Text(String(format: "%.0f%%", p * 100))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if let sp = songSpeed(s) {
                            Text(sp).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            Spacer(minLength: 6)
            VStack(alignment: .trailing, spacing: 3) {
                if s.stale {
                    Text("需更新").font(.footnote).foregroundStyle(.orange)
                } else if s.downloaded {
                    Text("已下载").font(.footnote).foregroundStyle(.green)
                } else {
                    Text(s.deleted ? "已删除" : "未下载")
                        .font(.footnote)
                        .foregroundStyle(s.deleted ? Color.secondary : Color.tertiary)
                }
                Text(String(format: "%.1f MB", Double(s.size) / 1_048_576))
                    .font(.footnote)
                    .foregroundStyle(.tertiary)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture {
            if on { selected.remove(s.key) }
            else { selected.insert(s.key) }
        }
    }

    /// 进度优先看音频；音频下完（或没有音频进度）时看歌词
    private func songProgress(_ s: SongEntry) -> Double? {
        if let a = s.audio, let p = downloader.progress[a.name], p < 0 || p < 1 { return p }
        if let l = s.lyric, let p = downloader.progress[l.name] { return p }
        if let a = s.audio, let p = downloader.progress[a.name] { return p }
        return nil
    }

    private func songSpeed(_ s: SongEntry) -> String? {
        if let a = s.audio, let t = downloader.speedText[a.name] { return t }
        if let l = s.lyric { return downloader.speedText[l.name] }
        return nil
    }

    // MARK: - 动作

    private func selectAll() {
        let list = visibleSongs
        for s in list { selected.insert(s.key) }
        hint = "已选中当前页 \(list.count) 首（歌词一并拉取）；后面的歌点「加载更多」再选"
    }

    private func downloadOrStop() {
        if downloader.state == .running {
            downloader.cancel()
            hint = "正在停止…"
            return
        }
        if lastServer == nil {
            hint = "先在上方点「读取列表」连上电脑"
            return
        }
        if selected.isEmpty {
            hint = "先勾选歌曲：点一行选一首，或用「全选」"
            return
        }
        downloadSelected()
    }

    private func connectManual() {
        let host = browser.manualHost.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !host.isEmpty else {
            hint = "先输入电脑 IP（例如 192.168.2.12）"
            return
        }
        ipFocused = false
        let s = SyncServer(id: "manual-\(host)", host: host,
                           port: 8450, displayName: host)
        browser.addManual(s)
        load(s)
    }

    private func sendDiag() {
        guard let s = lastServer else { hint = "先连上电脑，再点诊断发送日志"; return }
        DebugLog.shared.log("user tap 诊断")
        let ver = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        DebugLog.shared.upload(server: s, device: ProcessInfo.processInfo.hostName, version: ver)
        hint = "正在把诊断日志发到电脑…"
    }

    private func load(_ server: SyncServer) {
        lastServer = server
        showServers = false     // 连上就把服务器卡片收起
        selected = []
        hint = nil
        ipFocused = false
        Task { await downloader.fetchManifest(from: server) }
    }

    private func downloadSelected() {
        guard let server = lastServer else { return }
        // 选中一首 = 音频 + 它的歌词；电脑上没歌词就只有音频，不另外提示
        var files: [RemoteFile] = []
        for s in songs where selected.contains(s.key) {
            if let a = s.audio { files.append(a) }
            if let l = s.lyric { files.append(l) }
        }
        if files.isEmpty {
            hint = "选中的歌曲没有可下载的内容"
            return
        }
        Task {
            await downloader.download(files, from: server)
            library.refresh()
        }
    }
}
