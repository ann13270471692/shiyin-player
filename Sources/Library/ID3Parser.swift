import Foundation

/// 迷你 ID3v2.3/2.4 解析器：只取 USLT（歌词）帧。
enum ID3Parser {
    static func lyrics(from url: URL) -> String? {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? handle.close() }

        let header = handle.readData(ofLength: 10)
        guard header.count == 10 else { return nil }
        let h = [UInt8](header)
        guard h[0] == 0x49, h[1] == 0x44, h[2] == 0x33 else { return nil } // "ID3"
        let version = h[3]
        guard version >= 3 else { return nil } // 只支持 v2.3 / v2.4

        let tagSize = synchsafe(h, 6)
        guard tagSize > 0 else { return nil }
        let bodyData = handle.readData(ofLength: tagSize)
        guard bodyData.count >= 10 else { return nil }
        let b = [UInt8](bodyData)

        var pos = 0
        if h[5] & 0x40 != 0 { // 扩展头
            if version >= 4 {
                pos = synchsafe(b, 0)            // v2.4：大小含自身字段
            } else {
                let es = Int(b[0]) << 24 | Int(b[1]) << 16 | Int(b[2]) << 8 | Int(b[3])
                pos = 4 + es                     // v2.3：大小不含自身字段
            }
        }

        while pos + 10 <= b.count {
            let id = String(bytes: b[pos..<(pos + 4)], encoding: .ascii) ?? ""
            guard id.contains(where: { $0.isLetter }) else { break } // 进入 padding
            let fsize: Int
            if version >= 4 {
                fsize = synchsafe(b, pos + 4)
            } else {
                fsize = Int(b[pos + 4]) << 24 | Int(b[pos + 5]) << 16
                      | Int(b[pos + 6]) << 8 | Int(b[pos + 7])
            }
            let start = pos + 10
            guard fsize > 0, start + fsize <= b.count else { break }
            if id == "USLT" {
                return decodeUSLT(Array(b[start..<(start + fsize)]))
            }
            pos = start + fsize
        }
        return nil
    }

    private static func synchsafe(_ b: [UInt8], _ at: Int) -> Int {
        guard at + 4 <= b.count else { return 0 }
        return Int(b[at] & 0x7f) << 21 | Int(b[at + 1] & 0x7f) << 14
             | Int(b[at + 2] & 0x7f) << 7 | Int(b[at + 3] & 0x7f)
    }

    private static func decodeUSLT(_ f: [UInt8]) -> String? {
        guard f.count > 5, let enc = f.first else { return nil }
        var i = 1
        while i < f.count && f[i] != 0 { i += 1 } // 跳过语言（3 字节 + 结束符）
        i += 1
        guard i < f.count else { return nil }
        return decodeString(Array(f[i...]), encoding: enc)
    }

    private static func decodeString(_ bytes: [UInt8], encoding: UInt8) -> String? {
        switch encoding {
        case 0: return String(bytes: bytes, encoding: .isoLatin1)
        case 1: return String(bytes: bytes, encoding: .utf16)      // 带 BOM
        case 2: return String(bytes: bytes, encoding: .utf16BigEndian)
        case 3: return String(bytes: bytes, encoding: .utf8)
        default: return String(bytes: bytes, encoding: .utf8)
        }
    }
}
