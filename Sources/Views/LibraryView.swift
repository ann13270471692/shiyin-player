import SwiftUI

enum SortKey: String, CaseIterable, Identifiable {
    case file = "文件名"
    case title = "歌名"
    case artist = "歌手"
    case duration = "时长"
    var id: String { rawValue }
}

struct LibraryView: View {
    @EnvironmentObject var library: LibraryStore
    @EnvironmentObject var engine: PlayerEngine
    @EnvironmentObject var downloader: SyncDownloader
    @State private var search = ""
    @State private var trackToDelete: Track?
    @State private var showDeleteConfirm = false
    @State private var deleteError: String?
    @State private var showDeleteError = false
    @AppStorage("librarySortKey") private var sortKeyRaw = SortKey.file.rawValue

    private var sortKey: SortKey {
        SortKey(rawValue: sortKeyRaw) ?? .file
    }

    private var displayed: [Track] {
        var list = library.tracks
        if !search.isEmpty {
            list = list.filter {
                $0.title.localizedCaseInsensitiveContains(search)
                    || $0.artist.localizedCaseInsensitiveContains(search)
            }
        }
        switch sortKey {
        case .file:
            list.sort {
                $0.url.lastPathComponent.localizedStandardCompare(
                    $1.url.lastPathComponent) == .orderedAscending
            }
        case .title:
            list.sort { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending }
        case .artist:
            list.sort {
                let c = $0.artist.localizedCaseInsensitiveCompare($1.artist)
                return c == .orderedAscending
                    || (c == .orderedSame
                        && $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending)
            }
        case .duration:
            list.sort { $0.duration < $1.duration }
        }
        return list
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(displayed) { track in
                        Button {
                            engine.playQueue(displayed, startAt: track)
                        } label: {
                            rowLabel(track)
                        }
                        .buttonStyle(.plain)
                        // 长按走系统菜单：挂在 Button 上的 onLongPressGesture
                        // 会被 Button 自身的点击手势吃掉，长按根本不触发
                        .contextMenu {
                            Button {
                                askDelete(track)
                            } label: {
                                Label("从手机删除", systemImage: "trash")
                            }
                        }
                    } onDelete: { indexes in
                        // 左滑删除：同样只删手机副本，且要经过确认
                        let items = displayed
                        if let i = indexes.first, i < items.count {
                            askDelete(items[i])
                        }
                    }
                } header: {
                    if !displayed.isEmpty {
                        Text("长按或左滑歌曲可删除（只删手机副本）")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("曲库（\(library.tracks.count)）")
            .searchable(text: $search, prompt: "搜索歌名 / 歌手")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Picker("排序", selection: $sortKeyRaw) {
                            ForEach(SortKey.allCases) { k in
                                Text(k.rawValue).tag(k.rawValue)
                            }
                        }
                    } label: {
                        Image(systemName: "arrow.up.arrow.down")
                    }
                }
            }
            .refreshable { library.refresh() }
            .confirmationDialog("从手机删除", isPresented: $showDeleteConfirm, titleVisibility: .visible) {
                Button("删除", role: .destructive) {
                    if let t = trackToDelete { delete(t) }
                }
                Button("取消", role: .cancel) {}
            } message: {
                if let t = trackToDelete {
                    Text("\(t.title) — \(t.artist)")
                    Text("只删除手机上已下载的副本，电脑上的文件不受影响")
                }
            }
            .alert("删除失败", isPresented: $showDeleteError, presenting: deleteError) { _ in
                Button("好", role: .cancel) {}
            } message: { msg in
                Text(msg)
            }
            .overlay {
                if library.tracks.isEmpty {
                    ContentUnavailableView(
                        "还没有音乐",
                        systemImage: "music.note",
                        description: Text("用「导入」页从电脑拉取，或用数据线经 iTunes / Apple 设备把 MP3 放入 Music 文件夹")
                    )
                }
            }
        }
    }

    // 行内容拆成独立函数：整个 body 太长会让类型检查超时
    @ViewBuilder
    private func rowLabel(_ track: Track) -> some View {
        HStack(spacing: 10) {
            if engine.current?.id == track.id {
                Image(systemName: engine.isPlaying ? "waveform" : "music.note")
                    .font(.subheadline)
                    .foregroundStyle(Color.accentColor)
                    .symbolEffect(.variableColor.iterative, isActive: engine.isPlaying)
            } else {
                Image(systemName: "music.note")
                    .font(.subheadline)
                    .foregroundStyle(.tertiary)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(track.title)
                    .font(.body)
                    .foregroundStyle(engine.current?.id == track.id
                                     ? Color.accentColor : Color.primary)
                Text(track.artist)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            if track.hasLyrics {
                Image(systemName: "text.bubble")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            Text(TimeFormat.seconds(track.duration))
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - 删除手机副本

    private func askDelete(_ track: Track) {
        trackToDelete = track
        showDeleteConfirm = true
    }

    private func delete(_ track: Track) {
        // 正在播放的正是它：先停止播放、清空「正在播放」状态，再删文件
        if engine.current?.id == track.id {
            engine.stopAndClear()
        }
        engine.forgetTrack(track.path)
        do {
            try library.deleteLocalCopy(of: track)   // 内部会 refresh() 刷新曲库列表
        } catch {
            deleteError = "无法删除「\(track.title)」：\(error.localizedDescription)"
            showDeleteError = true
            return
        }
        // 清掉下载记录与记住的 mtime，导入页里该文件重新显示为「未下载」
        downloader.forgetLocalCopy(of: track.url)
    }
}
