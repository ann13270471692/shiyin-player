# -*- coding: utf-8 -*-
"""拾音同步服务器：在 Windows 上运行，向局域网广播 _shiyin._tcp 并提供音乐目录的 HTTP 下载。

用法:
    python sync_server.py "F:\\DeepSeek Workspace\\时事分析\\音乐集合"
    python sync_server.py <音乐目录> [端口，默认8450]

依赖(可选但强烈建议，用于手机自动发现):
    pip install zeroconf
"""
import hashlib
import json
import os
import re
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8450
ALLOWED_EXT = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".alac", ".lrc", ".txt", ".cue"}

if not os.path.isdir(ROOT):
    print("目录不存在:", ROOT)
    sys.exit(1)

# 影视金曲的剧名表（可选）：放在本脚本旁边，manifest 里给对应 mp3 带上 "movie" 字段
META_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "movie-meta.json")
_movie_meta = {}
_movie_meta_mtime = None


def load_movie_meta():
    global _movie_meta, _movie_meta_mtime
    try:
        mt = os.path.getmtime(META_PATH)
    except OSError:
        _movie_meta = {}
        return
    if mt == _movie_meta_mtime:
        return
    try:
        with open(META_PATH, encoding="utf-8") as f:
            _movie_meta = json.load(f)
        _movie_meta_mtime = mt
    except Exception:
        _movie_meta = {}


def build_manifest():
    load_movie_meta()
    items = []
    for name in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, name)
        if not os.path.isfile(p):
            continue
        if os.path.splitext(name)[1].lower() not in ALLOWED_EXT:
            continue
        st = os.stat(p)
        it = {"name": name, "size": st.st_size, "mtime": int(st.st_mtime)}
        mv = _movie_meta.get(os.path.splitext(name)[0])
        if mv:
            it["movie"] = mv
        items.append(it)
    return {"files": items}


# 列表缓存：曲库现在 2 万多条、每次现建要 0.4-0.7 秒，手机刷新频繁时这里先扛住。
MAN_TTL = 5.0
_man_cache = {"t": 0.0, "body": b"", "etag": "", "built": 0}


def manifest_body():
    now = time.time()
    if now - _man_cache["t"] >= MAN_TTL:
        body = json.dumps(build_manifest(), ensure_ascii=False).encode("utf-8")
        _man_cache["body"] = body
        _man_cache["etag"] = '"%s-%d"' % (hashlib.md5(body).hexdigest()[:16], len(body))
        _man_cache["t"] = now
        _man_cache["built"] += 1
        return _man_cache["body"], _man_cache["etag"], True
    return _man_cache["body"], _man_cache["etag"], False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 安静模式
        pass

    def do_GET(self):
        path = unquote(self.path.split("?")[0])
        if path == "/manifest.json":
            t0 = time.time()
            body, etag, built = manifest_body()
            ua = (self.headers.get("User-Agent") or "?")[:40]
            if self.headers.get("If-None-Match") == etag:
                print("读取列表: %s 304 未变 (UA=%s)" % (self.client_address[0], ua),
                      flush=True)
                self.send_response(304)
                self.send_header("ETag", etag)
                self.end_headers()
                return
            print("读取列表: %s -> %d 个文件, %s, %.0f ms, UA=%s"
                  % (self.client_address[0], body.count(b'"name"'),
                     "新建" if built else "缓存", (time.time() - t0) * 1000, ua), flush=True)
            self.send_response(200)
            self.send_header("ETag", etag)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        if path.startswith("/file/"):
            name = path[len("/file/"):]
            p = os.path.abspath(os.path.join(ROOT, name))
            if not (p == ROOT or p.startswith(ROOT + os.sep)) or not os.path.isfile(p):
                self.send_error(404)
                return
            size = os.path.getsize(p)
            start, end = 0, size - 1
            rng = self.headers.get("Range")
            partial = False
            if rng:
                m = re.match(r"bytes=(\d*)-(\d*)", rng)
                if m:
                    if m.group(1):
                        start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                    partial = True
            if start > end or start >= size:
                self.send_error(416)
                return
            self.send_response(206 if partial else 200)
            print("取文件: %s %s %s%s" % (self.client_address[0],
                                          "206" if partial else "200", name,
                                          "" if start is None else " from %d" % start),
                  flush=True)
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            with open(p, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    remaining -= len(chunk)
            return

        self.send_error(404)

    def do_POST(self):
        """手机把诊断日志推给电脑：POST /devlog，正文是日志文本。"""
        path = unquote(self.path.split("?")[0])
        if path != "/devlog":
            self.send_error(404)
            return
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 4 << 20)
        except ValueError:
            n = 0
        body = self.rfile.read(n) if n > 0 else b""
        dev = re.sub(r"[^A-Za-z0-9._-]", "", self.headers.get("X-Device") or "device") or "device"
        ver = re.sub(r"[^A-Za-z0-9._-]", "", self.headers.get("X-App-Version") or "")
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "devlog")
        os.makedirs(d, exist_ok=True)
        import time
        fn = os.path.join(d, "%s%s-%s.txt" % (dev, ("-v" + ver) if ver else "",
                                              time.strftime("%Y%m%d-%H%M%S")))
        with open(fn, "wb") as f:
            f.write(body)
        print("收到诊断日志: %s (%d 字节)" % (fn, len(body)), flush=True)
        out = json.dumps({"ok": True, "bytes": len(body)}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        try:
            self.wfile.write(out)
        except (BrokenPipeError, ConnectionResetError):
            pass


def get_local_ip():
    # 优先选「默认路由网关与本机 IP 同网段」的物理网卡（避开 VPN/虚拟网卡劫持），
    # 用 route print 的数字表解析，与系统语言无关。
    try:
        import subprocess
        out = subprocess.run(["route", "print", "0.0.0.0"], capture_output=True, text=True,
                             encoding="gbk", errors="ignore").stdout
        best = None
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                gw, iface = parts[2], parts[3]
                metric = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
                if iface.startswith("169.254.") or iface.startswith("127."):
                    continue
                same_subnet = gw.rsplit(".", 1)[0] == iface.rsplit(".", 1)[0]
                score = (0 if same_subnet else 1, metric)
                if best is None or score < best[0]:
                    best = (score, iface)
        if best:
            return best[1]
    except Exception:
        pass
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def advertise(ip):
    try:
        from zeroconf import ServiceInfo, Zeroconf
    except ImportError:
        print("[提示] 未安装 zeroconf，手机将无法自动发现（可手动输 IP）。安装: pip install zeroconf")
        return None
    import struct
    zc = Zeroconf(interfaces=[ip])  # 只从物理局域网网卡广播，避免 VPN 网卡抢组播
    host = re.sub(r"[^A-Za-z0-9-]", "-", socket.gethostname())[:20] or "pc"
    info = ServiceInfo(
        "_shiyin._tcp.local.",
        f"shiyin-{host}._shiyin._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=PORT,
        properties={"root": "music"},
    )
    zc.register_service(info)
    print("已广播 mDNS 服务: _shiyin._tcp")
    return zc, info


def main():
    ip = get_local_ip()
    print(f"拾音同步服务器")
    print(f"  目录: {ROOT}")
    print(f"  地址: http://{ip}:{PORT}")
    print(f"  手机 App「导入」页应能自动发现；若不能，手动输入上面这个 IP")
    print("  Ctrl+C 停止")
    adv = advertise(ip)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if adv:
            zc, info = adv
            zc.unregister_service(info)
            zc.close()
        server.server_close()


if __name__ == "__main__":
    main()
