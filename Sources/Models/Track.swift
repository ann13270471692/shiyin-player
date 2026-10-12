import Foundation

struct Track: Identifiable, Codable, Hashable {
    var id: String { path }
    var path: String
    var title: String
    var artist: String
    var duration: Double
    var addedAt: Date
    var hasLyrics: Bool

    var url: URL { URL(fileURLWithPath: path) }

    var lyricsURL: URL? {
        guard hasLyrics else { return nil }
        return url.deletingPathExtension().appendingPathExtension("lrc")
    }
}

enum TimeFormat {
    static func seconds(_ s: Double) -> String {
        guard s.isFinite && s >= 0 else { return "--:--" }
        let t = Int(s.rounded())
        return String(format: "%d:%02d", t / 60, t % 60)
    }
}
