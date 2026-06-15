#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法規 RTF → 結構化 Markdown 轉換器。

用途：將全國法規資料庫匯出的 RTF（Big5/cp950，內文以 \\uN unicode 跳脫）
轉成人類可讀、章條分明的 Markdown，供 statutes/ 入庫。

用法：
    python3 scripts/rtf2md_statute.py <來源.rtf> <輸出.md>

辨識規則（依全國法規資料庫排版）：
- 「法規名稱：X」「修正日期：…」→ 檔頭 metadata
- 「第 X 章 名稱」「第 X 章之一 名稱」→ ## 章標題
- 「第 N 條」「第 N-M 條」→ ### 條標題
- 行首「1   」「2   」…（數字＋多個空白）→ 項次，轉為有序清單
- 其餘段落原樣保留
"""
import sys, re

# ---------- 第一階段：RTF → 純文字 ----------
def rtf_to_text(data: str) -> str:
    out, bytebuf = [], bytearray()
    def flush():
        if bytebuf:
            out.append(bytebuf.decode('big5', errors='replace'))
            bytebuf.clear()
    skip_words = {'fonttbl','colortbl','stylesheet','info','pict','themedata',
                  'colorschememapping','latentstyles','datastore','rsidtbl',
                  'generator','listtable','listoverridetable','revtbl'}
    i, n, depth, skip_stack, ucskip = 0, len(data), 0, [], 1
    while i < n:
        c = data[i]
        if c == '\\':
            nxt = data[i+1] if i+1 < n else ''
            if nxt == "'":
                try: bytebuf.append(int(data[i+2:i+4], 16))
                except ValueError: pass
                i += 4; continue
            elif nxt in '\\{}':
                flush()
                if not skip_stack: out.append(nxt)
                i += 2; continue
            elif nxt == '*':
                skip_stack.append(depth); i += 2; continue
            elif nxt == 'u' and i+2 < n and (data[i+2].isdigit() or data[i+2]=='-'):
                m = re.match(r'u(-?\d+) ?', data[i+1:])
                if m:
                    flush()
                    code = int(m.group(1))
                    if code < 0: code += 65536
                    if not skip_stack: out.append(chr(code))
                    i += 1 + m.end()
                    skipped = 0
                    while skipped < ucskip and i < n:
                        if data[i] == '\\' and i+1 < n and data[i+1] == "'":
                            i += 4
                        elif data[i] == '\\':
                            mm = re.match(r'\\[a-zA-Z]+-?\d* ?', data[i:])
                            i += mm.end() if mm else 2
                        else:
                            i += 1
                        skipped += 1
                    continue
            m = re.match(r'\\([a-zA-Z]+)(-?\d+)? ?', data[i:])
            if m:
                word, arg = m.group(1), m.group(2)
                if word == 'uc': ucskip = int(arg) if arg else 1
                elif word in ('par','pard','line','sect'): flush(); out.append('\n')
                elif word == 'tab': flush(); out.append('\t')
                elif word in skip_words: skip_stack.append(depth)
                i += m.end(); continue
            i += 1; continue
        elif c == '{':
            flush(); depth += 1; i += 1; continue
        elif c == '}':
            flush()
            if skip_stack and skip_stack[-1] == depth: skip_stack.pop()
            depth -= 1; i += 1; continue
        elif c in '\r\n':
            i += 1; continue
        else:
            if not skip_stack:
                bytebuf.append(ord(c) if ord(c) < 256 else ord('?'))
            i += 1; continue
    flush()
    text = ''.join(out)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# ---------- 第二階段：純文字 → 結構化 Markdown ----------
RE_CHAP = re.compile(r'^第\s*[一二三四五六七八九十百]+\s*章(之[一二三四五六七八九十]+)?\s')
RE_ART  = re.compile(r'^第\s*\d+(-\d+)?\s*條$')
RE_CLAUSE = re.compile(r'^(\d+)\s{2,}(.*)$')          # 項：數字＋多空白
RE_NAME = re.compile(r'^法規名稱[：:]\s*(.+)$')
RE_DATE = re.compile(r'^(修正|發布|訂定|公發布|公布)日期[：:]\s*(.+)$')

def text_to_md(text: str) -> str:
    """產出符合 statutes/index.md 格式規範的 md：
    # 法規名 / > 來源｜版本日期 / 章為粗體列 / ## 第 X 條 / 項款目階層。"""
    lines = text.split('\n')
    name = date = date_label = None
    body = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        # 丟棄字型表殘留（含 ? 佔位符且非法規內容）
        if '?' in s and ('明體' in s or s.count('?') > 3):
            continue
        m = RE_NAME.match(s)
        if m and name is None:
            name = m.group(1).strip(); continue
        m = RE_DATE.match(s)
        if m and date is None:
            date_label = m.group(1).strip()
            date = m.group(2).strip(); continue
        body.append(s)

    md = []
    title = name or '（未命名法規）'
    md.append(f'# {title}\n')
    ver = f'版本日期：{date}（{date_label}）' if date else '版本日期：（原檔未標注，請核對官方來源）'
    md.append(f'> 來源：全國法規資料庫（使用者上傳 RTF 轉換）｜{ver}')
    md.append('>')
    md.append('> ⚠️ **法規快照**：本檔為入庫當下之版本，引用前請依 index.md「法規時效」核對官方現行版本。\n')

    for s in body:
        if RE_CHAP.match(s):
            # 章：正規化空白後以粗體列呈現（條一律為 ## 主標題，章不佔標題層級）
            chap = re.sub(r'^第\s*([一二三四五六七八九十百]+)\s*章(之[一二三四五六七八九十]+)?\s*',
                          lambda mm: f'第{mm.group(1)}章{mm.group(2) or ""}　', s)
            md.append(f'\n**{chap}**\n')
        elif RE_ART.match(s):
            art = re.sub(r'\s+', ' ', s)
            md.append(f'\n## {art}\n')
        else:
            mc = RE_CLAUSE.match(s)
            if mc:
                # 項：第 N 項　全文
                md.append(f'第 {int(mc.group(1))} 項　{mc.group(2).strip()}')
            else:
                # 款（一、）、目（（一））、或單項條文全文，原樣保留
                md.append(s)
    # 段落間以空行分隔，符合規範可讀性
    out = '\n\n'.join(md)
    out = re.sub(r'\n{3,}', '\n\n', out)
    # 標題與其後段落間維持單一空行
    out = re.sub(r'(^|\n)(#+ .+|\*\*第.+章.*\*\*)\n\n', r'\1\2\n\n', out)
    return out.strip() + '\n'

def main():
    if len(sys.argv) != 3:
        print('用法: python3 rtf2md_statute.py <來源.rtf> <輸出.md>', file=sys.stderr)
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, 'rb') as f:
        raw = f.read().decode('latin-1')
    text = rtf_to_text(raw)
    md = text_to_md(text)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(md)
    arts = len(re.findall(r'^## 第', md, re.M))
    chaps = len(re.findall(r'^\*\*第.+章', md, re.M))
    print(f'OK：{src} -> {dst}（{chaps} 章、{arts} 條）')

if __name__ == '__main__':
    main()
