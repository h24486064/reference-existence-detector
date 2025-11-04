# matcher.py   --------- 2025-07-16 重構版
from difflib import SequenceMatcher
import re
from typing import List, Dict, Any
from weakref import ref

# ------------------------ 私有工具 ------------------------
def _norm_author(name: str) -> str:
    """
    只留「第一作者姓」，處理：
      - 'Almeida et al.' / 'Almeida, J.' / 'Almeida 等'
      - 'Batra & Ray'
      - 中文姓：'林俊宏' -> '林'
    全部轉小寫，空字串回 ''。
    """
    if not name:
        return ""
    name = re.sub(r"[']", "", name) 
    name = re.split(r"[,&、和與]", name.strip())[0]           # 只保留第一個
    # 英文姓 → 取最後一段；中文直接用
    if re.search(r"[A-Za-z]", name):
        name = name.split()[-1]
    return name.lower()

def _title_sim(a: str, b: str) -> float:
    """兩字串相似度；任一<10字就回 0，避免短字串誤配。"""
    if len(a) < 10 or len(b) < 10:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# ----------------------- 對外介面 -------------------------
def match_inline_to_ref(inlines: List[Dict[str, Any]],
                        refs:    List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parameters
    ----------
    inlines : 引用清單（至少含 'author', 'year' 欄）
    refs    : reference_extractor.parse_references() 的結果

    Returns
    -------
    list[dict] — 每條 inline 加上 'title' 'doi'，找不到則空字串
    """
    # 先用 (first_author, year) 建倒排索引，加速查找
    idx = {}
    for r in refs:
        if not r.get("authors") or not r.get("year"):
            continue
        first = _norm_author(r["authors"][0])
        key = (first, int(str(r["year"])[:4]))
        idx.setdefault(key, []).append(r)

    out = []
    for c in inlines:
        key = (_norm_author(c["author"]), int(str(c["year"])[:4]))
        cand = idx.get(key, [])

        if not cand:
            out.append({**c, "title": "", "doi": ""})
            continue


        raw = c.get("raw_text") or c.get("raw") or ""

        def _score(ref):
            sim = _title_sim(ref["title"], raw)          # 0~1
            return (sim, ref.get("doi") != "", len(ref["title"]))

        best = max(cand, key=_score)

        out.append({**c, "title": best.get("title",""), "doi": best.get("doi",""), "raw":   best.get("raw","")})

    return out
