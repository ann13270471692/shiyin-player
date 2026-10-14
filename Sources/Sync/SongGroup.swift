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
    let deleted: Bool        // 曾在手机上下载、后来被删掉（不是没下过）
    // 文件名解析出来的展示/排序字段：YYYY-NNN - 歌手 - 歌名【影视】
    let year: Int
    let artist: String
    let title: String
    let movie: Bool          // 影视金曲
    let movieName: String    // 影视金曲的剧名（服务器给的，可能为空）
    let artistPy: String     // 歌手拼音，用来按歌手排序

    var id: String { key }
}

enum SongSort: Int, CaseIterable {
    case downloadedFirst      // 默认：已下载排在最前
    case undownloadedFirst    // 没下的排最前，方便找要拉的歌
    case deletedFirst         // 手机上删过的排最前，方便看删了哪些 / 要不要拉回来
    case year
    case artist
    case movie                // 影视金曲排最前

    var label: String {
        switch self {
        case .downloadedFirst: return "已下载"
        case .undownloadedFirst: return "未下载"
        case .deletedFirst: return "已删除"
        case .year: return "年份"
        case .artist: return "歌手"
        case .movie: return "影视"
        }
    }
}

/// 只看某一类：全部 / 影视金曲 / 手机上删过的 / 还没下的
enum SongFilter: Int, CaseIterable {
    case all
    case movie
    case deleted
    case undownloaded

    var label: String {
        switch self {
        case .all: return "全部"
        case .movie: return "只看影视"
        case .deleted: return "只看已删除"
        case .undownloaded: return "只看未下载"
        }
    }
}

enum SongGroup {
    private struct Parsed {
        var year = 0
        var artist = ""
        var movie = false
        var title: String
    }

    /// 拆 "1984-900 - 郑少秋 - 楚留香【影视】" -> 年份 / 歌手 / 歌名
    private static func parseKey(_ key: String) -> Parsed {
        var p = Parsed(title: key)
        guard let r1 = key.range(of: " - ") else { return p }
        let head = String(key[key.startIndex..<r1.lowerBound])
        if head.count == 4, let y = Int(head) { p.year = y }
        let rest = String(key[r1.upperBound...])
        guard let r2 = rest.range(of: " - ") else { p.title = rest; return p }
        p.artist = String(rest[rest.startIndex..<r2.lowerBound])
        var t = String(rest[r2.upperBound...])
        if t.hasSuffix("【影视】") {
            p.movie = true
            t = String(t.dropLast(4))
        }
        p.title = t
        return p
    }

    static func group(_ files: [RemoteFile], local: Set<String>, stale: Set<String>,
                      deleted: Set<String> = Set()) -> [SongEntry] {
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
            let p = parseKey(key)
            let isStale = stale.contains(a.name) || (l.map { stale.contains($0.name) } ?? false)
            let isLocal = local.contains(a.name) && (l == nil || local.contains(l!.name))
            // 本机已经没有它了，但它曾在手机上下载过：显示成「已删除」而不是「未下载」
            let isDeleted = !isLocal && (deleted.contains(a.name)
                                         || (l.map { deleted.contains($0.name) } ?? false))
            out.append(SongEntry(key: key, audio: a, lyric: l, size: a.size,
                                 stale: isStale, downloaded: isLocal, deleted: isDeleted,
                                 year: p.year, artist: p.artist, title: p.title,
                                 // 文件名没写【影视】，但服务器剧名表认它是影视金曲的，也算影视
                                 movie: p.movie || !(a.movie ?? "").isEmpty,
                                 movieName: a.movie ?? "",
                                 artistPy: FuzzyMatch.pinyinFull(p.artist)))
        }
        return out
    }

    /// 同一排序方式内回落到文件名序（= 年份序），保证稳定
    static func sort(_ list: inout [SongEntry], _ mode: SongSort) {
        list.sort { x, y in
            switch mode {
            case .downloadedFirst:
                if x.downloaded != y.downloaded { return x.downloaded }
            case .undownloadedFirst:
                if x.downloaded != y.downloaded { return !x.downloaded }
            case .deletedFirst:
                if x.deleted != y.deleted { return x.deleted }
            case .year:
                if x.year != y.year { return x.year < y.year }
            case .artist:
                if x.artistPy != y.artistPy { return x.artistPy < y.artistPy }
                if x.artist != y.artist { return x.artist < y.artist }
            case .movie:
                if x.movie != y.movie { return x.movie }
            }
            return x.key < y.key
        }
    }
}
