import SwiftUI

struct ImportView: View {
    @StateObject private var browser = SyncBrowser()
    @StateObject private var downloader = SyncDownloader()
    @EnvironmentObject var library: LibraryStore
    @State private var selected: Set<String> = []
    @State private var hint: String?
    @State private var lastServer: SyncServer?

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // 顶部：发现的电脑（固定，不随列表滚动）
                serverModule

                // 中间：选择与下载按钮（放在 List 外面，
                // List 的行级手势会吞掉行内裸文字按钮的点击）
                if !downloader.remoteFiles.isEmpty {
                    actionBar
                }

                Divider()

                // 底部：文件列表（只有它是滚动视图，底部安全区留给标签栏）
                List {
                    Section {
                        ForEach(downloader.remoteFiles) { f in
                            row(f)
                        }
                    } header: {
                        if !downloader.remoteFiles.isEmpty {
                            Text("音乐集合（\(downloader.remoteFiles.count) 个文件）")
                        }
                    } footer: {
                        if downloader.remoteFiles.isEmpty {
                            Text("连上电脑后这里会列出全部文件。")
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
            }
            .navigationTitle("导入")
            .onAppear {
                browser.start()
                downloader.rescanLocal()
            }
            .onDisappear { browser.stop() }
        }
    }

    private var isFailed: Bool {
        if case .failed = downloader.state { return true }
        return false
    }

    // MARK: - 顶部：发现的电脑

    private var serverModule: some View {
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
                    .keyboardType(.numbersAndPunctuation)
                Button("连接") {
                    let host = browser.manualHost.trimmingCharacters(in: .whitespaces)
                    guard !host.isEmpty else { return }
                    let s = SyncServer(id: "manual-\(host)", host: host,
                                       port: 8450, displayName: host)
                    browser.addManual(s)
                    load(s)
                }
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

    // MARK: - 中间：选择与下载

    private var actionBar: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                chip("全选待更新") { selectStale() }
                chip("全选") { selectAll() }
                chip("清空") {
                    selected = []
                    hint = nil
                }
                Spacer(minLength: 4)
                Text("已选 \(selected.count)")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    if downloader.state == .running, let a = downloader.activeFile {
                        Text("正在下载：\(a)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    } else if let h = hint {
                        Text(h)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    } else {
                        Text("先勾选要拉取的文件，再点右边下载")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                }
                Spacer(minLength: 6)
                Button {
                    downloadOrStop()
                } label: {
                    Text(downloader.state == .running ? "停止下载" : "下载所选（\(selected.count)）")
                        .font(.subheadline.weight(.semibold))
                        .padding(.horizontal, 4)
                }
                .buttonStyle(.borderedProminent)
                .tint(.orange)
                .controlSize(.large)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(Color(.systemBackground))
    }

    private func chip(_ title: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.footnote.weight(.medium))
                .foregroundStyle(.primary)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color(.secondarySystemBackground), in: Capsule())
                .overlay(Capsule().strokeBorder(Color(.systemGray4), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    // MARK: - 文件行

    private func row(_ f: RemoteFile) -> some View {
        let stale = downloader.staleNames.contains(f.name)
        let downloaded = downloader.localNames.contains(f.name)
        let on = selected.contains(f.name)
        return HStack(spacing: 10) {
            // 勾选框只反映"选没选"，和下载状态分开，已下载的文件也能重新拉取
            Button {
                if on { selected.remove(f.name) }
                else { selected.insert(f.name) }
            } label: {
                Image(systemName: on ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(on ? Color.orange : Color.secondary)
                    .font(.system(size: 24))
                    .frame(width: 30, height: 30)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            VStack(alignment: .leading, spacing: 3) {
                Text(f.name).font(.caption).lineLimit(1)
                if let p = downloader.progress[f.name] {
                    if p < 0 {
                        Text("下载失败，已自动重试仍未成功——再点一次「下载所选」可续传")
                            .font(.caption2).foregroundStyle(.red)
                    } else if p >= 1 {
                        Text("完成").font(.caption2).foregroundStyle(.green)
                    } else {
                        HStack(spacing: 6) {
                            ProgressView(value: p).progressViewStyle(.linear)
                            Text(String(format: "%.0f%%", p * 100))
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                        if let s = downloader.speedText[f.name] {
                            Text(s).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            Spacer()
            if stale {
                Text("需更新").font(.caption2).foregroundStyle(.orange)
            } else if downloaded {
                Text("已下载").font(.caption2).foregroundStyle(.green)
            } else {
                Text(String(format: "%.1f MB", Double(f.size) / 1_048_576))
                    .font(.caption2).foregroundStyle(.secondary)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture {
            if on { selected.remove(f.name) }
            else { selected.insert(f.name) }
        }
    }

    // MARK: - 动作

    private func selectStale() {
        downloader.rescanLocal()
        var n = 0
        for f in downloader.remoteFiles
        where !downloader.localNames.contains(f.name)
            || downloader.staleNames.contains(f.name) {
            selected.insert(f.name)
            n += 1
        }
        hint = n == 0
            ? "没有检测到需要更新的文件。想强制刷新歌词：点「全选」再下载"
            : "已选中 \(n) 个未下载或电脑上改过的文件"
    }

    private func selectAll() {
        for f in downloader.remoteFiles { selected.insert(f.name) }
        hint = "已全选 \(downloader.remoteFiles.count) 个文件，点「下载所选」重新拉取"
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
            hint = "先勾选文件：点「全选待更新」或「全选」"
            return
        }
        downloadSelected()
    }

    private func load(_ server: SyncServer) {
        lastServer = server
        selected = []
        hint = nil
        Task { await downloader.fetchManifest(from: server) }
    }

    private func downloadSelected() {
        guard let server = lastServer else { return }
        let files = downloader.remoteFiles.filter { selected.contains($0.name) }
        Task {
            await downloader.download(files, from: server)
            library.refresh()
        }
    }
}
