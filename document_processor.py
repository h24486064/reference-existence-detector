import pdfplumber, unicodedata, re

def pdf_to_text(path: str) -> str:
    with pdfplumber.open(path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    text = "\n".join(pages)
    
    # --- ① Unicode 正規化：Ṓ ➜ Ó
    text = unicodedata.normalize("NFKC", text)
    
    # --- ② 把常見智慧引號換成 ASCII 直引號
    text = text.replace("’", "'").replace("‘", "'") \
               .replace("“", '"').replace("”", '"')
    
    return text

REF_RE = re.compile(r"(References|Bibliography|參考文獻|參考來源)", re.I)

def extract_ref_block(full_txt: str) -> str:
    """
    取出〈參考文獻〉起點到全文結尾的文字。
    若找不到關鍵字就回空字串，讓上層程式自行處理。
    """
    matches = list(REF_RE.finditer(full_txt))
    if not matches:
        return ""          # 沒找到 → 交給呼叫端決定要不要報錯
    return full_txt[matches[-1].end():]