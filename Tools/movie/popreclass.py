# -*- coding: utf-8 -*-
r"""把流行库里本来就是影视金曲的歌认出来：计入影视额度 + 写剧名，不重命名不重下。
匹配路径：acquire-state 的 ok 条目 -> 当年池子里按 歌名+歌手 找回 id -> 网易云权威资料看证据。
用法：python F:\Temp\popreclass.py [--write]
"""
import json, os, re, sys, glob
sys.path.insert(0, r'F:\Temp')
import acquire
import moviefill as M

acquire._host_min['music.163.com'] = 3.0      # 三个下载进程在跑，这里更温和
POPSTATE = r'F:\Temp\acquire-state.json'
POOLS = r'F:\Temp\pools'
REC = r'F:\Temp\pop-movie.json'
META = r'F:\DeepSeek Workspace\时事分析\shiyin-player\SyncServer\movie-meta.json'
OUTLOG = r'F:\Temp\popreclass.log'


def log(s):
    with acquire.lock:
        open(OUTLOG, 'a', encoding='utf-8').write(s + '\n')


def main():
    do = '--write' in sys.argv
    st = json.load(open(POPSTATE, encoding='utf-8'))
    ok = {k: v for k, v in st.items() if v.get('state') == 'ok'}
    rec = json.load(open(REC, encoding='utf-8'))
    print('流行 ok %d | 已认定影视 %d' % (len(ok), len(rec)))

    # 年份 -> (歌名,歌手) -> id
    idx = {}
    for p in glob.glob(os.path.join(POOLS, '*.json')):
        y = os.path.splitext(os.path.basename(p))[0]
        if not y.isdigit():
            continue
        try:
            rows = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        for r in rows:
            if not isinstance(r, dict) or not r.get('id'):
                continue
            idx.setdefault(y, {})[(acquire.norm(r['name']), acquire.norm(r['artist']))] = r['id']

    todo = []
    unmatched = 0
    for k, v in ok.items():
        y = k[:4]
        f = v.get('file') or ''
        if f in rec:
            continue
        parts = f.split(' - ')
        if len(parts) < 3:
            unmatched += 1
            continue
        artist, title = parts[1], parts[2]
        cid = idx.get(y, {}).get((acquire.norm(title), acquire.norm(artist)))
        if not cid:
            unmatched += 1
            continue
        todo.append((k, f, int(cid), int(y)))
    print('待查 %d（池里找不到 id 的 %d）' % (len(todo), unmatched))

    ids = [t[2] for t in todo]
    det = {}
    for i in range(0, len(ids), 80):
        det.update(M.details(ids[i:i + 80]))
        if i % 1600 == 0:
            print('  资料 %d/%d' % (min(i + 80, len(ids)), len(ids)), flush=True)
    print('拿到资料 %d' % len(det))

    hits = []
    for k, f, cid, y in todo:
        d = det.get(cid)
        if not d:
            continue
        al, nm, ab = d['alias'], d['name'], d['album']
        m = M.BOOK.search(al) or M.BOOK.search(nm)
        drama = ''
        if m:
            drama = m.group(1).strip()
        else:
            mo = M.OST.search(al) or M.OST.search(ab)
            if mo:
                drama = M.clean_pre(ab[:M.OST.search(ab).start()]) if M.OST.search(ab) else M.clean_pre(ab)
                drama = drama or M.clean_pre(ab)
            elif ab and (ab == nm or nm in ab):
                drama = M.clean_pre(ab)
        if not drama:
            continue
        hits.append({'file': f, 'drama': drama, 'alias': al, 'id': cid, 'year': y,
                     'pub': d.get('pub') or 0, 'album': d['album'], 'name': nm,
                     'same': acquire.norm(drama) == acquire.norm(nm) or acquire.norm(drama) in acquire.norm(nm)})

    json.dump(hits, open(r'F:\Temp\popreclass-hits.json', 'w', encoding='utf-8'),
              ensure_ascii=False)
    print('认出影视金曲 %d 首（占待查 %.1f%%），命中已落盘'
          % (len(hits), 100.0 * len(hits) / max(1, len(todo))))
    for h in hits[:10]:
        log('REC %s | %s | %s' % (h['file'][:40], h['drama'], h['alias'][:30]))
        print('  ', h['file'][:44], '->', h['drama'], '(pub %s, 同名 %s)' % (h['pub'], h['same']))

    if not do:
        print('（试运行：加 --write 才写 pop-movie.json / movie-meta.json）')
        return

    good = [h for h in hits if h['same'] or (h['pub'] and abs(h['pub'] - h['year']) <= 2)]
    print('年份一致（同名或专辑年份±2）可计入 %d / %d' % (len(good), len(hits)))
    for h in good:
        f, dr, al, cid, y = h['file'], h['drama'], h['alias'], h['id'], h['year']
        rec[f] = {'alias': al, 'drama': dr, 'id': cid, 'year': y}
    tmp = REC + '.tmp'
    json.dump(rec, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
    os.replace(tmp, REC)
    print('pop-movie.json 现在 %d 条' % len(rec))

    try:
        meta = json.load(open(META, encoding='utf-8'))
    except Exception:
        meta = {}
    n = 0
    for h in good:
        if h['file'] not in meta:
            n += 1
        meta[h['file']] = h['drama']
    tmp = META + '.tmp'
    json.dump(meta, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    os.replace(tmp, META)
    print('movie-meta.json 新增 %d，共 %d 条' % (n, len(meta)))

    from collections import Counter
    c = Counter(int(v.get('year') or 0) for v in rec.values())
    print('按年影视额度（认定部分）Top:', sorted(c.items(), key=lambda x: -x[1])[:8])


main()
