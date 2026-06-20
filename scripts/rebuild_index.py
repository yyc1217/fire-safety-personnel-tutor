#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rebuild_index.py — 從各題 inline `🏷️` 標籤**反向建立** corpus/tags_index.json。

與 build_tags.py 的差異：build_tags.py 以關鍵字「自動判讀題目」產生標籤；本腳本
**不重新判讀題目**，只解析既有 inline 標籤（人工／語意校正後的結果即為唯一真相
來源），彙整成中央索引。語意校正分類請直接編輯各 md 的 `🏷️` 行，再執行本腳本。

用法：python3 scripts/rebuild_index.py
"""
import json, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MD_ROOT = ROOT / "corpus" / "md"
INDEX = ROOT / "corpus" / "tags_index.json"
TAG = "🏷️"

SYS_VOCAB = {"滅火設備", "警報設備", "避難逃生設備", "消防搶救上之必要設備", "綜合/通則"}
FLAG_VOCAB = {"找錯誤", "找正確", "計算題", "更正答案", "圖形題", "跨科"}
TYPE_VOCAB = {"申論題", "測驗題"}
ART_RE = re.compile(r"第\s*\d+\s*條")  # 條號標籤（法名＋第X條[之Y]）

# 設備、法規、知識領域詞彙取自 build_tags.py，確保與既有體系一致
import importlib.util
_spec = importlib.util.spec_from_file_location("build_tags", ROOT / "scripts" / "build_tags.py")
_bt = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_bt)
EQUIP_VOCAB = {name for _, name, _ in _bt.EQUIP}
TOPIC_VOCAB = {name for _, name in _bt.TOPICS} | {
    # 火災學知識領域（市面教材目錄；語意重標用）
    "燃燒理論","火災化學/化學計量","火災化學與化學計量","預混與擴散燃燒","火羽流與頂棚噴流",
    "閃燃","爆燃","區劃空間火災發展","煙控/煙流","煙控與煙流","熱傳","爆炸","燃燒界限與爆炸界限",
    "滅火原理/藥劑","滅火原理與滅火藥劑","電氣火災","靜電","危險物品分類","危險物品分類與特性",
    "建築物火災性狀","特殊場所火災","火災調查/危害物質","火災調查與鑑識","人員避難行為",
}
# 法規維度：命題大綱 51 部標準名稱 ＋ 過渡期舊粗名（重標未完成前並存）
LAW_VOCAB = {
 "消防法","消防法施行細則","消防設備人員法","消防設備人員法施行細則","消防設備人員執業執照登記辦法",
 "消防安全設備設計監造測試及檢修作業辦法","消防設備人員專業訓練機關構學校團體認可及管理辦法",
 "消防安全設備檢修專業機構管理辦法","防焰性能認證實施辦法",
 "公共危險物品及可燃性高壓氣體製造儲存處理場所設置標準暨安全管理辦法","公共危險物品試驗方法及判定基準",
 "防火牆及防火水幕設置基準","可燃性高壓氣體儲存場所防爆牆設置基準","可燃性高壓氣體儲存場所防護牆設置基準",
 "消防安全設備檢修及申報辦法","消防機具器材及設備認可實施辦法","防火管理人訓練與專業機構登錄及管理辦法",
 "服勤人員訓練與專業機構登錄及管理辦法","消防機關辦理公共危險物品及可燃性高壓氣體場所位置構造設備審查及查驗作業基準",
 "六類公共危險物品製造儲存及處理場所標示板規格及設置要點","可燃性高壓氣體場所標示板規格及設置要點",
 "各類場所消防安全設備設置標準","消防機關辦理建築物消防安全設備審查及查驗作業基準",
 "消防安全設備及必要檢修項目檢修基準","複合用途建築物判斷基準","二氧化碳滅火設備各種標示規格",
 "乾粉滅火設備各種標示規格","消防幫浦加壓送水裝置等及配管摩擦損失計算基準","緊急電源容量計算基準",
 "避難器具支固器具及固定部之結構強度計算及施工方法","消防安全設備測試報告書測試方法及判定要領",
 "滅火器性能檢查及藥劑更換充填作業專業廠商認可及管理要點","潔淨區消防安全設備設置要點",
 "住宅用火災警報器設置辦法","119火災通報裝置設置及維護注意事項","水道連結型自動撒水設備設置基準",
 "建築法","建築技術規則建築設計施工編","原有合法建築物公共安全改善辦法",
 "滅火器認可基準","滅火器用滅火藥劑認可基準","住宅用火災警報器認可基準","火警探測器認可基準",
 "火警受信總機認可基準","緊急廣播設備用揚聲器認可基準","一齊開放閥認可基準","撒水頭認可基準",
 "出口標示燈及避難方向指示燈認可基準","緩降機認可基準","金屬製避難梯認可基準","119火災通報裝置認可基準",
 # 過渡期舊粗名（尚未重標之題仍在用；待全部重標後可移除）
 "公共危險物品及可燃性高壓氣體設置標準暨安全管理辦法","檢修及申報作業基準","建築技術規則",
 "消防設備師及消防設備士管理辦法","防焰相關規定","（各設備）認可基準","測試報告書測試方法及判定要領",
 "可燃性高壓氣體儲存場所防爆牆/防護牆設置基準","NFPA（國外標準）",
}


def dim_of(tok):
    if tok in TYPE_VOCAB: return "by_type"
    if tok in SYS_VOCAB: return "by_system"
    if tok in EQUIP_VOCAB: return "by_equipment"
    if tok in FLAG_VOCAB: return "by_flag"
    if ART_RE.search(tok): return "by_article"
    if tok in LAW_VOCAB: return "by_law"
    if tok in TOPIC_VOCAB: return "by_topic"
    return None  # 未知 token（可能為新法規短名／自訂），歸入 by_law 以免遺失


def main():
    idx = {k: {} for k in ("by_type", "by_system", "by_equipment", "by_law",
                           "by_article", "by_topic", "by_flag")}
    total = 0
    unknown = set()
    for md in sorted(MD_ROOT.rglob("*.md")):
        rel = md.relative_to(MD_ROOT)
        level, year = rel.parts[0], rel.parts[1]
        subject = md.stem.split("_")[0]
        paper = f"{level}/{year}/{subject}"
        lines = md.read_text(encoding="utf-8").split("\n")
        # 取得每個 🏷️ 行對應之題號：往上找最近的 ### 第N題 / 申論第N題
        qno = None
        for ln in lines:
            mo = re.match(r"^### 第\s*(\d+)\s*題", ln)
            me = re.match(r"^### 申論第([一二三四五六七八九十\d]+)題", ln)
            if mo: qno = f"#Q{mo.group(1)}"
            elif me:
                cn = {"一":1,"二":2,"三":3,"四":4,"五":5}
                qno = f"#甲{cn.get(me.group(1), me.group(1))}"
            s = ln.lstrip()
            if s.startswith(f"> {TAG}") or s.startswith(TAG):
                if qno is None: continue
                ref = paper + qno
                total += 1
                body = s.split(TAG, 1)[1].strip()
                for seg in body.split("｜"):
                    for tok in (t.strip() for t in seg.split("、")):
                        if not tok: continue
                        d = dim_of(tok)
                        if d is None:
                            unknown.add(tok); d = "by_law"
                        idx[d].setdefault(tok, []).append(ref)
    idx["_meta"] = {"total_questions": total, "generator": "scripts/rebuild_index.py",
                    "note": "由各題 inline 🏷️ 標籤解析而得；分類以 inline 標籤（語意校正後）為唯一真相來源"}
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"parsed {total} questions -> {INDEX.relative_to(ROOT)}")
    for k in ("by_type","by_system","by_equipment","by_law","by_article","by_topic","by_flag"):
        items = sorted(idx[k].items(), key=lambda x:-len(x[1]))
        head = [(t,len(v)) for t,v in items[:8]]
        print(f"  {k}: {len(idx[k])} 種；前8={head}")
    if unknown:
        print(f"  ⚠️ 未能歸類之 token（暫歸 by_law）：{sorted(unknown)}")


if __name__ == "__main__":
    main()
