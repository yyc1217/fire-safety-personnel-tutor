#!/usr/bin/env python3
"""repo 完整性與格式檢查（CI 用，亦可本機執行）。

只做**機械可驗**的檢查，不觸碰內容正確性（法條數值、標籤語意等仍靠人工）。

    python3 scripts/ci_check_repo.py            # 全部檢查
    python3 scripts/ci_check_repo.py --list     # 列出可用檢查
    python3 scripts/ci_check_repo.py -k links   # 只跑名稱含 links 的檢查

有任何 ERROR 時以 1 結束；WARN 不影響結束碼。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 內容資料夾：格式規範（上標、全形編號括號）適用範圍
CONTENT_DIRS = ["statutes", "corpus", "reference"]

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def md_files(dirs: list[str]) -> list[Path]:
    out: list[Path] = []
    for d in dirs:
        out.extend(sorted((ROOT / d).rglob("*.md")))
    return out


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


# --------------------------------------------------------------------------
# 1. plugin / marketplace 資訊清單
# --------------------------------------------------------------------------
def check_manifests() -> None:
    """plugin.json 與 marketplace.json 之 schema 與跨檔一致性。"""
    pj_path = ROOT / ".claude-plugin" / "plugin.json"
    mp_path = ROOT / ".claude-plugin" / "marketplace.json"

    try:
        pj = json.loads(read(pj_path))
    except Exception as e:  # noqa: BLE001
        err(f"plugin.json 無法解析：{e}")
        return
    try:
        mp = json.loads(read(mp_path))
    except Exception as e:  # noqa: BLE001
        err(f"marketplace.json 無法解析：{e}")
        return

    if "name" not in pj:
        err("plugin.json 缺必填欄位 name")

    version = pj.get("version")
    if version and not re.fullmatch(r"\d+\.\d+\.\d+", version):
        err(f"plugin.json version 非 semver：{version!r}")

    for field in ("description", "keywords"):
        if field not in pj:
            warn(f"plugin.json 建議補上 {field}")

    names = [p.get("name") for p in mp.get("plugins", [])]
    if pj.get("name") not in names:
        err(
            f"marketplace.json 未列出本 plugin：plugin.json name={pj.get('name')!r}，"
            f"marketplace 條目={names}"
        )

    # 版本唯一真相在 plugin.json；marketplace 條目不得另立版本造成漂移
    for entry in mp.get("plugins", []):
        if entry.get("name") == pj.get("name") and "version" in entry:
            err(
                "marketplace.json 條目重複宣告 version，會與 plugin.json 漂移；"
                "版本請只留在 plugin.json"
            )

    # README badge 需與 plugin.json 同版
    if version:
        readme = read(ROOT / "README.md")
        badge = re.search(r"badge/version-([0-9.]+)-", readme)
        if not badge:
            warn("README.md 找不到 version badge")
        elif badge.group(1) != version:
            err(
                f"版本不一致：plugin.json={version}，README badge={badge.group(1)}"
                "（改動 skills／reference／corpus／statutes 時記得同步 bump 兩處）"
            )


# --------------------------------------------------------------------------
# 2. skill frontmatter
# --------------------------------------------------------------------------
def parse_frontmatter(text: str) -> dict | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    body = text[4:end]
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    try:
        return yaml.safe_load(body) or {}
    except Exception:  # noqa: BLE001
        return None


def check_skills() -> None:
    """每個 skill 需有可解析的 frontmatter 與 description。"""
    skill_dirs = sorted(d for d in (ROOT / "skills").iterdir() if d.is_dir())
    if not skill_dirs:
        err("skills/ 下沒有任何 skill")
        return

    for d in skill_dirs:
        f = d / "SKILL.md"
        if not f.exists():
            err(f"{rel(d)} 缺 SKILL.md")
            continue
        fm = parse_frontmatter(read(f))
        if fm is None:
            err(f"{rel(f)} frontmatter 無法解析")
            continue
        if not fm:
            continue  # 無 PyYAML，跳過細項
        if not fm.get("description"):
            err(f"{rel(f)} 缺 description（Claude 據此判斷何時載入）")
        desc = str(fm.get("description", "")) + str(fm.get("when_to_use", ""))
        if len(desc) > 1536:
            err(f"{rel(f)} description 長度 {len(desc)} 超過官方 1,536 字上限，會被截斷")
        at = fm.get("allowed-tools")
        if at is not None and not isinstance(at, list):
            err(f"{rel(f)} allowed-tools 應為 YAML 清單（含空白的規則如 'Bash(jq *)' 不可用空白分隔字串）")

    # README 宣稱的 slash command 數量需與實際相符
    readme = read(ROOT / "README.md")
    cmd_count = sum(
        1
        for d in skill_dirs
        if (d / "SKILL.md").exists()
        and "disable-model-invocation: true" in read(d / "SKILL.md")
    )
    core_count = len(skill_dirs) - cmd_count
    zh = "零一二三四五六七八九十"
    expect_core = zh[core_count] if core_count < len(zh) else str(core_count)
    expect_cmd = zh[cmd_count] if cmd_count < len(zh) else str(cmd_count)
    claim = re.search(r"([零一二三四五六七八九十]+)個功能 skill＋([零一二三四五六七八九十]+)個 slash command skill", readme)
    if not claim:
        warn("README.md 找不到 skill 數量敘述，無法比對")
    elif (claim.group(1), claim.group(2)) != (expect_core, expect_cmd):
        err(
            f"README skill 數量與實際不符：README 稱 {claim.group(1)}＋{claim.group(2)}，"
            f"實際 {expect_core}（功能）＋{expect_cmd}（slash command）"
        )


def check_slash_commands() -> None:
    """指令名須為 ASCII，且文件引用的 /指令 都要對得上實際 skill。"""
    # Claude Code 會把 skill 名稱中的非 ASCII 字元逐字換成 '-'（`/抽考` → `/--`），
    # 中文指令名會互相蓋掉而叫不動；文件裡的舊指令名則會叫使用者打不存在的指令。
    names: set[str] = set()
    for d in sorted(p for p in (ROOT / "skills").iterdir() if p.is_dir()):
        f = d / "SKILL.md"
        if not f.exists():
            continue
        fm = parse_frontmatter(read(f))
        name = str((fm or {}).get("name") or d.name)
        names.add(name)
        if not name.isascii():
            err(f"{rel(f)} name: {name!r} 含非 ASCII 字元——Claude Code 會逐字換成 '-'，指令會互相蓋掉")
        if not d.name.isascii():
            err(f"{rel(d)} 資料夾名含非 ASCII 字元（應與 ASCII 的 name: 同名）")
        if fm and name != d.name:
            err(f"{rel(f)} name: {name!r} 與資料夾名 {d.name!r} 不一致")

    targets = md_files(["skills", "reference", "docs"]) + [
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        ROOT / ".claude-plugin" / "plugin.json",
        ROOT / "scripts" / "build_article_list.py",
        ROOT / "statutes" / "index.md",
    ]
    # 前置排除路徑片段（`reference/對照表/`、`skills/fs-quiz/`、`原始檔案/…/附表一`）
    zh_cmd = re.compile(r"(?<![\w一-鿿/.\-…])/[一-鿿]{2,}")
    own_cmd = re.compile(r"/fs-[A-Za-z0-9\-]+")
    for f in targets:
        if not f.exists():
            continue
        text = read(f)
        # CHANGELOG 記錄的是歷史，舊版指令名（`/設定`、`/猜題清單`）本就該原樣保留
        for m in () if f.name == "CHANGELOG.md" else zh_cmd.finditer(text):
            line = text[: m.start()].count("\n") + 1
            err(f"{rel(f)}:{line} 出現中文 slash command {m.group(0)!r}——指令名一律用 ASCII（`/fs-*`）")
        for m in own_cmd.finditer(text):
            if m.group(0).lstrip("/") not in names:
                line = text[: m.start()].count("\n") + 1
                err(f"{rel(f)}:{line} 引用了不存在的指令 {m.group(0)!r}（skills/ 下無同名 skill）")


def check_equipment_index() -> None:
    """延伸知識考點之「設備」須與條文表用字一致（否則掌握度分母漏算）。"""
    f = ROOT / "reference" / "索引" / "設備條文索引.md"
    if not f.exists():
        err("找不到 reference/索引/設備條文索引.md")
        return
    head, _, tail = read(f).partition("## 延伸知識考點")
    if not tail:
        err(f"{rel(f)} 找不到「延伸知識考點」節")
        return
    known = {
        c[4].strip()
        for line in head.splitlines()
        if len(c := [x.strip() for x in line.split("|")]) >= 6
        and c[1] in ("設置標準", "檢修基準", "公危管理", "其他")
    } - {"-"}
    for i, line in enumerate(tail.splitlines(), 1):
        cells = [x.strip() for x in line.split("|")]
        if len(cells) != 4 or not cells[1] or cells[1] in ("設備", "------"):
            continue
        if cells[1] not in known:
            base = head.count("\n") + 1
            err(
                f"{rel(f)}:{base + i} 延伸知識考點之設備 {cells[1]!r} 不在條文表——"
                f"掌握度分母會漏算這一列（設備名須單一且與條文表用字完全一致）"
            )


# 僅在簡體中使用的字。清單以 statutes/、corpus/ 之正體語料反向驗證過：
# 凡在那些檔案中出現過的字（伍／斗／蜂／裝／戒／准…）一律不列，避免誤判。
SIMPLIFIED_ONLY = (
    "与专业东丝两个丰为丽举义习书买产亲们价会伤关兴养军农净减凤击划则办务动医单卖卫厂厅历厉压厌县参双发变叠叶员围图壳处学实对导币师广库应废开弃张录惩战户护报损断时术机权条来构标样检残汇没洁润湿灭点"
    "烧热爱现电画紧约级纪纸纹线练组织经绕统续维绵绸缎罚艺节范药营虫虾蚁蚕蛾蝇补袄袜袭裤规计认训议讲论证评识词试话该诫语说贝财责账货质购贵贷费资赠车过还这钙钢铁铜铝银销锌长门闭问间队题饰验鱼鸟鸡鸭龙"
)

def check_simplified_chinese() -> None:
    """規格與文件不得出現簡體字（本 repo 一律正體中文）。"""
    bad = set(SIMPLIFIED_ONLY)
    targets = md_files(["skills", "reference", "docs"]) + [
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        ROOT / ".claude-plugin" / "plugin.json",
        ROOT / ".claude-plugin" / "marketplace.json",
    ]
    for f in targets:
        if not f.exists():
            continue
        for i, line in enumerate(read(f).splitlines(), 1):
            hit = sorted({c for c in line if c in bad})
            if hit:
                err(f"{rel(f)}:{i} 出現簡體字 {''.join(hit)}：{line.strip()[:60]}")


# 「累到輪末才寫」是 0.11.0 修掉的行為，措辭一旦回流就等於靜默回歸（鐵則四）
BATCH_WRITE = re.compile(
    r"(一輪(結束|完成|跑完)|輪(末|尾)|全部(答|做)完|最後(再|才)?)[^。；\n]{0,12}"
    r"(一次|統一|才|再)?[^。；\n]{0,8}(寫入|寫回|落地|存檔|記錄)"
)
NEGATION = re.compile(r"不得|不可|嚴禁|勿|不要|禁止|不能|不再|不會|非|錯誤示範|反例")


def check_write_timing() -> None:
    """規格不得出現「累到一輪結束才寫入」這類措辭（鐵則四：逐題落地）。"""
    for f in md_files(["skills", "reference"]):
        text = read(f)
        for m in BATCH_WRITE.finditer(text):
            # 取該句（前後標點之間）判斷是否為否定敘述——「不得累積到一輪結束才寫」是合規的
            s = text.rfind("\n", 0, m.start()) + 1
            for sep in ("。", "；", "**", "，"):
                k = text.rfind(sep, s, m.start())
                if k != -1:
                    s = max(s, k + len(sep))
            e = min(
                (x for x in (text.find(c, m.end()) for c in "。；\n") if x != -1),
                default=len(text),
            )
            sentence = text[s:e]
            if NEGATION.search(sentence):
                continue
            line = text[: m.start()].count("\n") + 1
            err(
                f"{rel(f)}:{line} 疑似「累到輪末才寫入」措辭（鐵則四要求逐題落地）："
                f"{sentence.strip()[:70]}"
            )


# --------------------------------------------------------------------------
# 3. corpus 索引
# --------------------------------------------------------------------------
def check_corpus_index() -> None:
    """corpus/index.json 每筆試卷之檔案路徑須實際存在。"""
    idx = ROOT / "corpus" / "index.json"
    try:
        data = json.loads(read(idx))
    except Exception as e:  # noqa: BLE001
        err(f"corpus/index.json 無法解析：{e}")
        return

    papers = data.get("papers", [])
    if not papers:
        err("corpus/index.json 的 papers 為空")
        return

    for p in papers:
        tag = f"{p.get('level')}/{p.get('year')}/{p.get('subject')}"
        for field in ("md", "pdf", "ans_pdf", "mod_ans_pdf"):
            v = p.get(field)
            if v and not (ROOT / "corpus" / v).exists():
                err(f"corpus/index.json {tag} 的 {field} 指向不存在的檔案：{v}")


# --------------------------------------------------------------------------
# 4. 文件內部連結
# --------------------------------------------------------------------------
PLACEHOLDER = re.compile(r"[<>…\*\?]|\.\.\.|｜")
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
FENCE = re.compile(r"(?ms)^```.*?^```")
INLINE_CODE = re.compile(r"`[^`\n]*`")
# 只有結尾的 ` "標題"` 才是 markdown title，路徑本身可含空白（如「第 18 條完整條文.pdf」）
LINK_TITLE = re.compile(r"\s+[\"'(].*$")


def check_links() -> None:
    """markdown 相對連結（含圖片）須指向存在的檔案。"""
    from urllib.parse import unquote

    targets = md_files(["skills", "reference", "docs", "corpus", "statutes"]) + [
        ROOT / "README.md",
        ROOT / ".claude" / "CLAUDE.md",
        ROOT / "CHANGELOG.md",
    ]
    for f in targets:
        if not f.exists():
            continue
        # 程式碼區塊與行內 code 多為範例路徑（如 `![說明](檔名.png)`），不檢查
        text = INLINE_CODE.sub("", FENCE.sub("", read(f)))
        for m in LINK.finditer(text):
            target = LINK_TITLE.sub("", m.group(1)).strip().strip("<>")
            if (
                target.startswith(("http://", "https://", "#", "mailto:"))
                or PLACEHOLDER.search(target)
            ):
                continue
            path = target.split("#")[0]
            if not path:
                continue
            if not (f.parent / unquote(path)).exists():
                err(f"{rel(f)} 連結指向不存在的路徑：{target}")


# --------------------------------------------------------------------------
# 5. skill 內文之 ${CLAUDE_PLUGIN_ROOT} 路徑
# --------------------------------------------------------------------------
# 這些寫在行內 code 裡（非 markdown 連結），link 檢查看不到，需另外驗。
PLUGIN_ROOT_REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s`)\"'，、。；：」）]+)")


def check_plugin_paths() -> None:
    """skill 內文引用之 ${CLAUDE_PLUGIN_ROOT}/... 路徑須存在（含模式檔路由）。"""
    seen: set[str] = set()
    for f in md_files(["skills"]):
        text = read(f)
        for m in PLUGIN_ROOT_REF.finditer(text):
            target = m.group(1).rstrip(".,")
            if PLACEHOLDER.search(target) or target.endswith("/"):
                continue
            seen.add(target)
            if not (ROOT / target).exists():
                line = text[: m.start()].count("\n") + 1
                err(f"{rel(f)}:{line} 引用不存在的 plugin 路徑：${{CLAUDE_PLUGIN_ROOT}}/{target}")

    check_user_config_refs()

    # 反向：模式檔若沒有任何 skill 引用，等於孤兒（拆檔後忘了接上路由）
    modes_dir = ROOT / "skills" / "exam-tutor" / "modes"
    if modes_dir.is_dir():
        for mode in sorted(modes_dir.glob("*.md")):
            target = str(mode.relative_to(ROOT))
            if target not in seen:
                err(f"{target} 未被任何 skill 引用（模式檔須列入 exam-tutor 的模式路由表）")


USER_CONFIG_REF = re.compile(r"\$\{user_config\.([A-Za-z0-9_]+)\}")


def check_user_config_refs() -> None:
    """${user_config.X} 之 X 須在 plugin.json 的 userConfig 宣告，且宣告者須有人用。"""
    try:
        declared = set(json.loads(read(ROOT / ".claude-plugin" / "plugin.json")).get("userConfig", {}))
    except Exception:  # noqa: BLE001
        return  # manifest 的問題由 check_manifests 負責回報

    used: set[str] = set()
    for f in md_files(["skills"]):
        text = read(f)
        for m in USER_CONFIG_REF.finditer(text):
            used.add(m.group(1))
            if m.group(1) not in declared:
                line = text[: m.start()].count("\n") + 1
                err(
                    f"{rel(f)}:{line} 引用未宣告的 user_config 鍵：{m.group(1)}"
                    f"（未宣告者不會被代入，會原樣顯示成文字；已宣告：{sorted(declared)}）"
                )

    for key in sorted(declared - used):
        err(f"plugin.json 宣告了 userConfig.{key}，但沒有任何 skill 以 ${{user_config.{key}}} 取用")

    # reference/ 由 Read 工具讀入，不會做 ${user_config.*} 代入，寫在那裡等於失效
    for f in md_files(["reference"]):
        text = read(f)
        for m in USER_CONFIG_REF.finditer(text):
            line = text[: m.start()].count("\n") + 1
            err(
                f"{rel(f)}:{line} 在 reference/ 使用 {m.group(0)}：代入只發生在 skill 內文，"
                f"此處會原樣顯示。請改寫成規則描述，實際值回到 SKILL.md 取。"
            )

    # skills/ 底下的非 SKILL.md（模式檔、附屬說明）同樣是被 Read 讀入的，理由同上
    for f in md_files(["skills"]):
        if f.name == "SKILL.md":
            continue
        text = read(f)
        for m in USER_CONFIG_REF.finditer(text):
            line = text[: m.start()].count("\n") + 1
            err(
                f"{rel(f)}:{line} 在非 SKILL.md 檔使用 {m.group(0)}：代入只發生在**被叫用的** "
                f"SKILL.md 內文，模式檔由 Read 讀入、佔位符會原樣顯示。"
                f"請把代入區塊放到叫用此檔的指令 SKILL.md。"
            )

    check_user_config_injection(declared)


# 指令檔末尾的代入區塊起始標記（見 reference/user-config-spec.md「設定解析順序」）
INJECTION_BLOCK = "**目前的 plugin 設定值**"

# 「這支 skill 會用到使用者設定」的跡象。只看代入區塊**之前**的正文，
# 否則區塊自己提到 user-config-spec.md／<data_dir> 會讓判斷變成循環。
SETTINGS_HINT = re.compile(r"user-config-spec\.md|<data_dir>|config\.json|progress\.json")


def check_user_config_injection(declared: set[str]) -> None:
    """會用到使用者設定的 SKILL.md 須自帶 ${user_config.*} 代入區塊（issue #59）。

    代入只發生在「被叫用的那份 SKILL.md」；使用者實際叫用的是指令檔，
    只在正文寫「去讀某個 skill／模式檔」是取不到 plugin 設定的。
    `/fs-mock` 尤其不可省——它以 context: fork 執行，取不到值也無法回頭詢問。
    """
    for f in sorted((ROOT / "skills").rglob("SKILL.md")):
        text = read(f)
        body = text.split(INJECTION_BLOCK, 1)[0]
        if not SETTINGS_HINT.search(body):
            continue  # 這支不碰使用者設定（如 exam-archive、對照表）
        missing = sorted(k for k in declared if f"${{user_config.{k}}}" not in text)
        if missing:
            err(
                f"{rel(f)} 會用到使用者設定卻缺少代入區塊，未取用：{missing}。"
                f"請於檔末補上「{INJECTION_BLOCK}」區塊並列出全部 userConfig 鍵，"
                f"否則「設定解析順序」的順序 1（plugin 設定）在此指令路徑上永遠取不到值。"
            )


# --------------------------------------------------------------------------
# 6. 格式規範（CLAUDE.md 之機械可驗部分）
# --------------------------------------------------------------------------
# 「任何有平方的數字／單位一律以上標 ² 表示」——適用所有內容資料夾
SQUARED = re.compile(r"(?<![A-Za-z0-9])((?:c|m|k|d)?m|kgf/cm|N/mm)([23])(?![0-9A-Za-z\-])")

# 「條文階層編號之括號一律使用全形（）」——**只適用 statutes/**（法規條文）。
# corpus/ 的 (A)(B)(C)(D) 是考卷選項標記、reference/輸出格式/ 是選項版面範本，
# 兩者都不是條文階層編號，不受此規範。
HALFWIDTH_NUM = re.compile(
    r"(?m)^\s*(?:[-*>|]\s*)?\((?:[一二三四五六七八九十]+|\d{1,2})\)\s*[、\s]"
)


def check_format_rules() -> None:
    """上標（全內容資料夾）與條文階層編號全形括號（僅 statutes/）。"""
    for f in md_files(CONTENT_DIRS):
        text = read(f)
        for m in SQUARED.finditer(text):
            line = text[: m.start()].count("\n") + 1
            err(
                f"{rel(f)}:{line} 平方／立方未用上標：{m.group(0)!r} "
                f"（應寫成 {m.group(1)}{'²' if m.group(2) == '2' else '³'}）"
            )

    for f in md_files(["statutes"]):
        text = read(f)
        for m in HALFWIDTH_NUM.finditer(text):
            line = text[: m.start()].count("\n") + 1
            err(f"{rel(f)}:{line} 條文階層編號使用半形括號：{m.group(0).strip()!r}（應改全形（））")


# --------------------------------------------------------------------------
# skill 直接指定行號讀取 user-config-spec 的寫入 schema，區段位移就會讀錯
# --------------------------------------------------------------------------
# 只認「同一行同時出現 user-config-spec 與 offset/limit」者，避免誤抓
# 同一份 SKILL.md 裡談 statutes 條文區段的 offset 範例
SPEC_RANGE_REF = re.compile(r"offset=(\d+)\s+limit=(\d+)")


def check_progress_spec_range() -> None:
    """skill 引用之 user-config-spec.md 寫入 schema 行號須與實際區段相符。"""
    spec = ROOT / "reference" / "user-config-spec.md"
    if not spec.exists():
        err("reference/user-config-spec.md 不存在")
        return

    lines = read(spec).splitlines()
    start = end = None
    for i, line in enumerate(lines, 1):
        if line.startswith("## progress.json"):
            start = i
        elif start is not None and line.startswith("## 弱點筆記格式"):
            end = i - 1
            break
    if start is None or end is None:
        err(
            "user-config-spec.md 找不到寫入 schema 區段的邊界標題"
            "（`## progress.json` … `## 弱點筆記格式`）；skill 以行號取用該段，請同步修正"
        )
        return

    expect = (start, end - start + 1)
    cited = 0
    for f in md_files(["skills"]):
        for lineno, line in enumerate(read(f).splitlines(), 1):
            if "user-config-spec" not in line:
                continue
            for m in SPEC_RANGE_REF.finditer(line):
                cited += 1
                got = (int(m.group(1)), int(m.group(2)))
                if got != expect:
                    err(
                        f"{rel(f)}:{lineno} 指定的 user-config-spec 讀取範圍已失效："
                        f"寫 offset={got[0]} limit={got[1]}，實際寫入 schema 區段為第 {expect[0]}–{end} 行"
                        f"（offset={expect[0]} limit={expect[1]}）"
                    )
    if not cited:
        warn(
            "沒有任何 skill 以行號引用 user-config-spec 的寫入 schema 區段"
            "（若已改為其他取用方式，本檢查可移除）"
        )


# --------------------------------------------------------------------------
# 設備正規名詞彙：索引之「設備分類」欄須與 tags_index 之 by_equipment 鍵一致，
# 否則正規化後以索引名查標籤會回 null，整個設備的題目都撈不到（issue #77）
# --------------------------------------------------------------------------
# 已裁定之正當例外，每一項都要有理由；新增例外前請先確認不是單純打錯字
EQUIP_VOCAB_EXCEPTIONS = {
    # 索引有、tags 無
    "其他": "設置標準 §234 等不屬特定設備之條文，無對應 tag",
    "配線": "檢修基準第 27 章，跨設備之共通檢修項目，非獨立設備",
    # tags 有、索引無
    "二氧化碳滅火設備": "與「二氧化碳及惰性氣體滅火設備」同屬設置標準第六節（§82–§97），"
    "為 CO₂ 專題之標籤；索引以現行節名收錄，exam-tutor SKILL.md 規定兩鍵併查",
    "消防幫浦/加壓送水裝置": "跨設備共用元件，各水系統之加壓送水裝置條文分別掛在該設備下"
    "（室內消防栓 §37、水霧 §65、泡沫 §77）；僅供標籤統計與交叉補題，不作為出題單元",
}


def check_equipment_vocab() -> None:
    """設備條文索引之「設備分類」欄須與 tags_index 之 by_equipment 鍵一致。"""
    idx = ROOT / "reference" / "索引" / "設備條文索引.md"
    tags = ROOT / "corpus" / "tags_index.json"
    if not idx.exists() or not tags.exists():
        warn("設備條文索引或 tags_index.json 不存在，跳過設備詞彙比對")
        return

    in_index: set[str] = set()
    for line in read(idx).splitlines():
        cells = [c.strip() for c in line.split("|")]
        # 資料列形如 `| 法源 | 條文 | 場所 | 設備分類 | 項目 |` → 去頭尾空字串後第 4 欄
        if len(cells) < 7 or cells[1] in ("法源", "") or set(cells[1]) <= {"-"}:
            continue
        # 設備分類為 `-` 者是不屬特定設備之條文（如設置標準 §1 授權法源），非設備名
        if cells[4] and not set(cells[4]) <= {"-"}:
            in_index.add(cells[4])

    try:
        in_tags = set(json.loads(read(tags)).get("by_equipment", {}))
    except Exception as e:  # noqa: BLE001
        err(f"tags_index.json 無法解析：{e}")
        return

    if not in_index:
        err("設備條文索引解析不到任何「設備分類」值（表格格式可能已變更）")
        return

    for name in sorted(in_index - in_tags - set(EQUIP_VOCAB_EXCEPTIONS)):
        err(
            f"設備條文索引之「{name}」在 corpus/tags_index.json 的 by_equipment 查不到——"
            "依此名取標籤會回 null，該設備的題目一題都撈不到。"
            "請更正索引用語，或在 EQUIP_VOCAB_EXCEPTIONS 附理由列為例外"
        )
    for name in sorted(in_tags - in_index - set(EQUIP_VOCAB_EXCEPTIONS)):
        err(
            f"tags_index 有 by_equipment「{name}」但設備條文索引無對應課綱列——"
            "該設備有題目卻無出題順序可循。請補課綱列，"
            "或在 EQUIP_VOCAB_EXCEPTIONS 附理由列為例外"
        )
    # 例外一旦被消化（兩邊都有或兩邊都無）就該移除，免得清單長年累積失效項目
    for name in sorted(EQUIP_VOCAB_EXCEPTIONS):
        if (name in in_index) == (name in in_tags):
            warn(
                f"EQUIP_VOCAB_EXCEPTIONS 的「{name}」已不再是落差"
                f"（兩邊皆{'有' if name in in_index else '無'}），可從例外清單移除"
            )


# --------------------------------------------------------------------------
CHECKS = {
    "manifests": check_manifests,
    "skills": check_skills,
    "slash-commands": check_slash_commands,
    "equipment-index": check_equipment_index,
    "simplified-chinese": check_simplified_chinese,
    "write-timing": check_write_timing,
    "corpus-index": check_corpus_index,
    "links": check_links,
    "plugin-paths": check_plugin_paths,
    "format-rules": check_format_rules,
    "progress-spec-range": check_progress_spec_range,
    "equipment-vocab": check_equipment_vocab,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="列出可用檢查後結束")
    ap.add_argument("-k", metavar="SUBSTR", help="只跑名稱含 SUBSTR 的檢查")
    args = ap.parse_args()

    if args.list:
        for name, fn in CHECKS.items():
            print(f"{name:<14} {(fn.__doc__ or '').splitlines()[0]}")
        return 0

    selected = {n: f for n, f in CHECKS.items() if not args.k or args.k in n}
    if not selected:
        print(f"沒有符合 {args.k!r} 的檢查", file=sys.stderr)
        return 2

    for name, fn in selected.items():
        before = len(errors)
        fn()
        status = "FAIL" if len(errors) > before else "ok"
        print(f"[{status:>4}] {name}")

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")

    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main())
