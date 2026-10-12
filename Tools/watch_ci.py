# -*- coding: utf-8 -*-
"""轮询 GitHub Actions 构建状态；失败时下载失败 job 日志尾部。凭据经 git credential fill 获取，不落盘。"""
import json
import subprocess
import sys
import time
import urllib.request

OWNER = "ann13270471692"
REPO = "shiyin-player"


def get_token():
    p = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True,
    )
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line[9:]
    raise SystemExit("no token from git credential fill: " + p.stderr[:200])


def api(url, token, raw=False):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "User-Agent": "shiyin-build",
        "Accept": "application/vnd.github+json",
    })
    opener = urllib.request.build_opener(_NoRedir)
    try:
        r = opener.open(req)
        data = r.read()
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location")
        if e.code in (301, 302, 303, 307, 308) and loc:
            data = urllib.request.urlopen(
                urllib.request.Request(loc, headers={"User-Agent": "shiyin-build"})).read()
        else:
            raise
    return data if raw else json.loads(data)


class _NoRedir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    token = get_token()
    run = None
    for _ in range(80):  # 最多 ~40 分钟
        time.sleep(30)
        try:
            runs = api(f"https://api.github.com/repos/{OWNER}/{REPO}/actions/runs?per_page=5", token)
        except Exception as e:
            print("api err:", e, flush=True)
            continue
        wf = [r for r in runs.get("workflow_runs", []) if r.get("name") == "build"]
        if not wf:
            print("no run yet", flush=True)
            continue
        run = wf[0]
        st, con = run["status"], run.get("conclusion")
        print(f"run {run['id']}: {st} {con or ''}", flush=True)
        if st == "completed":
            break
    if not run or run.get("conclusion") != "success":
        concl = run.get("conclusion") if run else "none"
        print(f"BUILD NOT SUCCESS: {concl}", flush=True)
        if run:
            jobs = api(run["jobs_url"], token)["jobs"]
            for j in jobs:
                if j.get("conclusion") == "failure":
                    log = api(j["url"] + "/logs", token, raw=True).decode("utf-8", "replace")
                    lines = log.splitlines()
                    errs = [ln for ln in lines if "error:" in ln or "ERROR" in ln or "fatal" in ln]
                    print("=== error lines ===", flush=True)
                    for ln in errs[:60]:
                        print(ln, flush=True)
                    print("=== tail 80 ===", flush=True)
                    for ln in lines[-80:]:
                        print(ln, flush=True)
        sys.exit(1)
    # 成功：下载工件
    arts = api(f"https://api.github.com/repos/{OWNER}/{REPO}/actions/artifacts?per_page=50", token)["artifacts"]
    target = next((a for a in arts if a["name"] == "Shiyin-unsigned" and not a["expired"]), None)
    if not target:
        print("artifact not found", flush=True)
        sys.exit(1)
    blob = api(target["download_url"], token, raw=True)
    out = r"F:\DeepSeek Workspace\时事分析\shiyin-player\build\Shiyin-unsigned.zip"
    import os
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(blob)
    print(f"ARTIFACT SAVED: {out} ({len(blob)} bytes)", flush=True)


if __name__ == "__main__":
    main()
