#!/usr/bin/env python
"""
main.py － 全自動批次版
PDF → 引用抽取 → 參考文獻解析 → 配對 → Crossref → 輸出 CSV
執行方式：python main.py   （不需任何參數）
"""

import pathlib, time, pandas as pd
import reference_extractor as rex
import extract_citations_v19 as citex
import matcher, crossref_client as cr
from verify_refs import canonicalize_refs
from crossref_client import lookup

PDF_DIR   = pathlib.Path(r"D:\成功大學\學生資料\研究助理\for_test\submission")   
OUT_DIR   = pathlib.Path(r"D:\成功大學\學生資料\研究助理\for_test")  
EMAIL     = "r76131036@gs.ncku.edu.tw"                # Crossref polite‑pool

cr.HEADERS["User-Agent"] = f"pipeline/1.0 (mailto:{EMAIL})"
OUT_DIR.mkdir(exist_ok=True)

def pdf_to_text(pdf_path: pathlib.Path) -> str:
    from pdfminer.high_level import extract_text
    return extract_text(str(pdf_path))

def handle_one(pdf_path: pathlib.Path):
    raw_txt   = pdf_to_text(pdf_path)
    intext    = citex.extract_citations_v19(raw_txt) 
    ref_block = rex.extract_block(raw_txt)

    refs = rex.parse_references(ref_block)   
    refs = canonicalize_refs(refs)
    df_match = matcher.match_inline_to_ref(intext, refs)
    for r in refs:
        r["author"] = r["authors"][0] if r["authors"] else "?"


    rows = [{**rec, **cr.lookup(rec)} for rec in df_match]
    out_file = OUT_DIR / f"{pdf_path.stem}_enriched.csv"
    pd.DataFrame(rows).to_csv(out_file, index=False, encoding="utf-8-sig")
    print(f"✔ {pdf_path.name} → {out_file.name}")

def main():
    for pdf in PDF_DIR.glob("*.pdf"):
        handle_one(pdf)
        time.sleep(0.5)  
    print("finish")

if __name__ == "__main__":
    main()
