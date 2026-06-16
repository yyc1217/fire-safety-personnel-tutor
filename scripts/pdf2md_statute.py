#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""政府公報型 PDF 法規（檢修基準／認可基準）→ 結構化 Markdown。

適用於以 `pdftotext -layout` 匯出、具下列階層之基準類法規：
    第X章 → 一、二、（中項）→ （一）（二）→ １、２、→ （１）（２）→ A. B.

轉換規則：
- 去除頁首（行政院公報…）、頁尾頁碼（N-N、純數字、羅馬數字）、目錄頁
- 章標題 `第X章 名稱` → `## 第X章 名稱`
- 其餘階層標記保留原樣；硬斷行之續行接回上一段
- 附圖／附表（多為圖例、表單）無文字層，於文末統一附原始 PDF 連結

用法： python3 scripts/pdf2md_statute.py <來源.pdf> <輸出.md> "<法規全名>" "<版本日期>" [來源說明]
"""
import sys, re

# 章標題：第一章 / 第二十四章之一 …（行末可能帶目錄頁碼，本文則無）
RE_CHAP = re.compile(r'^第([一二三四五六七八九十]+)章(之[一二三四五六七八九十]+)?\s+(.+?)\s*$')
# 中項：一、二、…（全形頓號）
RE_MID  = re.compile(r'^([一二三四五六七八九十]+)、')
# 各層起始標記（用於判斷是否為續行）
RE_MARK = re.compile(
    r'^('
    r'第[一二三四五六七八九十]+章|'
    r'[一二三四五六七八九十]+、|'                     # 一、
    r'（[一二三四五六七八九十]+）|'                   # （一）
    r'\(\s*[一二三四五六七八九十]+\s*\)|'             # (一) 半形括號
    r'[１２３４５６７８９０]+、|'                       # １、(全形)
    r'（[１２３４５６７８９０]+）|'                     # （１）(全形)
    r'\([0-9]+\)|[0-9]+[.、]|'                          # (1) / 1.
    r'[A-Z][.．]|'                                  # A. / Ａ．
    r'壹、|貳、|參、|肆、|伍、|陸、|柒、|捌、|玖、|拾、'
    r')')

def is_noise(line):
    t = line.strip()
    if not t:
        return False  # 空行另行處理
    # 頁首：行政院公報 及其卷期續行
    if t.startswith('行政院公報'):
        return True
    if re.match(r'^第?\s*\d+\s*卷', t) or re.match(r'^第?\s*\d+\s*期', t):
        return True
    if re.match(r'^[第卷期\d\s]+內政篇$', t):
        return True
    # 頁尾頁碼：N-N、N-N-N、純數字、羅馬數字
    if re.match(r'^[0-9]+(-[0-9]+){1,2}$', t):
        return True
    if re.match(r'^[0-9]+$', t) and len(t) <= 4:
        return True
    if re.match(r'^[IVXLﾞ]+$', t):
        return True
    return False

# 壹貳參…大段標題（認可基準型）：行首大寫數字＋頓號，標題短且**不以中文數字開頭**
# （排除頁眉如「壹、二十一」「壹、三十一」之頁碼型running header）
RE_DASEC = re.compile(r'^(壹|貳|參|肆|伍|陸|柒|捌|玖|拾)、\s*([^一二三四五六七八九十百\d\s].*?)\s*$')

def is_toc_line(line):
    """目錄行：含點引導線（………）並以頁碼結尾，或『第X章 名稱 …… N-N』。"""
    t = line.strip()
    if re.search(r'[.．…]{4,}\s*[0-9]+(-[0-9]+)*\s*$', t):
        return True
    return bool(re.match(r'^第[一二三四五六七八九十]+章.*\s[0-9]+(-[0-9]+)+\s*$', t))

def convert(text, name, date, source):
    pages = text.split('\f')
    # 跳過目錄頁：含多行 toc-line 的前置頁
    body_pages = []
    started = False
    for pg in pages:
        lines = pg.split('\n')
        toc = sum(1 for l in lines if is_toc_line(l))
        if not started and toc >= 3:
            continue  # 目錄頁
        started = True
        body_pages.append(pg)

    raw = '\n'.join(body_pages)
    lines = raw.split('\n')

    md = [f'# {name}\n']
    md.append(f'> 來源：{source}｜版本日期：{date}')
    md.append('>')
    md.append('> ⚠️ **法規快照**：本檔為入庫當下之版本，引用前請依 index.md「法規時效」核對官方現行版本。')
    md.append('>')
    md.append('> 🛈 本檔由 PDF（`pdftotext -layout`）自動轉換，已去頁首頁尾。**附圖、表單及複雜試驗表無文字層，請以文末原始 PDF 連結核對**。\n')

    # 表單專屬詞彙（prose 條文不會出現此類組合；不含「不良狀況/處置措施/判定」等
    # prose 常用詞，避免誤刪法條內容）：用於辨識檢修報告表/檢查表殘骸
    FORM_TOKENS = ('簽章', '證書字號', '委託服務廠商', '校正年月日', '機器名稱',
                   '下次性能檢查日期', '消防設備師(士)', '消防設備師（士）')

    def is_form(par):
        if '□' in par:
            return True
        hits = sum(1 for t in FORM_TOKENS if t in par)
        if hits >= 2:
            return True
        if par.count('MΩ') >= 2 or par.count('○') >= 3:
            return True
        return False

    # 部分認可基準 PDF 以寬字距排版，CJK 字元間夾單一空白；合併之以利閱讀
    _cjk = r'[　-〿㐀-䶿一-鿿＀-￯，、。：；（）「」]'
    def collapse_cjk(s):
        prev = None
        while prev != s:
            prev = s
            s = re.sub(f'({_cjk}) +({_cjk})', r'\1\2', s)
        return s

    buf = []
    def flush():
        if buf:
            md.append(collapse_cjk(''.join(s.strip() for s in buf)))
            buf.clear()

    for ln in lines:
        if is_noise(ln) or is_toc_line(ln):
            continue
        s = ln.strip()
        if not s:
            flush()
            continue
        mc = RE_CHAP.match(s)
        if mc and len(s) < 30:  # 章標題通常短
            flush()
            zhi = mc.group(2) or ''
            md.append(f'\n## 第{mc.group(1)}章{zhi}　{mc.group(3)}\n')
            continue
        md_sec = RE_DASEC.match(s)
        if md_sec and len(s) < 30:  # 壹貳參…大段標題
            flush()
            md.append(f'\n## {md_sec.group(1)}、{md_sec.group(2)}\n')
            continue
        if RE_MARK.match(s):
            flush()
            buf.append(ln)
        else:
            # 續行：接回上一段
            buf.append(ln)
    flush()

    # 後處理：將連續的表單殘骸段落收合為單一 PDF 連結提示
    NOTE = '> 📋 此處為檢修報告表／檢查表（表單），PDF 文字層無法乾淨呈現，請見文末原始 PDF 連結。'
    cleaned, run = [], 0
    for par in md:
        if par.startswith('#') or par.startswith('>'):
            cleaned.append(par); run = 0; continue
        if is_form(par):
            if run == 0:
                cleaned.append(NOTE)
            run += 1
        else:
            cleaned.append(par); run = 0
    md = cleaned

    # 去除連續重複之標題（目錄殘留與本文標題重複時）
    dedup = []
    for par in md:
        if par.startswith('## ') and dedup and dedup[-1].strip() == par.strip():
            continue
        dedup.append(par)
    md = dedup

    out = '\n\n'.join(md)
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out.strip() + '\n'

def main():
    if len(sys.argv) < 5:
        print('用法: python3 pdf2md_statute.py <來源.pdf 的 txt> <輸出.md> "<全名>" "<版本日期>" [來源說明]', file=sys.stderr)
        sys.exit(1)
    src, dst, name, date = sys.argv[1:5]
    source = sys.argv[5] if len(sys.argv) > 5 else '使用者上傳 PDF 轉換'
    text = open(src, encoding='utf-8', errors='replace').read()
    md = convert(text, name, date, source)
    open(dst, 'w', encoding='utf-8').write(md)
    chaps = len(re.findall(r'^## 第', md, re.M))
    print(f'OK：{src} -> {dst}（{chaps} 章、{len(md)} 字元）')

if __name__ == '__main__':
    main()
