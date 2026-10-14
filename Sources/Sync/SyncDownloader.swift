import Foundation

struct RemoteFile: Codable, Identifiable, Hashable {
    let name: String
    let size: Int
    let mtime: Int
    /// 影视金曲的剧名（服务器 movie-meta.json 提供，普通歌没有这个字段）
    let movie: String?
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
    /// 每个文件上次下载时对应的电脑 mtime，用来判断"电脑上改过没有"
    @Published private(set) var knownMtimes: [String: Int] =
        (UserDefaults.standard.dictionary(forKey: "remoteMtimes") as? [String: Int]) ?? [:]
    @Published private(set) var state: DownloadState = .idle
    @Published private(set) var activeFile: String?
    @Published private var cancelRequested = false
    /// 在手机上被删过的歌（含它的歌词）：导入页标成「已删除」，不会被自动重下；
    /// 手动重新下载成功后标记自动清掉。
    @Published private(set) var deletedNames: Set<String> =
        Set(UserDefaults.standard.stringArray(forKey: "deletedNames") ?? [])

    func markDeleted(_ name: String) {
        guard !name.isEmpty, !deletedNames.contains(name) else { return }
        deletedNames.insert(name)
        UserDefaults.standard.set(Array(deletedNames), forKey: "deletedNames")
        DebugLog.shared.log("mark deleted \(name)")
    }

    func clearDeleted(_ name: String) {
        guard deletedNames.remove(name) != nil else { return }
        UserDefaults.standard.set(Array(deletedNames), forKey: "deletedNames")
        DebugLog.shared.log("unmark deleted \(name)")
    }

    nonisolated private let box = TaskBox()

    func rescanLocal() {
        let dir = LibraryStore.musicDirectory()
        localNames = Set((try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? [])
        markStale(remoteFiles)
    }

    /// 手机副本被删除后：去掉「已下载」记录与记住的电脑 mtime，
    /// 让导入页把该文件重新显示为「未下载」，之后可以重新下载。
    func forgetLocalCopy(of url: URL) {
        let name = url.lastPathComponent
        localNames.remove(name)
        staleNames.remove(name)
        progress.removeValue(forKey: name)
        speedText.removeValue(forKey: name)
        knownMtimes.removeValue(forKey: name)
        UserDefaults.standard.set(knownMtimes, forKey: "remoteMtimes")
        // 删掉的就是手机副本：标成「已删除」，导入页一眼能看出来它为什么又变成没下了
        markDeleted(name)
        let lrc = (name as NSString).deletingPathExtension + ".lrc"
        if remoteFiles.contains(where: { $0.name == lrc }) { markDeleted(lrc) }
    }

    func cancel() {
        cancelRequested = true
        box.cancelCurrent()
    }

    private var lastEtag: String?
    private var lastManifest: [RemoteFile]?

    func fetchManifest(from server: SyncServer) async {
        state = .running
        defer { if case .running = state { state = .idle } }
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 15
        cfg.waitsForConnectivity = false
        let session = URLSession(configuration: cfg)
        defer { session.invalidateAndCancel() }
        let t0 = CFAbsoluteTimeGetCurrent()
        guard let url = URL(string: "http://\(server.host):\(server.port)/manifest.json") else {
            DebugLog.shared.log("manifest BAD URL \(server.host):\(server.port)")
            state = .failed("服务器地址格式不对")
            return
        }
        var req = URLRequest(url: url)
        if let e = lastEtag { req.setValue(e, forHTTPHeaderField: "If-None-Match") }
        do {
            let (data, response) = try await session.data(for: req)
            let http = response as? HTTPURLResponse
            let ms = Int((CFAbsoluteTimeGetCurrent() - t0) * 1000)
            if http?.statusCode == 304, let old = lastManifest {
                DebugLog.shared.log("manifest 304 未变 (\(ms) ms)")
                remoteFiles = old
                rescanLocal()
                markStale(old)
                return
            }
            guard let m = try? JSONDecoder().decode(Manifest.self, from: data) else {
                DebugLog.shared.log("manifest BAD JSON \(data.count) bytes")
                state = .failed("文件列表读不懂：服务器返回的内容不对")
                return
            }
            lastManifest = m.files
            if let etag = http?.value(forHTTPHeaderField: "ETag") { lastEtag = etag }
            DebugLog.shared.log("manifest ok \(m.files.count) files in \(ms) ms")
            remoteFiles = m.files
            rescanLocal()
            markStale(m.files)
        } catch {
            DebugLog.shared.log("manifest FAIL \(server.host):\(server.port): \(error)")
            state = .failed("无法读取文件列表：检查服务器是否在运行、IP 是否正确")
        }
    }

    func markStale(_ files: [RemoteFile]) {
        let dir = LibraryStore.musicDirectory()
        var s: Set<String> = []
        for f in files where localNames.contains(f.name) {
            let path = dir.appendingPathComponent(f.name).path
            let attrs = try? FileManager.default.attributesOfItem(atPath: path)
            let size = (attrs?[.size] as? Int) ?? -1
            // 大小不同：一定是旧文件
            if size != f.size {
                s.insert(f.name)
                continue
            }
            // 记住过这台电脑上的 mtime：直接比它，这才是"电脑上改过没有"
            if let known = knownMtimes[f.name] {
                if known != f.mtime { s.insert(f.name) }
                continue
            }
            // 从没记过：本地 mtime 是下载时间，跟电脑上的原始 mtime 必然不同，
            // 只能先粗判一次（会全部标记一轮），重新下载后就按记下的 mtime 精确判断
            let m = (attrs?[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0
            if abs(m - Double(f.mtime)) > 2 { s.insert(f.name) }
        }
        staleNames = s
    }

    private func recordMtime(_ name: String, _ mtime: Int) {
        knownMtimes[name] = mtime
        UserDefaults.standard.set(knownMtimes, forKey: "remoteMtimes")
    }

    func download(_ files: [RemoteFile], from server: SyncServer) async {
        state = .running
        cancelRequested = false
        DebugLog.shared.log("download begin n=\(files.count)")
        for f in files {
            if cancelRequested { break }
            await downloadOne(f, server: server)
        }
        DebugLog.shared.log("download end cancelled=\(cancelRequested)")
        activeFile = nil
        state = cancelRequested ? .cancelled : .done
        markStale(remoteFiles)
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
        DebugLog.shared.log("dl FAIL \(f.name)")
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
        if await MainActor.run(body: { self.staleNames.contains(name) }) {
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
                self.recordMtime(name, f.mtime)
                self.clearDeleted(name)      // 重新下回来了，「已删除」标记自动消掉
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
                self.recordMtime(name, f.mtime)
                self.clearDeleted(name)      // 重新下回来了，「已删除」标记自动消掉
            }
            return true
        }
        // 未完成：保留 .part，下次自动续传
        return false
    }
}
