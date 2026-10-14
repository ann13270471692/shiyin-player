import Foundation

/// 导入页的一行 = 一首歌：mp3 和它的歌词绑在一起，选一次两个都下。
/// 电脑上没有歌词的歌 lyric 为 nil，下载时自然跳过，不提示。
struct SongEntry: Identifiable, Hashable {
    let key: String          // 去掉扩展名的文件名
    let audio: RemoteFile?
    let lyric: RemoteFile?
    let size: Int            // 显示用（音频大小）
    let stale: Bool          // 音频或歌词任一在电脑上改过
    let downloaded: Bool     // 音频已在本机（缺歌词不算没下完）

    var id: String { key }
}

enum SongGroup {
    static func group(_ files: [RemoteFile], local: Set<String>, stale: Set<String>) -> [SongEntry] {
        var audios: [String: RemoteFile] = [:]
        var lyrics: [String: RemoteFile] = [:]
        for f in files {
            let key = (f.name as NSString).deletingPathExtension
            switch (f.name as NSString).pathExtension.lowercased() {
            case "mp3": audios[key] = f
            case "lrc": lyrics[key] = f
            default: break
            }
        }
        var out: [SongEntry] = []
        out.reserveCapacity(audios.count)
        for (key, a) in audios {
            let l = lyrics[key]
            let isStale = stale.contains(a.name) || (l.map { stale.contains($0.name) } ?? false)
            let isLocal = local.contains(a.name) && (l == nil || local.contains(l!.name))
            out.append(SongEntry(key: key, audio: a, lyric: l,
                                 size: a.size, stale: isStale, downloaded: isLocal))
        }
        out.sort { $0.key < $1.key }
        return out
    }
}
