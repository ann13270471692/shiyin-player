# -*- coding: utf-8 -*-
# 精确撤销：外语名冒充剧名 / 唱片名冒充剧名 / 语种版本后缀
import io, json, os, re, sys
T = r'F:\Temp'
REC = os.path.join(T, 'pop-movie.json')
META = r'F:\DeepSeek Workspace\时事分析\shiyin-player\SyncServer\movie-meta.json'
FOREIGN = re.compile(u'[\uac00-\ud7af\u1100-\u11ff\u3041-\u3096\u30a1-\u30fa\u30fc\u0400-\u04ff\u0e00-\u0e7f]')
ALBUMY = re.compile(u'Vol\\.|\\d+集|雷射|精选|金曲|纪念|Soundtrack|soundtrack|原声|专辑|EP|单曲|Demo|小样', re.I)
LANGV = re.compile(u'粤语|国语版|完整版|现场|Live|演奏|伴奏|纯音乐', re.I)
def main(write):
    rec = json.load(io.open(REC, encoding='utf-8'))
    meta = json.load(io.open(META, encoding='utf-8'))
    drop = []
    for stem, v in rec.items():
        if not isinstance(v, dict):
            continue
        dn = (v.get('drama') or u'').strip()
        how = v.get('how')
        why = u''
        if FOREIGN.search(dn):
            why = u'外语名（不是华语影视）'
        elif ALBUMY.search(dn):
            why = u'唱片名冒充剧名'
        elif how in ('pool', 'libhit') and LANGV.search(dn):
            why = u'语种/版本后缀'
        if why:
            drop.append((stem, v.get('year'), (v.get('artist') or u''), (v.get('name') or u''), dn, why))
    print('要撤销 %d 条' % len(drop))
    for d in drop[:14]:
        print(u'  %s %-12s %-16s <- 《%s》  %s' % (d[1], (d[2] or u'')[:12], d[3][:16], d[4][:14], d[5]))
    if not write:
        print(u'（dry run）')
        return
    for stem, y, ar, nm, dn, why in drop:
        rec.pop(stem, None)
        meta.pop(stem, None)
    json.dump(rec, io.open(REC + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(REC + '.tmp', REC)
    json.dump(meta, io.open(META + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(META + '.tmp', META)
    print(u'已写盘：记账 %d / 剧名表 %d' % (len(rec), len(meta)))
main('--write' in sys.argv)
