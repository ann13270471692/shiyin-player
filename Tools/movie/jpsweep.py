# -*- coding: utf-8 -*-
# 清理库里混进来的日文歌（按文件名判定，离线）：
#   默认只列出来，加 --write 才真删（同时删 .lrc 并从 state 里剔除）
import json
import os
import re
import sys

LIB = r'F:\DeepSeek Workspace\时事分析\音乐集合'
STATES = [r'F:\Temp\movie-state.json', r'F:\Temp\movie-state-a.json',
          r'F:\Temp\movie-state-b.json', r'F:\Temp\movie-state-c.json']
NAME = re.compile(r'^(\d{4})-(\d+) - (.+) - (.+?)(?:【影视】)?\.mp3$')
KANA = re.compile(u'[\u3041-\u3096\u30a1-\u30fa\u30fc]')  # 不含「・」U+30FB：中文标题也用它


def main(write):
    hits = []
    for f in sorted(os.listdir(LIB)):
        m = NAME.match(f)
        if not m:
            continue
        artist, title = m.group(3), m.group(4)
        if KANA.search(artist) or KANA.search(title):
            hits.append(f)
    print('日文文件 %d 个' % len(hits))
    for f in hits[:40]:
        print('  ', f)
    if not write:
        print('（dry run，加 --write 才删）')
        return
    base = set(os.path.splitext(f)[0] for f in hits)
    for f in hits:
        stem = os.path.splitext(f)[0]
        for ext in ('.mp3', '.lrc'):
            p = os.path.join(LIB, stem + ext)
            try:
                os.remove(p)
            except Exception:
                pass
    dropped = 0
    for sp in STATES:
        if not os.path.exists(sp):
            continue
        try:
            st = json.load(open(sp, encoding='utf-8'))
        except Exception:
            continue
        keep = {}
        for k, v in st.items():
            fn = (v.get('file') or '') + '.mp3'
            if fn in base or os.path.splitext(v.get('file') or '') in base:
                dropped += 1
                continue
            keep[k] = v
        if len(keep) != len(st):
            json.dump(keep, open(sp + '.tmp', 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1)
            os.replace(sp + '.tmp', sp)
    print('已删除 %d 首，state 剔除 %d 条' % (len(base), dropped))


if __name__ == '__main__':
    main('--write' in sys.argv[1:])
