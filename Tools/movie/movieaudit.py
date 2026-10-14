# -*- coding: utf-8 -*-
r"""审计已入库的影视金曲：用候选 id 的网易云权威资料复核「发行年份 + 影视证据」。
不合格 -> 删 mp3/lrc/part，并从所属 state 文件里删掉该槽位（腾出来重下合格的）。
合格   -> 剧名写进 F:\Temp\movie-meta-audit.json。
用法：python F:\Temp\movieaudit.py            # 只报告
      python F:\Temp\movieaudit.py --write   # 真的删/写
"""
import json, os, sys, time
sys.path.insert(0, r'F:\Temp')
import acquire
import moviefill as M

acquire._host_min['music.163.com'] = 1.1
LIB = M.LIB
LOG = r'F:\Temp\movie-audit.log'
OUT = r'F:\Temp\movie-meta-audit.json'
STATES = [r'F:\Temp\movie-state.json', r'F:\Temp\movie-state-a.json',
          r'F:\Temp\movie-state-b.json', r'F:\Temp\movie-state-c.json']
TAG = M.TAG


def log(s):
    with acquire.lock:
        open(LOG, 'a', encoding='utf-8').write(s + '\n')
        print(s, flush=True)


def main():
    do = '--write' in sys.argv
    data = {}
    for sp in STATES:
        if os.path.exists(sp):
            try:
                data[sp] = json.load(open(sp, encoding='utf-8'))
            except Exception as e:
                print('跳过', sp, e)
    ok = [(sp, k, v) for sp, d in data.items() for k, v in d.items()
          if v.get('state') == 'ok']
    print('%s 模式 | ok 条目 %d' % ('写入' if do else '试运行', len(ok)))

    ids = [int(v['id']) for _, _, v in ok if v.get('id')]
    print('取资料 %d 个 id …' % len(ids))
    det = M.details(ids)
    print('拿到 %d 个' % len(det))

    meta = {}
    drop = []
    unver = 0
    for sp, k, v in ok:
        cid = int(v.get('id') or 0)
        year = int(k[:4])
        if cid not in det:
            unver += 1
            continue
        drama, bad = M.gate({'id': cid}, det, year)
        if bad:
            drop.append((sp, k, v, bad))
        elif drama:
            meta[v.get('file', '')[:-4] if v.get('file', '').endswith('.mp3')
                  else v.get('file', '')] = drama

    print('合格带剧名 %d | 要剔除 %d | 查不到资料(保留) %d' % (len(meta), len(drop), unver))
    for sp, k, v, bad in drop[:20]:
        log('DROP %s %-30s %s' % (k, (v.get('file') or '')[:30], bad[:60]))

    if not do:
        print('（试运行：加 --write 才删文件、才写剧名）')
        return

    removed = 0
    for sp, k, v, bad in drop:
        f = v.get('file') or ''
        for ext in ('.mp3', '.lrc', '.mp3.part', '.part'):
            p = os.path.join(LIB, f + ext) if not f.endswith('.mp3') else os.path.join(LIB, f)
            if ext == '.mp3' and f.endswith('.mp3'):
                p = os.path.join(LIB, f)
            try:
                if os.path.exists(p):
                    os.remove(p)
                    if ext == '.mp3':
                        removed += 1
            except Exception as e:
                log('删除失败 %s %s' % (p, e))
        data[sp].pop(k, None)
        log('DROP %s %-34s %s' % (k, f[:34], bad[:60]))
    for sp, d in data.items():
        tmp = sp + '.tmp'
        json.dump(d, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(tmp, sp)
    print('删除 mp3 %d 个，state 已清理' % removed)

    try:
        cur = json.load(open(OUT, encoding='utf-8'))
    except Exception:
        cur = {}
    cur.update(meta)
    json.dump(cur, open(OUT + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False)
    os.replace(OUT + '.tmp', OUT)
    print('剧名写入 %s（%d 条）' % (OUT, len(cur)))

    from collections import Counter
    c = Counter(k[:4] for sp, d in data.items() for k, v in d.items() if v.get('state') == 'ok')
    print('清理后各年 ok:', ' '.join('%s:%d' % (y, c[y]) for y in sorted(c)))


main()
