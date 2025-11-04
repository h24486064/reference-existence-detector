import re, unicodedata
from google.genai import types
import json
import re
from google.genai import types
from google import genai

# 全域變數存放API Key
_API_KEY = None
_GEMINI_MODEL = "gemini-2.5-flash"

def set_api_key(api_key: str):
    """設定API Key"""
    global _API_KEY
    _API_KEY = api_key

def get_api_key():
    """獲取API Key"""
    return _API_KEY

def parse_references_with_gemini(ref_text: str):
    """
    使用 Gemini API 將參考文獻純文字區塊解析為結構化資料。

    Args:
        ref_text: 包含所有參考文獻的單一字串。

    Returns:
        一個包含解析後文獻字典的 list，以及解析失敗的原始字串 list。
    """
    
    if not _API_KEY:
        raise ValueError("API Key 尚未設定，請先呼叫 set_api_key()")

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
        client = genai.Client(api_key = _API_KEY)
        response = client.models.generate_content(
            model= _GEMINI_MODEL,
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

    except json.JSONDecodeError as e:
        error_msg = f"Gemini API 回應的 JSON 格式錯誤: {e}\n回應內容: {response.text if 'response' in locals() else '無回應'}"
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Gemini API 呼叫失敗: {type(e).__name__}: {str(e)}"
        raise RuntimeError(error_msg)

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