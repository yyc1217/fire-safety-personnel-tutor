#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消防署「消防法令查詢系統」HTML 法規 → 結構化 Markdown。

用於資料夾型法規（基準／要點），其本文以 <pre> 區塊存放、各「點」一塊，
內含 ASCII 框線表格。轉換規則：
- 法規名稱取自 <h1>；修正日期 94/08/26 → 民國 94 年 08 月 26 日
- 每個 <pre> 視為一「點」，首碼（一二三…）轉為 ## 第 N 點 標題
- ASCII 框線表格：欄數一致的「簡單表」轉 markdown 表格；
  含合併儲存格的「複雜表」保留原框線於 ``` 區塊（無損、可讀）
- 其餘款目（（一）、1.、(1)）原樣保留

用法： python3 scripts/html2md_statute.py <來源.html> <輸出.md>
"""
import sys, re, html

BOX = set('─━│┌┐└┘├┤┬┴┼ ')

def roc_date(s):
    m = re.match(r'\s*(\d{2,3})/(\d{1,2})/(\d{1,2})', s)
    if m:
        return f'民國 {int(m.group(1))} 年 {int(m.group(2)):02d} 月 {int(m.group(3)):02d} 日'
    return s.strip()

def is_sep(line):
    t = line.strip()
    return bool(t) and set(t) <= BOX and ('─' in t or '━' in t)

def dedent(block):
    lines = block.split('\n')
    indents = [len(l) - len(l.lstrip(' ')) for l in lines if l.strip()]
    cut = min(indents) if indents else 0
    return [l[cut:] if len(l) >= cut else l for l in lines]

def try_markdown_table(tlines):
    """嘗試把框線表轉 markdown；欄數不一致（合併儲存格）回傳 None。"""
    groups, cur = [], []
    for ln in tlines:
        if is_sep(ln):
            if cur: groups.append(cur); cur = []
        elif '│' in ln:
            cur.append(ln)
    if cur: groups.append(cur)
    if len(groups) < 2:
        return None
    rows = []
    for grp in groups:
        cells = None
        for ln in grp:
            parts = ln.split('│')
            if parts and parts[0].strip() == '':
                parts = parts[1:]
            if parts and parts[-1].strip() == '':
                parts = parts[:-1]
            parts = [p.strip() for p in parts]
            if cells is None:
                cells = parts
            else:
                if len(parts) != len(cells):
                    return None
                cells = [(c + p).strip() for c, p in zip(cells, parts)]
        rows.append(cells)
    ncols = len(rows[0])
    if any(len(r) != ncols for r in rows):
        return None
    out = []
    out.append('| ' + ' | '.join(c or ' ' for c in rows[0]) + ' |')
    out.append('| ' + ' | '.join(['---'] * ncols) + ' |')
    for r in rows[1:]:
        out.append('| ' + ' | '.join(c or ' ' for c in r) + ' |')
    return '\n'.join(out)

# 款／目／細項的起始標記（用於還原硬換行：非標記行視為續行接回上一段）
RE_ITEM = re.compile(r'^\s*(（[一二三四五六七八九十百]+）|'
                     r'[一二三四五六七八九十百]+、|'
                     r'\(\s*[一二三四五六七八九十百]+\s*\)|'
                     r'\(\s*\d+\s*\)|'
                     r'\d+[.、])')

def is_box_line(ln):
    t = ln.strip()
    if not t:
        return False
    return t[0] in '┌┍┎┏├┝┞┟┠└┕┖┗─━' or '│' in t or set(t) <= BOX

def render_body(text):
    lines = dedent(text)
    out, buf = [], []

    def flush():
        if buf:
            # CJK 硬換行續行直接相接（去掉行首空白）
            para = ''.join(s.strip() for s in buf)
            out.append(para)
            buf.clear()

    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        if is_box_line(ln):
            flush()
            j = i
            while j < n and (lines[j].strip() == '' or is_box_line(lines[j])):
                if lines[j].strip() == '' and j + 1 < n and not is_box_line(lines[j + 1]):
                    break
                j += 1
            tlines = [l for l in lines[i:j] if l.strip()]
            md = try_markdown_table(tlines)
            out.append('')
            if md:
                out.append(md)
            else:
                out.append('```')
                out.extend(l.rstrip() for l in tlines)
                out.append('```')
            out.append('')
            i = j
            continue
        if not ln.strip():
            i += 1
            continue
        if RE_ITEM.match(ln):
            flush()
            buf.append(ln)
        else:
            buf.append(ln)
        i += 1
    flush()
    # 合併因表格插入造成的多重空行
    res = '\n'.join(out)
    res = re.sub(r'\n{3,}', '\n\n', res)
    return res.strip()

def convert(raw):
    name = '（未命名法規）'
    m = re.search(r'<h1[^>]*>\s*(.*?)\s*</h1>', raw, re.S)
    if m:
        name = re.sub(r'<[^>]+>', '', m.group(1)).strip()
    date = None
    m = re.search(r'修正日期[：:]\s*([\d/]+)', raw)
    if not m:
        m = re.search(r'(?:訂定|發布)日期[：:]\s*([\d/]+)', raw)
    if m:
        date = roc_date(m.group(1))

    pres = re.findall(r'<pre>(.*?)</pre>', raw, re.S)
    md = [f'# {name}\n']
    ver = f'版本日期：{date}（修正）' if date else '版本日期：（原檔未標注，請核對官方來源）'
    md.append(f'> 來源：內政部消防署消防法令查詢系統（使用者上傳 HTML 轉換）｜{ver}')
    md.append('>')
    md.append('> ⚠️ **法規快照**：本檔為入庫當下之版本，引用前請依 index.md「法規時效」核對官方現行版本。\n')

    for p in pres:
        t = html.unescape(p)
        body = render_body(t)
        # 取出首碼「一/二/…」或「第N點」作為標題
        m = re.match(r'^\s*([一二三四五六七八九十百]+)[、\s]\s*(.*)', body, re.S)
        if m:
            num = m.group(1)
            rest = m.group(2).strip()
            md.append(f'\n## 第 {num} 點\n')
            if rest:
                md.append(rest)
        else:
            md.append('\n' + body)
    out = '\n'.join(md)
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out.strip() + '\n'

def main():
    if len(sys.argv) != 3:
        print('用法: python3 html2md_statute.py <來源.html> <輸出.md>', file=sys.stderr)
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    raw = open(src, encoding='utf-8', errors='replace').read()
    md = convert(raw)
    open(dst, 'w', encoding='utf-8').write(md)
    pts = len(re.findall(r'^## 第', md, re.M))
    tbl = md.count('| --- |') if '| ---' in md else len(re.findall(r'\n\| .+ \|\n\| ---', md))
    fence = md.count('```') // 2
    print(f'OK：{src} -> {dst}（{pts} 點、markdown表 {tbl}、保留框線表 {fence}）')

if __name__ == '__main__':
    main()
