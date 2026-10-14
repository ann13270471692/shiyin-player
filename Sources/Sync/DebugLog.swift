import Foundation
import os

/// 诊断日志：内存环形 + 沙盒文件，可一键 POST 到电脑上的同步服务器（/devlog）。
/// 同时写 os_log，所以 Windows 上 `pymobiledevice3 syslog live` 也能直接看到。
final class DebugLog: ObservableObject {
    static let shared = DebugLog()

    @Published var lastUpload: String = ""
    @Published var lineCount: Int = 0

    private let oslog = Logger(subsystem: "com.shiyin.player", category: "diag")
    private let lock = NSLock()
    private var lines: [String] = []
    private let maxLines = 5000

    private lazy var fileURL: URL = {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        let dir = base.appendingPathComponent("diag", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("shiyin-diag.log")
    }()

    func log(_ msg: String) {
        let stamp = Self.fmt.string(from: Date())
        let line = "\(stamp) \(msg)"
        oslog.notice("\(msg, privacy: .public)")
        lock.lock()
        lines.append(line)
        if lines.count > maxLines { lines.removeFirst(lines.count - maxLines) }
        let n = lines.count
        lock.unlock()
        DispatchQueue.main.async { self.lineCount = n }
        if let h = try? FileHandle(forWritingTo: fileURL) {
            h.seekToEndOfFile()
            h.write(Data((line + "\n").utf8))
            try? h.close()
        } else {
            try? (line + "\n").write(to: fileURL, atomically: true, encoding: .utf8)
        }
    }

    func text() -> String {
        lock.lock()
        defer { lock.unlock() }
        return lines.joined(separator: "\n")
    }

    func upload(server: SyncServer, device: String, version: String) {
        let body = text()
        log("upload diag \(body.utf8.count)B -> \(server.host):\(server.port)/devlog")
        guard let url = URL(string: "http://\(server.host):\(server.port)/devlog") else { return }
        var req = URLRequest(url: url, timeoutInterval: 25)
        req.httpMethod = "POST"
        req.setValue(device, forHTTPHeaderField: "X-Device")
        req.setValue(version, forHTTPHeaderField: "X-App-Version")
        req.setValue("text/plain; charset=utf-8", forHTTPHeaderField: "Content-Type")
        req.httpBody = Data(body.utf8)
        URLSession.shared.dataTask(with: req) { _, resp, err in
            let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
            DispatchQueue.main.async {
                self.lastUpload = (err == nil && code == 200)
                    ? "日志已发送到电脑（\(body.utf8.count) 字节）"
                    : "发送失败：\(err?.localizedDescription ?? "HTTP \(code)")"
                self.log("upload result code=\(code) err=\(err?.localizedDescription ?? "-")")
            }
        }.resume()
    }

    private static let fmt: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "MM-dd HH:mm:ss.SSS"
        return f
    }()
}
