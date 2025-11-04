import re, unicodedata
from google.genai import types
import json
import re
from google.genai import types
from google import genai
import os

# IMPORTANT: Do not hardcode API keys. Read from environment or be set by GUI at runtime.
API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"


def parse_references_with_gemini(ref_text: str):
    """
    使用 Gemini API 將參考文獻純文字區塊解析為結構化資料。

    Args:
        ref_text: 包含所有參考文獻的單一字串。

    Returns:
        一個包含解析後文獻字典的 list，以及解析失敗的原始字串 list。
    """

    # 設計一個強力的 Prompt，包含詳細指令和範例 (Few-shot Prompting)
    prompt = f"""
You are an expert academic reference parser. Your task is to parse the user-provided reference list text into a clean, structured JSON format.

Follow these rules strictly:
1.  Analyze each entry in the reference list.
2.  For each entry, extract the following fields: "authors" (a list of all author surnames), "year", "title", and "doi".
3.  If a field is not present, use an empty string "" for "title" and "doi", or an empty list [] for "authors". The "year" must be an integer.
4.  The output MUST be a valid JSON array (a list of objects). Do not include any text or explanations outside of the JSON structure.

Here are some examples:

---
Input Text:
Rushton, A., Croucher, P., & Baker, P. (2017). The handbook of logistics and distribution management: Understanding the supply chain (6th ed.). Kogan Page Publishers.
Liao, C.-H., Huang, J.-Y., & Chang, C.-C. (2023). The mediation of trust on artificial intelligence (AI) in service: An empirical study of the roles of AI anxiety and AI awareness. Computers in Human Behavior, 138, 107517. https://doi.org/10.1016/j.chb.2022.107517
駱俊宏、方世榮、洪東興（2005）。服務品質、關係品質與顧客忠誠度之研究—以網路購物中心為例。中華管理評論，8(1)，1-25。

Expected JSON Output:
[
    {{
        "authors": ["Rushton", "Croucher", "Baker"],
        "year": 2017,
        "title": "The handbook of logistics and distribution management: Understanding the supply chain (6th ed.)",
        "doi": ""
    }},
    {{
        "authors": ["Liao", "Huang", "Chang"],
        "year": 2023,
        "title": "The mediation of trust on artificial intelligence (AI) in service: An empirical study of the roles of AI anxiety and AI awareness",
        "doi": "10.1016/j.chb.2022.107517"
    }},
    {{
        "authors": ["駱俊宏", "方世榮", "洪東興"],
        "year": 2005,
        "title": "服務品質、關係品質與顧客忠誠度之研究—以網路購物中心為例",
        "doi": ""
    }}
]
---

Now, parse the following reference list:

{ref_text}
"""

    try:
        # Require API key at runtime; GUI 版本會注入，CLI 可透過環境變數提供
        if not API_KEY:
            raise RuntimeError("Gemini API key is not set. Please set GEMINI_API_KEY env var or use the GUI to input it.")
        client = genai.Client(api_key = API_KEY)
        response = client.models.generate_content(
            model= GEMINI_MODEL,
            contents= prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        
        # 從回應中提取 JSON 內容
        # Gemini 有時會在 JSON 前後加上 ```json ... ```，需要移除
        json_text = re.search(r'\[.*\]', response.text, re.DOTALL).group(0)
        
        parsed_refs = json.loads(json_text)
        
        # (可選) 增加一個 raw 欄位，方便後續對照
        # 這部分邏輯可以更複雜，例如用標題相似度來匹配
        # 這裡用一個簡化版，假設順序不變
        raw_lines = [line.strip() for line in ref_text.split('\n') if line.strip()]
        
        results = []
        fails = []

        for ref_data in parsed_refs:
            # 進行基本的資料清理和格式化
            # 這裡的 _surname 函式來自您原本的 reference_extractor.py
            authors = ref_data.get("authors", [])
            surnames = [_surname(name) for name in authors] # 使用您既有的姓氏正規化工具

            results.append({
                "authors": surnames,
                "year": int(ref_data.get("year", 0)),
                "title": ref_data.get("title", "").strip(),
                "doi": ref_data.get("doi", "").strip(),
                "raw": "" # 您可以之後再填充這個欄位
            })
            
        return results, fails # 回傳與原函式相同的格式 (refs, fails)

    except (Exception, json.JSONDecodeError) as e:
        print(f"Gemini API 呼叫或 JSON 解析失敗: {e}")
        # 如果失敗，回傳空的結果，讓後續流程知道
        return [], [ref_text]

def _surname(name: str) -> str:
    """從您的 reference_extractor.py 複製過來，確保函式可用"""
    name = name.strip()
    if not name:
        return ""
    if re.search(r"[A-Za-z]", name):
        name = name.split(",")[0] if "," in name else name.split()[-1]
    else:
        name = name[0]
    return name.lower()

CN_PAT = re.compile(r"""
^
(?P<authors>[\u4e00-\u9fff、與和,，\s]+?)\s*     # ← ① 作者可含空白
[（(](?P<year>\d{4})[)）]\s*[。\.]\s*           #   ② 作者後空白 + （2005）。
(?P<title>.+?)\s*[。\.]\s*
(?P<journal>[^,，]+)[,，]\s*
(?P<vol>\d+)[,，]\s*
(?P<pages>\d+[-–]\d+)
[。\.]?\s*
(?:https?://\S*doi\.org/|doi[:：]?\s*)?
(?P<doi>10\.\S+)?\s*$
""", re.X | re.S)


CN_FUZZY_PAT = re.compile(r"""
^(?P<authors>[\u4e00-\u9fff、與和]+).*?        # 作者
([（(]?(?P<year>\d{4})[a-z]?[）)]?).*?         # 年
(?P<doi>10\.\S+)$                             # 行尾 DOI
""", re.X | re.S)

GEN_PAT = re.compile(r"""
^(?P<authors>.+?)\s*\(\s*(?P<year>\d{4})[a-z]?\)\.\s*
(?P<rest>.+?)\s*
(?:https?://\S*doi\.org/|doi[:：]?\s*)?
(?P<doi>10\.\S+)?\s*$   # ← 末尾 ? 代表可無
""", re.X | re.S | re.I)

BOOK_PAT = re.compile(r"""
^(?P<authors>.+?)\s*\((?P<year>\d{4})\)\.\s*
(?P<title>.+?)\s*\(pp\..+?\)\.\s*        # 可有 pp.、vi, 329 等
[^.]*?Press\.?\s*                        # 以 Press. 結尾
(?P<doi>10\.\S+)?\s*$                    # 通常沒有 DOI
""", re.X | re.S | re.I)




# 只換到 REF_PAT 這一行，其餘程式碼維持
REF_PAT = re.compile(r"""
^
(?P<authors>.+?)\s*\(\s*(?P<year>\d{4})[a-z]?\)\.\s*   # 作者(年).
(?P<title>.+?)\s*(?:\.\s*|:\s*|$)                               # 標題後可接「.」或「:」或「,」
(?P<journal>[^.,]+?)\s*,?\s*                           # 期刊
(?P<vol>\d+)?                                          # 卷
(?:\((?P<issue>\d+)\))?\s*,?\s*                        # (期)
(?P<pages>\d+[-–]\d+)?\.?\s*                           # 版次
(?:https?://\s*\S*doi\.org/|doi[:：]?\s*)?             # DOI 前綴可有可無
(?P<doi>10\.\S+)?\s*$                                  # DOI
""", re.X | re.I | re.S)


REF_RE = re.compile(
    r"^\s*(參考資料?|References?)\s*$",  # 行首行尾，避免 TOC 的「…… 25」
    flags=re.I | re.M,
)

_ZH_PUNCT_MAP = str.maketrans({
    '（': '(', '）': ')', '。': '.', '、': ',',
    '，': ',', '：': ':', '；': ';'
})
def _normalize_punct(text: str) -> str:
    NBSP = '\u00A0'
    text = text.replace(NBSP, ' ')
    return text.translate(_ZH_PUNCT_MAP)



def _split_refs(line: str) -> list[str]:
    """
    若同一行含多筆「Author (Year)」參考文獻，遞迴拆成多行。
    不符合條件時會原封不動回傳，所以加了也不會破壞舊邏輯。
    """
    pattern = re.compile(
        r"(?<![A-Z一-龥])\.\s+"                     # 句點＋空白，但左邊不能是另一個作者起始
        r"(?<![A-Z一-龥])\.\s+(?=[A-Z一-龥][A-Za-z一-龥'’.\-]+[^()]{0,400}\(\d{4}[a-z]?\))"
    )
    segs, queue = [], [line]
    while queue:
        ln = queue.pop()
        parts = pattern.split(ln, 1)              # 只切一次；若還能切再放回 queue
        if len(parts) == 2:
            queue.extend(parts[::-1])             # 保持原本順序
        else:
            segs.append(ln.strip())
    return segs

def extract_block(text, span=50000):
    """從 pdf 文字中擷取『參考文獻』區塊；取最後一個標題開始算。"""
    matches = list(REF_RE.finditer(text))
    if not matches:
        return ""          # 整份文件都沒 References 字樣
    start = matches[-1].start()     # ← 最後一筆
    return text[start : start + span]


def _surname(name: str) -> str:
    """回傳英文逗號前／英文最後 token；中文取第一字，全小寫。"""
    name = name.strip()
    if not name:
        return ""
    if re.search(r"[A-Za-z]", name):
        # 'Smith, J.' → 'Smith'；'John   Smith' → 'Smith'
        name = name.split(",")[0] if "," in name else name.split()[-1]
    else:
        # 中文『駱俊宏』→『駱』
        name = name[0]
    return name.lower()

def _normalize_punct(text: str) -> str:
    text = text.translate(_ZH_PUNCT_MAP)
    # 刪掉常見 italic/underline 標記：_Title_、*Title*、<i>Title</i>
    text = re.sub(r"[_*](.+?)[_*]", r"\1", text)   # _Title_ or *Title*
    text = re.sub(r"</?i>", "", text, flags=re.I)  # <i>Title</i>
    return text




def parse_references(ref_text: str, *, debug=False, dump_file=None):
    refs, fails = [], []

    # ------ ❶ 把多行合併成「以句號結尾」的段落 -----------------
    lines = [ln.strip() for ln in ref_text.splitlines() if ln.strip()]
    lines = [_normalize_punct(ln) for ln in lines]
    lines = [ln for ln in lines if ln not in {"參考資料", "中文文獻", "英文文獻"}]

    merged_lines, buf, buf_has_year = [], [], False
    DOI_LINE = re.compile(r"^(https?://\s*\S*doi\.org/|10\.\d{4,9}/\S+)", re.I | re.S)
    PAGE_NUM = re.compile(r"^\d+$", re.S) 
    AUTHOR_YEAR = re.compile(r".+[\(（]([12]\d{3})[a-z]?[\)）]", re.S) 
    DOI_FRAGMENT = re.compile(r"^\d+\.\d+\.\d+\.\d+$", re.S)
    

    for ln in lines:
        ln = re.sub(r'^\d+\s*[\.\t]?[\s–-]*', '', ln)
        if not ln or PAGE_NUM.match(ln):
            continue


        if DOI_FRAGMENT.match(ln) and buf:
            buf[-1] += " " + ln
            continue

        if DOI_LINE.match(ln) or (DOI_FRAGMENT.match(ln) and buf):
            buf[-1] += " " + ln if buf else ln
            continue

        if AUTHOR_YEAR.match(ln) and buf:
            if not re.match(r"[A-Z一-龥]", ln[0]):
                buf[-1] += " " + ln
                continue
        
        
            merged_lines.append(" ".join(buf))
            buf = [ln]
            continue

        has_year = bool(AUTHOR_YEAR.search(ln))
        if has_year and buf_has_year:
            merged_lines.append(" ".join(buf))
            buf, buf_has_year = [], False



        if buf and re.match(r"^[A-Z][A-Za-z &\-]+[,]?\s*\d", ln):
            buf[-1] += " " + ln
            continue 

        if buf and re.match(r"^\d+\([\d–-]+\)", ln):
            buf[-1] += " " + ln
            continue

        if buf and "Science," in ln:
            buf[-1] += " " + ln
            continue

        if buf and AUTHOR_YEAR.search(buf[-1]) and not re.match(r"[A-Z一-龥]", ln[0]):
            buf[-1] += " " + ln
            continue


        if buf and (
            re.match(r"^[A-Z][A-Za-z &\-]+[,，]?$", ln)              # Science, Nature,
            or re.match(r"^\d+\([\d–-]+\)", ln)                     # 319(5870)
            or ln.startswith("https://doi.org") or ln.startswith("doi")
            ):
            buf[-1] += " " + ln
            continue 

        if buf and not ln.endswith(".") and not AUTHOR_YEAR.match(ln):
            buf[-1] += " " + ln
            continue   

        buf.append(ln)
        buf_has_year = buf_has_year or has_year


    if buf:                                     # 檔尾殘留
        merged_lines.append(" ".join(buf))

    if dump_file:
        with open(dump_file, "w", encoding="utf-8") as f:
            for i, line in enumerate(merged_lines, 1):
                f.write(f"{i:03d}\t{line}\n")

    fixed_lines = []
    for raw in merged_lines:
        raw = re.sub(r"(10\.\d{4,9}/\S*?)[\s\u00A0]+(\S+)", r"\1\2", raw)
        fixed_lines.append(raw)
    merged_lines = fixed_lines

    tmp_lines = []
    for raw in merged_lines:
        raw = re.sub(r"(10\.\d{4,9})/+(\S+)", r"\1/\2", raw)          # 10.1037// → /
        prev = None
        while prev != raw:
            prev = raw
            raw = re.sub(r"(10\.\d{4,9}/\S*?)\s+(\S+)", r"\1\2", raw)  # 刪掉中途空白
        # 若 DOI 後面立刻跟作者大寫或中文姓氏，re.split 會把 DOI 單獨抽出
        DOI_TOKEN = r"(10\.\d{4,9}/\S+)"
        parts = re.split(fr"{DOI_TOKEN}\s+(?=[A-Z一-龥])", raw)
        if len(parts) == 1:
            tmp_lines.append(raw)
        else:
            # re.split 會保留 group；把切出的片段重新整理、丟回 list
            cur = ""
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                # 若是 DOI 片段，先接到前段再立即 flush
                if re.match(r"10\.\d{4,9}/\S+", p):
                    cur = f"{cur} {p}".strip()
                    tmp_lines.append(cur)
                    cur = ""
                else:
                    # 普通文字段；若前面還有累積，就 flush
                    if cur:
                        tmp_lines.append(cur)
                    cur = p
            if cur:
                tmp_lines.append(cur)

    merged_lines = tmp_lines

    # ----- PATCH A: DOI 斷行  ---------------------------------------
    URL_TOKEN = r"(?:https?://\S+|10\.\d{4,9}/\S+)"
    split_lines = []
    for raw in merged_lines:
        m = re.search(URL_TOKEN, raw)
        if m and re.match(r"\s+[A-Z一-龥]", raw[m.end():]):
        # ① DOI 以前（含 DOI）視為本條結尾
            split_lines.append(raw[:m.end()].rstrip())
        # ② DOI 之後若還有文字，視為下一條待處理
            split_lines.append(raw[m.end():].lstrip()) 
        else:
           split_lines.append(raw)
    merged_lines = split_lines
# --------------------------------------------------------------


    AUTHOR_YEAR_PHRASE = re.compile(
        r"[A-Z一-龥][A-Za-z一-龥'’\-\.]+[^()]{0,800}?\([12]\d{3}[a-z]?\)"
    )

    tmp1 = []
    for raw in merged_lines:
        parts = re.split(r"(10\.\d{4,9}/\S+)\s+(?=[A-Z一-龥])", raw)
        if len(parts) == 1:
            tmp1.append(raw)
        else:
            for p in parts:
                p = p.strip()
                if p:
                    tmp1.append(p)

# ❷ 再抓 "句點 + 空白 + 新作者(年)"
    tmp2 = []
    for raw in tmp1:
        parts = re.split(r"\.\s+(?=[A-Z一-龥][A-Za-z一-龥'’\-\.]+[^()]{0,40}?\([12]\d{3})", raw)
        if len(parts) == 1:
            tmp2.append(raw)
        else:
            tmp2.extend([p.strip() for p in parts if p.strip()])


    split_lines = []

    for raw in merged_lines:
        matches = list(AUTHOR_YEAR_PHRASE.finditer(raw))
        if len(matches) <= 1:
            split_lines.append(raw)
            continue

        # 依 match span 切段
        start = 0
        for m in matches[1:]:
            split_lines.append(raw[start:m.start()].strip())
            start = m.start()
        split_lines.append(raw[start:].strip())

    merged_lines = [ln for ln in split_lines if ln]

    split_lines = []
    for raw in merged_lines:
        m = re.search(r"(10\.\d{4,9}/\S+)", raw)
        if m:
        # a. DOI 前段（含 DOI）
            split_lines.append(raw[: m.end()].strip())
        # b. DOI 後段（可能還有下一篇作者(年)）
            tail = raw[m.end():].strip()
            if tail:
                split_lines.append(tail)
        else:
            split_lines.append(raw)
    merged_lines = split_lines

    tmp = []
    for ln in merged_lines:
        tmp.extend(_split_refs(ln))
    merged_lines = tmp

    # ------ ❷ 對每一條 merged_line 跑 PAT ----------------------
    CHAP_PAT = re.compile(r"""
    ^(?P<authors>.+?)\s*\((?P<year>\d{4})\)\.\s*
    (?P<title>.+?)\.\s*                # ← `.+?` 已允許換行被合併
    In\s+[^.]+?\(Vol\.\s*\d+.*?\),?\s*
    p{1,2}\.\s*\d+[-–]\d+\)\.\s*
    (?:https?://\S*doi\.org/|doi[:：]?\s*)?
    (?P<doi>10\.\S+)?$
    """, re.X | re.I | re.S)


    for raw in merged_lines:
        m = REF_PAT.match(raw)
        if not m:
            m = CHAP_PAT.match(raw) or CN_PAT.match(raw)
        if not m:
            m = GEN_PAT.match(raw) or CN_FUZZY_PAT.match(raw) or BOOK_PAT.match(raw)  # ★ 新增保底
        if not m:
            if debug: fails.append(raw)
            continue

        # -- 以下取作者、年、標題、doi 與之前相同 -----------------
        authors_raw = m.group("authors")
        names = re.split(r"[、,，&和與]", authors_raw)
        authors = [_surname(n) for n in names if n.strip()]
        year = int(m.group("year"))

        if m.re is CN_FUZZY_PAT:
            after_year = raw.split(")。", 1)[-1]          # 年份後開始
            title = after_year.split("。", 1)[0].strip()  # 到第一個句號
        elif m.re is GEN_PAT:
            rest = m.group("rest")
            title = re.split(r"[.:]", rest, 1)[0].strip() # 取第一個 . 或 :
        elif m.re is BOOK_PAT:
            title = m.group("title").strip()
        else:
            title = m.group("title").strip()

        #title = m.group("title").strip()
        title = re.sub(r"https?://\S+|www\.\S+", "", title).strip(" .")
        doi = (m.group("doi") or "").rstrip(").").strip()
        refs.append({
            "authors": authors,
            "year": year,
            "title": title,
            "doi": doi,
            "raw": raw
        })

    return (refs, fails) if debug else refs
