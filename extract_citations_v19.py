# final_test_and_export_v19.py

import re
import unicodedata
import time
import pprint
import csv
from document_processor import pdf_to_text
from reference_extractor import REF_RE

# -------------------- V19 核心函式 --------------------
def extract_citations_v19(text: str):
    # --- 步驟 1: 強力預處理 ---
    text = unicodedata.normalize("NFC", text).replace("’", "'")
    text = re.sub(r'[\x00-\x1f\u200b\ufeff]', '', text)

    # text = unicodedata.normalize("NFKD", text)
    # text = ''.join(ch for ch in text if not unicodedata.combining(ch))

    results = []
    processed_mask = [False] * len(text)
    YEAR_PAT = r"\b\d{4}[a-z]?\b"

    # --- 步驟 2: 定義兩套獨立且經過強化的規則 ---
    
    # 規則 A: 專門處理英文/西文引用，並開放「白名單」中文連接詞
    # 這是這次修改的靈魂：在允許的字元集中，加入了 與, 和, 以及
    ENG_AUTHOR_CHARS_WITH_WHITELIST = r"[A-Za-zÀ-ž\d&'.,\-\s與和以及]"
    
    ENG_CITE_PAT = re.compile(
        rf"""
        # 確保左邊界不是一個緊跟著的中文字，避免從中文句子中間開始匹配
        (?<![A-Za-z]) 
        (?P<author>{ENG_AUTHOR_CHARS_WITH_WHITELIST}{{1,79}}?) # 非貪婪匹配，限制長度
        (?:\s*(?:et\s+al\.|等[\s\u3000]*人?)\s*)?
        \s*
        [（(]
        \s*
        (?P<year>{YEAR_PAT})
        .*?
        [)）]
        """,
        re.I | re.VERBOSE
    )

    # 規則 B: 專門處理中文引用，並修正了 "等 人" 的問題
    CHI_AUTHOR_CHARS = r"[一-龥]"
    CHI_CITE_PAT = re.compile(
        rf"""
        (?P<author>{CHI_AUTHOR_CHARS}+(?:\s*等\s*人?)?) # 允許 "等" 和 "人" 之間有空格
        \s*
        [（(]
        \s*
        (?P<year>{YEAR_PAT})
        .*?
        [)）]
        """,
        re.I | re.VERBOSE
    )

    # --- 步驟 3: 分別執行，先英文後中文 ---
    
    # 執行英文引用擷取


    for m in ENG_CITE_PAT.finditer(text):
        start, end = m.span()
        if any(processed_mask[start:end]): continue
        
        author_candidate = m.group('author').strip()
        # author_match = re.search(r"([A-Za-z].*)$", author_candidate) # 確保以英文字母開頭
        # if not author_match: continue
        
        # author_str = author_match.group(1).strip(" ,、，")
        author_str = re.sub(r'^[^A-Za-z]+', '', author_candidate).strip(" ,、，")
        
        # 健全性檢查
        if len(author_str) < 2 or len(author_str.split()) > 8:
            continue

        results.append({ "raw_text": m.group(0).strip(), "author": author_str, "year": m.group('year')})
        processed_mask[start:end] = [True] * (end - start)

    # 執行中文引用擷取
    for m in CHI_CITE_PAT.finditer(text):
        start, end = m.span()
        if any(processed_mask[start:end]): continue
        
        author_str = m.group('author').strip()
        results.append({ "raw_text": m.group(0).strip(), "author": author_str, "year": m.group('year')})
        processed_mask[start:end] = [True] * (end - start)

    # --- 步驟 4: 處理括號內的引用 ---
    paren_pat = re.compile(r"\(([^()]+?)\)")
    separator = re.compile(r"[;；]")
    for m in paren_pat.finditer(text):
        start, end = m.span()
        if any(processed_mask[start:end]): continue
        content = m.group(1)
        if ',' not in content: continue
        
        parts = separator.split(content)
        temp_results = []
        is_valid = True
        for part in parts:
            match = re.fullmatch(rf"^(?P<author>.+?),\s*(?P<year>{YEAR_PAT})(?:\s*[,;，；].+)?$", part.strip(), re.I)
            if match:
                temp_results.append({"raw_text": f"({part.strip()})", "author": match.group('author').strip(), "year": match.group('year')})
            else:
                is_valid = False; break
        if is_valid:
            results.extend(temp_results)

    # --- 步驟 5: 最終去重與標準化 ---
    unique_results = []
    seen_keys = set()
    seen_raw = set()

    for res in results:
        # 標準化：將中文連接詞換成 &
        author_std = res['author'].replace(" 與 ", " & ").replace(" 和 ", " & ").replace(" 以及 ", " & ")

        backup = author_std 
        # 強力清理作者結尾的 "et al." 和 "等"
        author_clean = re.sub(r'\s*(et\s+al\.|等(?:人)?)$', '', author_std, flags=re.I).strip()
        
        if not author_clean:          # ← 新增：剪掉後變空就還原
            author_clean = backup.strip()

        author_clean = re.sub(r'^(?:以及|和|與|及)\s*', '', author_clean, flags=re.I)
        author_clean = re.sub(r'\d+', '', author_clean)   # 刪掉所有 0-9
        author_clean = re.sub(r'\s{2,}', ' ', author_clean).strip()  # 合併多餘空白

        if res['raw_text'] in seen_raw:
            continue
        seen_raw.add(res['raw_text'])

        if not author_clean:
            continue       

        if re.search(r'\d', author_clean):
            continue

        if re.fullmatch(r"[A-Za-z]\.?", author_clean):
            continue

        if re.fullmatch(r"(?:al\.?|等人?)$", author_clean, re.I):
            continue

        
        
        key = (author_clean.lower(), res['year'])
        if key not in seen_keys:
            seen_keys.add(key)
            res['author'] = author_clean
            unique_results.append(res)
            
    return sorted(unique_results, key=lambda x: (x['author'].lower(), x['year']))

# --- 主測試與匯出邏輯 ---
if __name__ == "__main__":
    pdf_path = r"D:/成功大學/學生資料/研究助理/crossref API/submission/test.pdf"
    csv_output_path = "citations_output_v19_final.csv"
    
    print("正在讀取並解析 PDF...")
    full_text = pdf_to_text(pdf_path)
    m = REF_RE.search(full_text)
    body_text = full_text[: m.start()] if m else full_text
    
    print(">>> 開始執行 V19 版「白名單連接詞」與「中英分離」策略...")
    start_time = time.time()
    all_citations = extract_citations_v19(body_text)
    end_time = time.time()
    
    print(f"✅ 擷取完成！總共找到 {len(all_citations)} 筆獨立引用，耗時 {end_time - start_time:.4f} 秒。")
    print("-" * 50)
    
    print("\n>>> 以下是所有擷取到的獨立引用 (依作者排序)：\n")
    pprint.pprint(all_citations)
    
    print("\n" + "-" * 50)
    print(f"\n>>> 正在將全部 {len(all_citations)} 筆結果匯出至 {csv_output_path} ...")
    try:
        with open(csv_output_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = ['raw_text', 'author', 'year',]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_citations)
        print(f"🎉 成功匯出 CSV 檔案！請查看 {csv_output_path}")
    except Exception as e:
        print(f"❌ 匯出 CSV 時發生錯誤: {e}")