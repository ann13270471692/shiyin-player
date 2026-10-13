import Foundation

/// 模糊检索：原文包含 / 拼音首字母包含 / 跳字命中。
/// 「晴天」「qt」「qing」「2019」都能命中「2019-012 - 周杰伦 - 晴天.mp3」。
enum FuzzyMatch {
    private static var charInitial: [Character: String] = [:]
    /// Han → 汉语拼音（CoreFoundation 内置转换；用 rawValue 避免 SDK 常量名差异）
    private static let pinyinTransform = StringTransform(rawValue: "Mandarin-Latin")

    /// 只留字母数字与汉字，去掉空格、连字符、扩展名等噪声
    static func compact(_ s: String) -> String {
        var out = ""
        for u in s.lowercased().unicodeScalars {
            if (u >= "a" && u <= "z") || (u >= "0" && u <= "9")
                || (u.value >= 0x4E00 && u.value <= 0x9FFF) {
                out.unicodeScalars.append(u)
            }
        }
        return out
    }

    /// 汉字取拼音首字母（系统内置转换），字母数字原样保留
    static func initials(_ s: String) -> String {
        var out = ""
        for ch in s {
            if let u = ch.unicodeScalars.first, u.value >= 0x4E00 && u.value <= 0x9FFF {
                if let hit = charInitial[ch] {
                    out += hit
                    continue
                }
                var py = String(ch).applyingTransform(Self.pinyinTransform,
                                                       reverse: false) ?? String(ch)
                py = py.applyingTransform(StringTransform(rawValue: "Strip Combination Marks"),
                                          reverse: false) ?? py
                var ini = ""
                if let f = py.lowercased().unicodeScalars.first, f >= "a" && f <= "z" {
                    ini.unicodeScalars.append(f)
                }
                charInitial[ch] = ini
                out += ini
            } else if let f = ch.lowercased().unicodeScalars.first,
                      (f >= "a" && f <= "z") || (f >= "0" && f <= "9") {
                out.unicodeScalars.append(f)
            }
        }
        return out
    }

    private static var pinyinCache: [String: String] = [:]

    /// 汉字全拼连写（晴天 → qingtian），字母数字原样保留
    static func pinyinFull(_ s: String) -> String {
        if let hit = pinyinCache[s] { return hit }
        var t = s.applyingTransform(pinyinTransform, reverse: false) ?? s
        t = t.applyingTransform(StringTransform(rawValue: "Strip Combination Marks"),
                                reverse: false) ?? t
        let out = compact(t)
        if pinyinCache.count > 4000 { pinyinCache.removeAll() }
        pinyinCache[s] = out
        return out
    }

    private static func subseq(_ needle: String, _ hay: String) -> Bool {
        let n = Array(needle), h = Array(hay)
        var p = 0
        for c in h {
            if p < n.count && c == n[p] { p += 1 }
            if p == n.count { return true }
        }
        return p == n.count
    }

    /// 3=原文包含 2=拼音（首字母或全拼）包含 1=跳字命中 0=不匹配
    static func score(_ name: String, _ q: String) -> Int {
        let needle = compact(q)
        if needle.isEmpty { return 3 }
        let base = name.replacingOccurrences(of: "\\.(mp3|lrc|jpg|png|txt)$",
                                             with: "", options: .regularExpression)
        let hay = compact(base)
        if hay.contains(needle) { return 3 }
        let ini = initials(base)
        let full = pinyinFull(base)
        if ini.contains(needle) || full.contains(needle) { return 2 }
        // 跳字只按拼音判定：太短的查询走跳字会把无关长文件名捞进来
        if needle.count >= 3 && (subseq(needle, ini) || subseq(needle, full)) { return 1 }
        return 0
    }

    /// 「 - 」分隔的最后一段视为歌名；歌名里命中的排在前面
    private static func titlePart(_ name: String) -> String {
        let base = name.replacingOccurrences(of: "\\.(mp3|lrc|jpg|png|txt)$",
                                             with: "", options: .regularExpression)
        if let r = base.range(of: " - ", options: .backwards) {
            return String(base[r.upperBound...])
        }
        return base
    }

    static func filter<T>(_ items: [T], name: (T) -> String, _ q: String) -> [T] {
        let needle = compact(q)
        if needle.isEmpty { return items }
        var scored: [(Int, Int, String, T)] = []
        scored.reserveCapacity(items.count)
        for it in items {
            let n = name(it)
            let s = score(n, q)
            if s > 0 {
                scored.append((s, score(titlePart(n), q) > 0 ? 1 : 0, n, it))
            }
        }
        // 匹配度 → 歌名是否命中 → 文件名
        scored.sort { a, b in
            if a.0 != b.0 { return a.0 > b.0 }
            if a.1 != b.1 { return a.1 > b.1 }
            return a.2 < b.2
        }
        return scored.map { $0.3 }
    }
}
