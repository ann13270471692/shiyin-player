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
    @State private var search = ""
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
                ForEach(displayed) { track in
                    Button {
                        engine.playQueue(displayed, startAt: track)
                    } label: {
                        HStack(spacing: 10) {
                            if engine.current?.id == track.id {
                                Image(systemName: engine.isPlaying ? "waveform" : "music.note")
                                    .font(.subheadline)
                                    .foregroundStyle(Color.accentColor)
                                    .symbolEffect(.variableColor.iterative,
                                                 isActive: engine.isPlaying)
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
                    .buttonStyle(.plain)
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
}
