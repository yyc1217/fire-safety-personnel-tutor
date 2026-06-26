#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_tags.py — 解析 corpus/md 內所有考古題 md，為每題自動標籤，
並（1）將內嵌標籤寫回各 md（2）產生中央索引 corpus/tags_index.json。

標籤維度見 docs/設計_題目標籤系統.md。可機判維度（題型、找錯誤/找正確、
計算題、圖形題、更正答案）由規則判定；系統／設備／法規／知識領域以關鍵詞
字典初判（auto），仍建議人工校正。重複執行為冪等（先移除舊內嵌標籤再寫入）。

用法：python3 scripts/build_tags.py
"""
import json, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MD_ROOT = ROOT / "corpus" / "md"
INDEX = ROOT / "corpus" / "tags_index.json"

TAG = "🏷️"

# ── 設備 → 系統 對照（長詞優先比對）────────────────────────────
EQUIP = [
    # (關鍵詞 list, 設備標準名, 系統)
    (["室內消防栓"], "室內消防栓", "滅火設備"),
    (["室外消防栓"], "室外消防栓", "滅火設備"),
    (["水道連結型自動撒水", "水道連結型"], "水道連結型自動撒水設備", "滅火設備"),
    (["自動撒水", "撒水頭", "撒水設備", "一齊開放閥", "流水檢知"], "自動撒水設備", "滅火設備"),
    (["水霧"], "水霧滅火設備", "滅火設備"),
    (["泡沫"], "泡沫滅火設備", "滅火設備"),
    (["二氧化碳", "CO2", "CO₂"], "二氧化碳滅火設備", "滅火設備"),
    (["惰性氣體", "IG-541", "IG541", "IG-55", "IG-01", "IG-100", "INERGEN"], "二氧化碳及惰性氣體滅火設備", "滅火設備"),
    (["乾粉"], "乾粉滅火設備", "滅火設備"),
    (["鹵化烴", "鹵化烷", "海龍", "HFC-227", "HFC-23", "FM-200", "FE-13", "NOVEC", "潔淨藥劑", "潔淨式"], "鹵化烴滅火設備", "滅火設備"),
    (["冷卻撒水"], "冷卻撒水設備", "滅火設備"),
    (["射水設備", "射水槍", "泡沫射水"], "射水設備", "滅火設備"),
    (["簡易自動滅火", "簡易滅火"], "簡易自動滅火設備", "滅火設備"),
    (["滅火器"], "滅火器", "滅火設備"),
    (["消防幫浦", "加壓送水", "呼水", "全揚程", "性能曲線"], "消防幫浦/加壓送水裝置", "滅火設備"),
    # 警報設備
    (["瓦斯漏氣", "瓦斯燃燒器具", "檢知器", "加瓦斯"], "瓦斯漏氣火警自動警報設備", "警報設備"),
    (["緊急廣播", "揚聲器", "擴音機"], "緊急廣播設備", "警報設備"),
    (["手動報警", "火警發信機", "火警警鈴"], "手動報警設備", "警報設備"),
    (["一一九", "119火災通報", "火災通報裝置"], "119火災通報設備", "警報設備"),
    (["住宅用火災警報器"], "住宅用火災警報器", "警報設備"),
    (["火警自動警報", "受信總機", "探測器", "火警分區", "中繼器"], "火警自動警報設備", "警報設備"),
    # 避難逃生設備
    (["出口標示燈", "避難方向指示燈", "避難指標", "標示設備", "引導燈"], "標示設備", "避難逃生設備"),
    (["緩降機", "救助袋", "避難梯", "滑臺", "滑台", "滑杆", "避難橋", "避難繩索", "避難器具", "支固器具"], "避難器具", "避難逃生設備"),
    (["緊急照明"], "緊急照明設備", "避難逃生設備"),
    # 消防搶救上之必要設備
    (["連結送水管", "送水口", "中繼幫浦"], "連結送水管", "消防搶救上之必要設備"),
    (["消防專用蓄水池", "蓄水池", "採水口", "投入孔"], "消防專用蓄水池", "消防搶救上之必要設備"),
    (["排煙", "防煙壁", "防煙區劃", "排煙機"], "排煙設備", "消防搶救上之必要設備"),
    (["緊急電源插座"], "緊急電源插座", "消防搶救上之必要設備"),
    (["無線電通信輔助", "洩波同軸"], "無線電通信輔助設備", "消防搶救上之必要設備"),
    (["防災中心", "防災監控", "綜合操作裝置"], "防災監控系統綜合操作裝置", "消防搶救上之必要設備"),
]

LAWS = [
    (["各類場所消防安全設備檢修及申報作業基準", "檢修及申報作業基準", "檢修及申報", "檢修基準"], "檢修及申報作業基準"),
    (["消防安全設備測試報告書", "測試方法及判定要領", "測試報告書"], "測試報告書測試方法及判定要領"),
    (["各類場所消防安全設備設置標準", "設置標準"], "各類場所消防安全設備設置標準"),
    (["消防法施行細則"], "消防法施行細則"),
    (["公共危險物品", "可燃性高壓氣體設置標準", "安全管理辦法"], "公共危險物品及可燃性高壓氣體設置標準暨安全管理辦法"),
    (["建築技術規則"], "建築技術規則"),
    (["消防設備師及消防設備士管理辦法", "消防設備師", "消防設備士管理"], "消防設備師及消防設備士管理辦法"),
    (["消防安全設備檢修專業機構管理辦法", "檢修專業機構", "檢修機構"], "消防安全設備檢修專業機構管理辦法"),
    (["消防幫浦加壓送水裝置等及配管摩擦損失計算基準", "配管摩擦損失計算基準"], "消防幫浦加壓送水裝置等及配管摩擦損失計算基準"),
    (["防火牆及防火水幕設置基準", "防火水幕設置基準", "防火水幕"], "防火牆及防火水幕設置基準"),
    (["防爆牆設置基準", "防護牆設置基準", "防爆牆", "防護牆"], "可燃性高壓氣體儲存場所防爆牆/防護牆設置基準"),
    (["認可基準"], "（各設備）認可基準"),
    (["防焰性能", "防焰物品", "防焰標示", "防焰"], "防焰相關規定"),
    (["NFPA"], "NFPA（國外標準）"),
    (["消防法"], "消防法"),
]

# 火災學知識領域
TOPICS = [
    (["爆炸", "爆轟", "爆燃", "BLEVE", "粉塵爆炸", "塵爆", "分解爆炸"], "爆炸"),
    (["煙囪效應", "中性帶", "能見度", "光學密度", "消光係數", "減光", "煙層", "煙流"], "煙控/煙流"),
    (["輻射", "對流", "傳導", "熱通量", "史蒂芬", "波茲曼", "熱傳"], "熱傳"),
    (["靜電", "帶電", "放電"], "靜電"),
    (["電線", "短路", "焦耳", "積污導電", "漏電", "電氣火災", "電阻"], "電氣火災"),
    (["閃燃", "flashover", "複燃", "backdraft", "閃火點", "著火", "燃燒下限", "燃燒界限", "燃燒上限", "發火", "自然發火", "燃燒形式", "燃燒型態"], "燃燒理論"),
    (["理論空氣量", "莫耳", "燃燒熱", "化學理論濃度", "化學反應式", "理論濃度", "當量濃度"], "火災化學/化學計量"),
    (["滅火劑", "滅火藥劑", "海龍替代", "窒息", "抑制連鎖", "滅火原理", "滅火方法"], "滅火原理/藥劑"),
    (["危險物品", "公共危險物品", "禁水性", "氧化性", "自反應"], "危險物品分類"),
    (["火災調查", "火災統計", "火災紀錄", "火災原因", "HAZMAT", "危害物質"], "火災調查/危害物質"),
    (["森林火災", "古蹟", "無塵室", "高科技廠房", "隧道", "地下建築物火災"], "特殊場所火災"),
]


# ── 法條（條號）擷取 ───────────────────────────────────────────
# 法規短名（供條號前綴）；較具體/較長者在前，避免「消防法」誤搶「消防法施行細則」。
LAW_SHORT = [
    (["消防法施行細則"], "施行細則"),
    (["各類場所消防安全設備設置標準", "設置標準"], "設置標準"),
    (["公共危險物品", "可燃性高壓氣體", "安全管理辦法"], "公危辦法"),
    (["建築技術規則"], "建築技術規則"),
    (["建築法"], "建築法"),
    (["各類場所消防安全設備檢修及申報作業基準", "檢修及申報", "檢修基準"], "檢修基準"),
    (["消防安全設備測試報告書", "測試方法及判定要領", "測試報告書"], "測試報告書"),
    (["消防設備師及消防設備士管理辦法", "消防設備士管理", "消防設備師"], "設備人員管理辦法"),
    (["消防安全設備檢修專業機構管理辦法", "檢修專業機構"], "檢修機構管理辦法"),
    (["消防幫浦加壓送水裝置等及配管摩擦損失計算基準", "配管摩擦損失計算基準"], "幫浦計算基準"),
    (["認可基準"], "認可基準"),
    (["消防法"], "消防法"),
]

_CN = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
       "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn2int(s):
    """中文或阿拉伯數字（0–999，含十、百）轉整數；無法解析回 None。"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    if not s:
        return None
    section, num = 0, 0
    for ch in s:
        if ch in _CN:
            num = _CN[ch]
        elif ch == "十":
            section += (num or 1) * 10; num = 0
        elif ch == "百":
            section += (num or 1) * 100; num = 0
        else:
            return None
    val = section + num
    return val or None


ART_RE = re.compile(r"第\s*([〇零一二三四五六七八九十百\d]+)\s*條(?:之\s*([〇零一二三四五六七八九十百\d]+))?")


def _law_short_before(text, pos):
    """回傳 pos 之前文字中最近出現之法規短名；若該題完全未提及任何法規，回 None。"""
    best, best_pos = None, -1
    for kws, short in LAW_SHORT:
        for k in kws:
            p = text.rfind(k, 0, pos)
            if p > best_pos:
                best_pos, best = p, short
    return best


def extract_articles(text):
    """擷取題幹明確引用之條號，附上最近法規短名作前綴；僅在可歸屬法源時納入。"""
    arts = set()
    for m in ART_RE.finditer(text):
        n = _cn2int(m.group(1))
        if not n:
            continue
        sub = ""
        if m.group(2):
            s2 = _cn2int(m.group(2))
            if s2:
                sub = f"之{s2}"
        law = _law_short_before(text, m.start())
        if not law:
            continue  # 無法歸屬法源者不納入，避免雜訊
        arts.add(f"{law}第{n}條{sub}")
    return arts


def classify(text, sci_paper):
    systems, equips, laws, topics, flags = set(), set(), set(), set(), set()
    for kws, name, sysname in EQUIP:
        if any(k in text for k in kws):
            equips.add(name); systems.add(sysname)
    for kws, name in LAWS:
        if any(k in text for k in kws):
            laws.add(name)
    if sci_paper:
        for kws, name in TOPICS:
            if any(k in text for k in kws):
                topics.add(name)
    # flags
    if re.search(r"何者(錯誤|有誤|不正確|不符|為誤|錯)|何者非|不包括|不屬|非屬|不正確|何者不", text):
        flags.add("找錯誤")
    elif re.search(r"何者正確|何者為(正確|對)|下列正確|何者最(適當|正確)", text):
        flags.add("找正確")
    if re.search(r"計算|試求|試算|約為多少|每分鐘.*公升|kgf|kW|公斤.*多少|多少公尺|多少立方|放水量|出水量|揚程|換算|平方|×|公式", text) and re.search(r"\d", text):
        if any(w in text for w in ["計算", "試求", "試算", "約為", "估算", "求得", "試問", "幾倍", "幾分鐘", "多少"]):
            flags.add("計算題")
    articles = extract_articles(text)
    return systems, equips, laws, topics, flags, articles


def process(md_path):
    rel = md_path.relative_to(MD_ROOT)
    level = rel.parts[0]
    year = rel.parts[1]
    subject = md_path.stem.split("_")[0]
    paper_ref = f"{level}/{year}/{subject}"
    lines = md_path.read_text(encoding="utf-8").split("\n")
    sci = "火災學" in md_path.stem
    figure_paper = any("圖形題" in ln for ln in lines[:15])

    out, recs = [], []
    i = 0
    # remove old inline tag lines first
    lines = [ln for ln in lines if not ln.lstrip().startswith(f"> {TAG}")]
    n = len(lines)
    while i < n:
        ln = lines[i]
        out.append(ln)
        m_obj = re.match(r"^### 第\s*(\d+)\s*題", ln)
        m_essay = re.match(r"^### 申論第([一二三四五六七八九十\d]+)題", ln)
        if m_obj:
            qno = m_obj.group(1)
            # gather until 標準答案
            j = i + 1
            buf = []
            while j < n and not lines[j].startswith("### ") and not lines[j].startswith("## "):
                buf.append(lines[j]); j += 1
            block = "\n".join(buf)
            syss, eqs, laws, tps, flags, arts = classify(ln + "\n" + block, sci)
            flags.add("__type_測驗")
            if "圖形題" in block or "圖形）" in block or (figure_paper and "對照" in block):
                flags.add("圖形題")
            if re.search(r"一律給分|均給分|更正答案", block):
                flags.add("更正答案")
            ref = f"{paper_ref}#Q{qno}"
            recs.append((ref, "測驗題", syss, eqs, laws, tps, flags, arts))
            # build inline tag, insert right after the 標準答案 line
            seg = lines[i + 1 : j]
            new_seg = []
            inserted = False
            for s in seg:
                new_seg.append(s)
                if (not inserted) and s.startswith("**標準答案"):
                    new_seg.append("")
                    new_seg.append("> " + tagline("測驗題", syss, eqs, laws, tps, flags, arts))
                    inserted = True
            out.extend(new_seg)
            i = j
            continue
        if m_essay:
            # essay: question text until next heading
            j = i + 1
            buf = []
            while j < n and not lines[j].startswith("### ") and not lines[j].startswith("## "):
                buf.append(lines[j]); j += 1
            block = "\n".join(buf)
            syss, eqs, laws, tps, flags, arts = classify(ln + "\n" + block, sci)
            flags.add("__type_申論")
            ref = f"{paper_ref}#甲{essay_no(m_essay.group(1))}"
            recs.append((ref, "申論題", syss, eqs, laws, tps, flags, arts))
            # insert tag after heading line
            out.append("> " + tagline("申論題", syss, eqs, laws, tps, flags, arts))
            out.extend(lines[i + 1 : j])
            i = j
            continue
        i += 1
    md_path.write_text("\n".join(out), encoding="utf-8")
    return recs


def essay_no(s):
    cn = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
    return cn.get(s, s)


def tagline(typ, syss, eqs, laws, tps, flags, arts=None):
    parts = [typ]
    if syss: parts.append("、".join(sorted(syss)))
    if eqs: parts.append("、".join(sorted(eqs)))
    if laws: parts.append("、".join(sorted(laws)))
    if arts: parts.append("、".join(sorted(arts, key=_art_sortkey)))
    if tps: parts.append("、".join(sorted(tps)))
    extra = [f for f in sorted(flags) if not f.startswith("__")]
    if extra: parts.append("、".join(extra))
    return f"{TAG} " + "｜".join(parts)


def _art_sortkey(a):
    """條號標籤排序：先依法規短名，再依條號數字。"""
    m = re.search(r"第(\d+)", a)
    return (a.split("第")[0], int(m.group(1)) if m else 0)


def main():
    idx = {"by_type": {}, "by_system": {}, "by_equipment": {}, "by_law": {},
           "by_article": {}, "by_topic": {}, "by_flag": {}}
    total = 0
    for md_path in sorted(MD_ROOT.rglob("*.md")):
        for ref, typ, syss, eqs, laws, tps, flags, arts in process(md_path):
            total += 1
            idx["by_type"].setdefault(typ, []).append(ref)
            for s in syss: idx["by_system"].setdefault(s, []).append(ref)
            for e in eqs: idx["by_equipment"].setdefault(e, []).append(ref)
            for l in laws: idx["by_law"].setdefault(l, []).append(ref)
            for a in arts: idx["by_article"].setdefault(a, []).append(ref)
            for t in tps: idx["by_topic"].setdefault(t, []).append(ref)
            for f in flags:
                if not f.startswith("__"):
                    idx["by_flag"].setdefault(f, []).append(ref)
    idx["_meta"] = {"total_questions": total, "generator": "scripts/build_tags.py",
                    "note": "可機判維度為規則判定；系統/設備/法規/知識領域為關鍵詞自動初判，建議人工校正"}
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"processed {total} questions -> {INDEX.relative_to(ROOT)}")
    for k in ("by_type", "by_system", "by_equipment", "by_law", "by_topic", "by_flag"):
        print(f"  {k}: {[(t, len(v)) for t, v in sorted(idx[k].items(), key=lambda x:-len(x[1]))]}")
    print(f"  by_article: {len(idx['by_article'])} 種條號；前20={[(t, len(v)) for t, v in sorted(idx['by_article'].items(), key=lambda x:-len(x[1]))][:20]}")


if __name__ == "__main__":
    main()
