import Foundation
import AVFoundation

@MainActor
final class LibraryStore: ObservableObject {
    @Published private(set) var tracks: [Track] = []

    static func musicDirectory() -> URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let dir = docs.appendingPathComponent("Music", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    func refresh() {
        let dir = Self.musicDirectory()
        let audioExts: Set<String> = ["mp3", "m4a", "aac", "flac", "wav", "alac"]
        let items = (try? FileManager.default.contentsOfDirectory(
            at: dir,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]
        )) ?? []

        var found: [Track] = []
        for url in items where audioExts.contains(url.pathExtension.lowercased()) {
            let lrc = url.deletingPathExtension().appendingPathExtension("lrc")
            let hasLyrics = FileManager.default.fileExists(atPath: lrc.path)
            let (title, artist) = Self.parseFilename(url.deletingPathExtension().lastPathComponent)
            let mod = (try? url.resourceValues(forKeys: [.contentModificationDateKey]))?
                .contentModificationDate ?? .distantPast
            found.append(Track(path: url.path, title: title, artist: artist,
                               duration: 0, addedAt: mod, hasLyrics: hasLyrics))
        }
        found.sort { a, b in
            if a.artist != b.artist { return a.artist.localizedStandardCompare(b.artist) == .orderedAscending }
            return a.title.localizedStandardCompare(b.title) == .orderedAscending
        }
        tracks = found
        Task { await self.loadDurations() }
    }

    /// 删除一首歌的手机本地副本（音频文件 + 同名 .lrc，若存在），
    /// 电脑上的文件不受影响。失败时抛出，由调用方提示用户。
    func deleteLocalCopy(of track: Track) throws {
        let fm = FileManager.default
        try fm.removeItem(at: track.url)
        let lrc = track.url.deletingPathExtension().appendingPathExtension("lrc")
        if fm.fileExists(atPath: lrc.path) {
            try fm.removeItem(at: lrc)
        }
        refresh()
    }

    /// "01 - 杨宗纬 - 其实都没有" → (其实都没有, 杨宗纬)
    static func parseFilename(_ name: String) -> (title: String, artist: String) {
        let parts = name.components(separatedBy: " - ")
        if parts.count >= 3 {
            let artist = parts[parts.count - 2]
            let title = parts[parts.count - 1]
            return (title, artist)
        } else if parts.count == 2 {
            return (parts[1], parts[0])
        }
        return (name, "未知歌手")
    }

    private func loadDurations() async {
        for i in tracks.indices where tracks[i].duration == 0 {
            let asset = AVURLAsset(url: tracks[i].url)
            if let d = try? await asset.load(.duration) {
                let secs = CMTimeGetSeconds(d)
                if secs.isFinite && secs > 0 {
                    tracks[i].duration = secs
                }
            }
        }
    }
}
