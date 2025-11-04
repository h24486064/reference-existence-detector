"""
Lightweight Crossref REST wrapper (no external deps except requests)
Usage:  from crossref_client import lookup
"""

import requests, time, logging
from difflib import SequenceMatcher
import requests, time, logging, re
from difflib import SequenceMatcher
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE = "https://api.crossref.org/works"
HEADERS = {"User-Agent": "pipeline/1.1 (mailto:r76131036@gs.ncku.edu.tw)"}
TIMEOUT = (5, 30)        # (connect, read) 讀取拉長到 30s

session = requests.Session()
retry = Retry(
    total=3, backoff_factor=1.5,
    status_forcelist=[500, 502, 503, 504, 520],
    allowed_methods=["GET"]
)
session.mount("https://", HTTPAdapter(max_retries=retry))

DOI_PAT = re.compile(r"10\.\d{4,9}/\S+", re.I)

def enrich_refs(refs: list[dict]) -> list[dict]:
    """直接接收 canonicalize_refs() 的輸出 → 回傳加了 Crossref 欄位的 list"""
    enriched = []
    for rec in refs:
        enriched.append({**rec, **lookup(rec)})   # lookup() 原本的單筆查詢
    return enriched

def _sim(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() if a and b else 0

def _clean_doi(d: str) -> str:
    if not d: return ""
    d = DOI_PAT.search(d)  # 把作者等多餘字元切掉
    return d.group(0) if d else ""

def lookup(row, pause=0.2):
    time.sleep(pause)      # 控制速率
    doi = _clean_doi(row.get("doi", ""))
    try:
        if doi:
            url, params = f"{BASE}/{doi}", {}
        else:
            params = {
                "query.bibliographic": row["title"][:250],  # 避免太長
                "query.author": row["author"][:100],
                "filter": f"from-pub-date:{row['year']},until-pub-date:{row['year']}",
                "rows": 1,
            }
            url = BASE
        params["mailto"] = HEADERS["User-Agent"].split("mailto:")[1][:-1]
        r = session.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        if r.status_code in (404, 400):
            logging.warning("Crossref error %s for %s", r.status_code, doi or row["title"][:40])
            return {"found": 0, "cr_title": "", "cr_doi": ""}
        r.raise_for_status()
    except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
        logging.error("Crossref timeout跳過：%s", doi or row["title"][:40])
        return {"found": 0, "cr_title": "", "cr_doi": ""}
    data = r.json()["message"]
    if "items" in data:
        data = data["items"][0] if data["items"] else {}
    cr_doi   = data.get("DOI", "")
    cr_title = data.get("title", [""])[0] if isinstance(data.get("title"), list) else data.get("title", "")
    ok = bool(cr_doi) and _sim(row["title"], cr_title) > 0.7
    return {"found": int(ok), "cr_title": cr_title, "cr_doi": cr_doi}
