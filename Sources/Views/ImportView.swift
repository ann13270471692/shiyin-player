import SwiftUI

struct ImportView: View {
    @StateObject private var browser = SyncBrowser()
    @StateObject private var downloader = SyncDownloader()
    @EnvironmentObject var library: LibraryStore
    @State private var selected: Set<String> = []
    @State private var lastServer: SyncServer?

    var body: some View {
        NavigationStack {
            List {
                Section("发现的电脑") {
                    if browser.servers.isEmpty {
                        Text("自动搜索中… 请确认电脑上运行着 sync_server.py，且手机与其在同一 WiFi")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    ForEach(browser.servers) { server in
                        HStack {
                            Image(systemName: "desktopcomputer")
                            VStack(alignment: .leading, spacing: 2) {
                                Text(server.displayName)
                                Text("\(server.host):\(server.port)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button("读取列表") { load(server) }
                                .buttonStyle(.bordered)
                        }
                    }
                    HStack {
                        TextField("或手动输入电脑 IP", text: $browser.manualHost)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                        Button("连接") {
                            let host = browser.manualHost.trimmingCharacters(in: .whitespaces)
                            guard !host.isEmpty else { return }
                            let s = SyncServer(id: "manual-\(host)", host: host,
                                               port: 8450, displayName: host)
                            browser.addManual(s)
                            load(s)
                        }
                    }
                }

                if !downloader.remoteFiles.isEmpty {
                    Section("音乐集合（\(downloader.remoteFiles.count) 个文件）") {
                        HStack(spacing: 16) {
                            Button("全选未下载") {
                                for f in downloader.remoteFiles
                                where !downloader.localNames.contains(f.name) {
                                    selected.insert(f.name)
                                }
                            }
                            Button("清空选择") { selected = [] }
                            Spacer()
                        }
                        .font(.footnote)
                        ForEach(downloader.remoteFiles) { f in
                            row(f)
                        }
                        Button("下载所选（\(selected.count)）") { downloadSelected() }
                            .disabled(selected.isEmpty || lastServer == nil)
                    }
                }

                if case .failed(let msg) = downloader.state {
                    Section {
                        Text(msg).font(.footnote).foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("导入")
            .onAppear { browser.start() }
            .onDisappear { browser.stop() }
        }
    }

    private func row(_ f: RemoteFile) -> some View {
        let already = downloader.localNames.contains(f.name)
        return HStack(spacing: 10) {
            Image(systemName: already ? "checkmark.circle.fill"
                    : (selected.contains(f.name) ? "largecircle.fill.circle" : "circle"))
                .foregroundStyle(already ? Color.green : Color.secondary)
            VStack(alignment: .leading, spacing: 3) {
                Text(f.name).font(.caption).lineLimit(1)
                if let p = downloader.progress[f.name] {
                    if p < 0 {
                        Text("下载失败，可重新勾选再试")
                            .font(.caption2).foregroundStyle(.red)
                    } else if p >= 1 {
                        Text("完成").font(.caption2).foregroundStyle(.green)
                    } else {
                        ProgressView(value: p).progressViewStyle(.linear)
                    }
                }
            }
            Spacer()
            Text(String(format: "%.1f MB", Double(f.size) / 1_048_576))
                .font(.caption2).foregroundStyle(.secondary)
        }
        .contentShape(Rectangle())
        .onTapGesture {
            guard !already else { return }
            if selected.contains(f.name) { selected.remove(f.name) }
            else { selected.insert(f.name) }
        }
    }

    private func load(_ server: SyncServer) {
        lastServer = server
        selected = []
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
