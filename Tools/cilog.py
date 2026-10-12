"""取最近一次 CI 失败的构建日志，过滤出编译错误。"""
import sys, re
sys.path.insert(0, r'F:\DeepSeek Workspace\时事分析\shiyin-player\Tools')
import watch_ci as w

token = w.get_token()
runs = w.api(f"https://api.github.com/repos/{w.OWNER}/{w.REPO}/actions/runs?per_page=5", token)
run = runs["workflow_runs"][0]
print("run", run["id"], run["head_sha"][:8], run["conclusion"])
for j in w.api(run["jobs_url"], token)["jobs"]:
    if j.get("conclusion") == "success":
        continue
    print("job:", j["name"], j["conclusion"])
    log = w.api(j["url"] + "/logs", token, raw=True).decode("utf-8", "replace")
    pats = re.compile(r"(error:|error E|fatal error|The following build errors|❌|BUILD FAILED|error CS|note:)", re.I)
    hits = [l for l in log.splitlines() if pats.search(l)]
    for l in hits[:40]:
        print("  ", l.strip()[:300])
    if not hits:
        print("   (no error lines; tail:)")
        for l in log.splitlines()[-25:]:
            print("  ", l.strip()[:300])
