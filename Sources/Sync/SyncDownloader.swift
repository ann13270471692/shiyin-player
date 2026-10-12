import Foundation

struct RemoteFile: Codable, Identifiable, Hashable {
    let name: String
    let size: Int
    let mtime: Int
    var id: String { name }
}

private struct Manifest: Codable { let files: [RemoteFile] }

enum DownloadState: Equatable {
    case idle, running, done, cancelled, failed(String)
}

/// 线程安全地持有当前下载任务，让「停止下载」能立刻中断
private final class TaskBox: @unchecked Sendable {
    private let lock = NSLock()
    private var task: URLSessionTask?
    func set(_ t: URLSessionTask?) { lock.lock(); task = t; lock.unlock() }
    func cancelCurrent() { lock.lock(); let t = task; lock.unlock(); t?.cancel() }
}

/// 流式接收：数据到达即写盘，不再整文件缓冲在内存里
private final class StreamDelegate: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let handle: FileHandle
    private let resumedFrom: Int
    private var written: Int
    private var status = 0
    private var finished = false
    private var onFinish: ((Error?) -> Void)?
    private let lock = NSLock()
    private let onChunk: (_ totalWritten: Int) -> Void

    init(handle: FileHandle, start: Int, onChunk: @escaping (_ totalWritten: Int) -> Void) {
        self.handle = handle
        self.resumedFrom = start
        self.written = start
        self.onChunk = onChunk
    }

    var totalWritten: Int { lock.lock(); defer { lock.unlock() }; return written }

    func setFinish(_ cb: @escaping (Error?) -> Void) {
        lock.lock(); onFinish = cb; lock.unlock()
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask,
                    didReceive response: URLResponse,
                    completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        if let http = response as? HTTPURLResponse {
            lock.lock(); status = http.statusCode; lock.unlock()
            // 服务器忽略 Range 时从头写，避免把整份内容追加到断点之后
            if http.statusCode == 200 && resumedFrom > 0 {
                handle.truncateFile(atOffset: 0)
                lock.lock(); written = 0; lock.unlock()
            }
        }
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        handle.write(data)
        lock.lock(); written += data.count; let total = written; lock.unlock()
        onChunk(total)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        lock.lock()
        if finished { lock.unlock(); return }
        finished = true
        let cb = onFinish
        lock.unlock()
        cb?(error)
    }
}

@MainActor
final class SyncDownloader: ObservableObject {
    @Published private(set) var remoteFiles: [RemoteFile] = []
    @Published private(set) var progress: [String: Double] = [:]   // -1 = 失败
    @Published private(set) var speedText: [String: String] = [:]
    @Published private(set) var localNames: Set<String> = []
    /// 电脑上已更新（mtime 不一致）的本地文件，需要重新拉取
    @Published private(set) var staleNames: Set<String> = []
    @Published private(set) var state: DownloadState = .idle
    @Published private(set) var activeFile: String?
    @Published private var cancelRequested = false

    nonisolated private let box = TaskBox()

    func rescanLocal() {
        let dir = LibraryStore.musicDirectory()
        localNames = Set((try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? [])
    }

    func cancel() {
        cancelRequested = true
        box.cancelCurrent()
    }

    func fetchManifest(from server: SyncServer) async {
        state = .running
        defer { if case .running = state { state = .idle } }
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 15
        cfg.waitsForConnectivity = false
        let session = URLSession(configuration: cfg)
        defer { session.invalidateAndCancel() }
        guard let url = URL(string: "http://\(server.host):\(server.port)/manifest.json"),
              let (data, _) = try? await session.data(from: url),
              let m = try? JSONDecoder().decode(Manifest.self, from: data)
        else {
            state = .failed("无法读取文件列表：检查服务器是否在运行、IP 是否正确")
            return
        }
        remoteFiles = m.files
        rescanLocal()
        markStale(m.files)
    }

    private func markStale(_ files: [RemoteFile]) {
        let dir = LibraryStore.musicDirectory()
        var s: Set<String> = []
        for f in files where localNames.contains(f.name) {
            let path = dir.appendingPathComponent(f.name).path
            let attrs = try? FileManager.default.attributesOfItem(atPath: path)
            let m = (attrs?[.modificationDate] as? Date)?.timeIntervalSince1970
            if m == nil || abs(m! - Double(f.mtime)) > 2 {
                s.insert(f.name)
            }
        }
        staleNames = s
    }

    func download(_ files: [RemoteFile], from server: SyncServer) async {
        state = .running
        cancelRequested = false
        for f in files where !localNames.contains(f.name) || staleNames.contains(f.name) {
            if cancelRequested { break }
            await downloadOne(f, server: server)
        }
        activeFile = nil
        state = cancelRequested ? .cancelled : .done
    }

    nonisolated private func downloadOne(_ f: RemoteFile, server: SyncServer) async {
        await MainActor.run {
            self.activeFile = f.name
            self.progress[f.name] = 0.0
            self.speedText[f.name] = "连接中…"
        }
        for attempt in 1...4 {
            let ok = await downloadAttempt(f, server: server)
            if ok { return }
            let stop: Bool = await MainActor.run { self.cancelRequested }
            if stop { break }
            try? await Task.sleep(nanoseconds: UInt64(attempt) * 700_000_000)
        }
        await MainActor.run {
            self.progress[f.name] = -1
            self.speedText[f.name] = nil
        }
    }

    nonisolated private func downloadAttempt(_ f: RemoteFile, server: SyncServer) async -> Bool {
        let dir = await MainActor.run { LibraryStore.musicDirectory() }
        let dest = dir.appendingPathComponent(f.name)
        let tmp = URL(fileURLWithPath: dest.path + ".part")
        let fm = FileManager.default
        let name = f.name
        let size = f.size
        // 电脑上文件已更新：旧断点内容不同，必须整份重下
        if await MainActor.run { self.staleNames.contains(name) } {
            try? fm.removeItem(at: tmp)
        }

        var start = 0
        if let attrs = try? fm.attributesOfItem(atPath: tmp.path),
           let partial = attrs[.size] as? Int {
            start = partial
        }
        if start > size {
            try? fm.removeItem(at: tmp)
            start = 0
        }
        if start == size {   // 断点已完整
            try? fm.removeItem(at: dest)
            try? fm.moveItem(at: tmp, to: dest)
            await MainActor.run {
                self.progress[name] = 1
                self.speedText[name] = nil
                self.localNames.insert(name)
            }
            return true
        }

        var handle: FileHandle?
        if start > 0 { handle = try? FileHandle(forWritingTo: tmp) }
        if handle == nil {
            try? fm.removeItem(at: tmp)
            fm.createFile(atPath: tmp.path, contents: nil)
            handle = try? FileHandle(forWritingTo: tmp)
            start = 0
        }
        guard let fh = handle else { return false }
        if start > 0 { fh.seekToEndOfFile() }

        let encoded = name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? name
        guard let url = URL(string: "http://\(server.host):\(server.port)/file/\(encoded)") else {
            try? fh.close()
            return false
        }

        var lastReport = Date()
        var lastBytes = start
        let delegate = StreamDelegate(handle: fh, start: start) { total in
            let now = Date()
            guard now.timeIntervalSince(lastReport) >= 0.3 else { return }
            let dt = now.timeIntervalSince(lastReport)
            let mbps = Double(total - lastBytes) / max(dt, 0.001) / 1_048_576
            lastReport = now
            lastBytes = total
            let p = size > 0 ? Double(total) / Double(size) : 0
            let txt = String(format: "%.1f MB/s", mbps)
            Task { @MainActor in
                self.progress[name] = min(0.99, p)
                self.speedText[name] = txt
            }
        }

        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 30        // 30 秒无数据即判定断开，快速重试
        cfg.timeoutIntervalForResource = 1800
        cfg.waitsForConnectivity = false          // 连不上就报错，不再无限等待
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        let session = URLSession(configuration: cfg, delegate: delegate, delegateQueue: nil)

        var request = URLRequest(url: url)
        if start > 0 { request.setValue("bytes=\(start)-", forHTTPHeaderField: "Range") }

        let task = session.dataTask(with: request)
        box.set(task)

        let err: Error? = await withCheckedContinuation { (cont: CheckedContinuation<Error?, Never>) in
            delegate.setFinish { e in cont.resume(returning: e) }
            task.resume()
        }

        box.set(nil)
        session.finishTasksAndInvalidate()
        try? fh.close()

        let total = delegate.totalWritten
        if total >= size {
            try? fm.removeItem(at: dest)
            try? fm.moveItem(at: tmp, to: dest)
            await MainActor.run {
                self.progress[name] = 1
                self.speedText[name] = nil
                self.localNames.insert(name)
            }
            return true
        }
        // 未完成：保留 .part，下次自动续传
        return false
    }
}
