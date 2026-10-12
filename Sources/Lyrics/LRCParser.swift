import Foundation

struct LyricLine: Identifiable, Hashable {
    let id: Int
    let time: Double
    let text: String
}

enum LRCParser {
    private static let tagRegex = try? NSRegularExpression(
        pattern: "\\[(\\d{1,2}):(\\d{2})(?:[.:](\\d{1,3}))?\\]")

    static func parse(_ raw: String) -> [LyricLine] {
        guard let regex = tagRegex else { return [] }
        var result: [LyricLine] = []
        var id = 0

        for rawLine in raw.split(whereSeparator: { $0 == "\n" || $0 == "\r" }) {
            let line = String(rawLine)
            let matches = regex.matches(in: line, range: NSRange(line.startIndex..., in: line))
            guard !matches.isEmpty else { continue }

            var times: [Double] = []
            for m in matches {
                guard
                    let minR = Range(m.range(at: 1), in: line),
                    let secR = Range(m.range(at: 2), in: line)
                else { continue }
                let minutes = Double(line[minR]) ?? 0
                let seconds = Double(line[secR]) ?? 0
                var frac = 0.0
                if m.range(at: 3).location != NSNotFound,
                   let fracR = Range(m.range(at: 3), in: line) {
                    let digits = String(line[fracR])
                    frac = (Double(digits) ?? 0) / pow(10.0, Double(digits.count))
                }
                times.append(minutes * 60 + seconds + frac)
            }

            var text = line
            for m in matches.reversed() {
                if let r = Range(m.range, in: text) { text.removeSubrange(r) }
            }
            text = text.trimmingCharacters(in: .whitespaces)
            guard !text.isEmpty else { continue }

            for t in times {
                result.append(LyricLine(id: id, time: t, text: text))
                id += 1
            }
        }
        result.sort { $0.time < $1.time }
        return result
    }
}
