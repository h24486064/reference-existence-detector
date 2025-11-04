
from google.genai import types
from google import genai
import json
import re
import time
from difflib import SequenceMatcher

# 全域變數存放API Key
_API_KEY = None

def set_api_key(api_key: str):
    """設定API Key"""
    global _API_KEY
    _API_KEY = api_key

def get_api_key():
    """獲取API Key"""
    return _API_KEY

def _calculate_similarity(str1: str, str2: str) -> float:
    """計算兩個字串的相似度 (0.0 ~ 1.0)"""
    if not str1 or not str2:
        return 0.0
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

def _extract_doi_from_url(url: str) -> str:
    """從 URL 中提取 DOI"""
    if not url:
        return ""
    # 匹配 DOI 格式：10.xxxx/xxxxx
    doi_match = re.search(r'10\.\d{4,9}/[^\s"<>)]+', url)
    if doi_match:
        # 移除尾部可能的標點符號
        return doi_match.group(0).rstrip('.,;)')
    return ""

def _get_similarity_threshold(title: str) -> float:
    """
    根據標題特性動態調整相似度門檻
    
    規則：
    - 短標題（<30字）：要求更高（0.90）
    - 有副標題（包含冒號）：允許較低（0.80）
    - 中文標題：稍微放寬（0.82）
    - 一般情況：0.85
    """
    if len(title) < 30:
        return 0.90
    elif ':' in title or '：' in title:
        return 0.80
    elif re.search(r'[\u4e00-\u9fff]', title):  # 包含中文
        return 0.82
    else:
        return 0.85

def find_reference_with_gemini_search(row: dict) -> dict:
    """
    使用 Gemini Search 尋找學術文獻
    
    改進版本特點：
    1. 簡化的 Prompt - 只要求搜尋，不要求判斷
    2. Python 端驗證相似度
    3. 自動提取和驗證 DOI
    4. 詳細的日誌輸出
    
    Parameters:
    -----------
    row : dict
        包含 'title', 'author', 'year' 的字典
    
    Returns:
    --------
    dict with keys: 'found', 'cr_title', 'cr_doi', 'verification_url'
        - found: 1 表示成功找到，0 表示失敗
        - cr_title: 找到的標題
        - cr_doi: DOI（如果有）
        - verification_url: 驗證用的 URL
    """
    
    if not _API_KEY:
        raise ValueError("API Key 尚未設定，請先呼叫 set_api_key()")
    
    original_title = row.get("title", "").strip()
    author_str = row.get("author", "").strip()
    year = row.get("year", "")
    
    if not original_title:
        return {"found": 0, "cr_title": "", "cr_doi": "", "verification_url": ""}

    # ============ 簡化版 Prompt（只負責搜尋） ============
    prompt = f"""You are a precise academic search assistant. Find the most authoritative URL for this research paper.

**Target Paper:**
- Title: "{original_title}"
- Author: "{author_str}"
- Year: {year}

**Search Instructions:**
1. Search for the exact title (use quotes for exact match if needed)
2. Prioritize these sources (in order):
   a) DOI links (doi.org)
   b) Google Scholar (scholar.google.com)
   c) Major publishers (sciencedirect.com, springer.com, wiley.com, nature.com, science.org)
   d) Academic databases (jstor.org, apa.org, pubmed.ncbi.nlm.nih.gov)
   e) University repositories (.edu domains)

3. Return the FIRST high-quality academic source you find

**Output (JSON only, no other text):**
{{
  "title": "Full title as shown on the webpage",
  "url": "Complete URL to the paper"
}}

**If no academic source found:**
{{
  "title": "",
  "url": ""
}}

**Important:**
- Extract the EXACT title from the webpage
- Include subtitle if present
- Choose peer-reviewed sources only
- Return ONLY valid JSON, no explanations
"""

    try:
        # 呼叫 Gemini API
        client = genai.Client(api_key=_API_KEY)
        tools = types.Tool(googleSearch=types.GoogleSearch())
        config = types.GenerateContentConfig(
            tools=[tools],
            temperature=0.0  # 設定為 0.0 以確保結果的準確性和一致性
        )

        print(f"\n  [Gemini Search] 搜尋標題: {original_title[:60]}...")
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        
        # ============ 提取 JSON 結果 ============
        text = response.text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        
        if not match:
            print(f"  [Gemini Search] ✗ 失敗：無法解析 JSON 回應")
            return {"found": 0, "cr_title": original_title, "cr_doi": "", "verification_url": ""}

        result_json = json.loads(match.group(0))
        found_title = result_json.get("title", "").strip()
        found_url = result_json.get("url", "").strip()
        
        # ============ 檢查是否找到結果 ============
        if not found_url or not found_title:
            print(f"  [Gemini Search] ✗ 未找到任何學術來源")
            return {"found": 0, "cr_title": original_title, "cr_doi": "", "verification_url": ""}
        
        print(f"  [Gemini Search] ✓ 找到 URL: {found_url}")
        print(f"  [Gemini Search]   找到標題: {found_title[:60]}...")
        
        # ============ 嘗試提取 DOI ============
        extracted_doi = _extract_doi_from_url(found_url)
        if extracted_doi:
            print(f"  [DOI 提取] ✓ 從 URL 提取到 DOI: {extracted_doi}")
            
            # 可選：用 CrossRef 驗證 DOI（需要導入 crossref_client）
            # 這裡先不實作，避免循環依賴
        
        # ============ Python 端驗證標題相似度 ============
        similarity = _calculate_similarity(original_title, found_title)
        threshold = _get_similarity_threshold(original_title)
        
        print(f"  [相似度驗證] 原始: {original_title[:50]}...")
        print(f"  [相似度驗證] 找到: {found_title[:50]}...")
        print(f"  [相似度驗證] 分數: {similarity:.3f} (門檻: {threshold:.3f})")
        
        # ============ 判定結果 ============
        if similarity >= threshold:
            print(f"  [相似度驗證] ✓ 通過！相似度 {similarity:.3f} >= {threshold:.3f}")
            return {
                "found": 1,
                "cr_title": found_title,
                "cr_doi": extracted_doi,
                "verification_url": found_url
            }
        else:
            print(f"  [相似度驗證] ✗ 失敗。相似度 {similarity:.3f} < {threshold:.3f}")
            print(f"  [相似度驗證]   標題差異過大，可能是錯誤匹配")
            return {
                "found": 0,
                "cr_title": original_title,
                "cr_doi": "",
                "verification_url": ""
            }

    except json.JSONDecodeError as e:
        print(f"  [Gemini Search] ✗ JSON 解析錯誤: {e}")
        return {"found": 0, "cr_title": original_title, "cr_doi": "", "verification_url": ""}
    except Exception as e:
        print(f"  [Gemini Search] ✗ API 呼叫錯誤: {e}")
        return {"found": 0, "cr_title": original_title, "cr_doi": "", "verification_url": ""}


def find_reference_with_multi_search(row: dict, max_attempts: int = 3) -> dict:
    """
    多重搜尋策略版本（更穩定但較慢）
    
    執行多次搜尋，使用不同的查詢策略，然後選擇最佳結果
    
    Parameters:
    -----------
    row : dict
        包含 'title', 'author', 'year' 的字典
    max_attempts : int
        最多嘗試幾種搜尋策略（預設 3）
    
    Returns:
    --------
    dict with keys: 'found', 'cr_title', 'cr_doi', 'verification_url'
    """
    
    if not _API_KEY:
        raise ValueError("API Key 尚未設定")
    
    original_title = row.get("title", "").strip()
    author_str = row.get("author", "").strip()
    year = row.get("year", "")
    
    if not original_title:
        return {"found": 0, "cr_title": "", "cr_doi": "", "verification_url": ""}

    # 定義多種搜尋策略
    search_strategies = [
        {
            "name": "精確標題匹配",
            "query": f'"{original_title}"',
        },
        {
            "name": "標題+作者",
            "query": f'{original_title} {author_str}',
        },
        {
            "name": "標題+年份+DOI",
            "query": f'{original_title} {year} doi',
        },
    ]
    
    results = []
    
    print(f"\n  [多重搜尋] 開始針對 '{original_title[:50]}...' 進行 {max_attempts} 輪搜尋")
    
    for i, strategy in enumerate(search_strategies[:max_attempts]):
        print(f"\n  [搜尋 {i+1}/{max_attempts}] 策略: {strategy['name']}")
        
        # 構建簡化的 prompt
        prompt = f"""Search for: {strategy['query']}

Find the most authoritative academic URL. Return JSON only:
{{"title": "exact title from webpage", "url": "complete URL"}}"""

        try:
            client = genai.Client(api_key=_API_KEY)
            tools = types.Tool(googleSearch=types.GoogleSearch())
            config = types.GenerateContentConfig(
                tools=[tools],
                temperature=0.0  # 設定為 0.0 以確保結果的準確性和一致性
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=config,
            )
            
            text = response.text
            match = re.search(r'\{.*\}', text, re.DOTALL)
            
            if match:
                result_json = json.loads(match.group(0))
                found_title = result_json.get("title", "").strip()
                found_url = result_json.get("url", "").strip()
                
                if found_url and found_title:
                    similarity = _calculate_similarity(original_title, found_title)
                    doi = _extract_doi_from_url(found_url)
                    
                    print(f"  [搜尋 {i+1}] ✓ 找到: {found_title[:50]}...")
                    print(f"  [搜尋 {i+1}]   相似度: {similarity:.3f}")
                    
                    results.append({
                        "url": found_url,
                        "title": found_title,
                        "doi": doi,
                        "similarity": similarity,
                        "strategy": strategy['name']
                    })
                else:
                    print(f"  [搜尋 {i+1}] ✗ 未找到有效結果")
            else:
                print(f"  [搜尋 {i+1}] ✗ 無法解析 JSON")
            
            # 避免 API 限制
            if i < max_attempts - 1:
                time.sleep(1)
            
        except Exception as e:
            print(f"  [搜尋 {i+1}] ✗ 錯誤: {e}")
            continue
    
    # ============ 選擇最佳結果 ============
    if not results:
        print(f"\n  [多重搜尋] ✗ 所有搜尋策略都失敗")
        return {"found": 0, "cr_title": original_title, "cr_doi": "", "verification_url": ""}
    
    # 按相似度排序，選擇最高的
    best = max(results, key=lambda x: x["similarity"])
    threshold = _get_similarity_threshold(original_title)
    
    print(f"\n  [多重搜尋] 最佳結果:")
    print(f"  [多重搜尋]   策略: {best['strategy']}")
    print(f"  [多重搜尋]   相似度: {best['similarity']:.3f} (門檻: {threshold:.3f})")
    print(f"  [多重搜尋]   URL: {best['url']}")
    
    if best["similarity"] >= threshold:
        print(f"  [多重搜尋] ✓ 驗證通過！")
        return {
            "found": 1,
            "cr_title": best["title"],
            "cr_doi": best["doi"],
            "verification_url": best["url"]
        }
    else:
        print(f"  [多重搜尋] ✗ 驗證失敗。最高相似度仍低於門檻")
        return {
            "found": 0,
            "cr_title": original_title,
            "cr_doi": "",
            "verification_url": ""
        }


# ============ 測試程式碼 ============
if __name__ == "__main__":
    # 測試範例
    test_cases = [
        {
            "title": "The effects of caffeine on cognitive performance",
            "author": "Smith",
            "year": 2020
        },
        {
            "title": "服務品質、關係品質與顧客忠誠度之研究",
            "author": "駱俊宏",
            "year": 2005
        }
    ]
    
    # 需要先設定 API Key
    import os
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        set_api_key(api_key)
        
        for i, test in enumerate(test_cases):
            print(f"\n{'='*70}")
            print(f"測試案例 {i+1}")
            print(f"{'='*70}")
            
            # 測試單次搜尋
            result = find_reference_with_gemini_search(test)
            print(f"\n結果: {result}")
            
            # 也可以測試多重搜尋（較慢但更穩定）
            # result = find_reference_with_multi_search(test, max_attempts=2)
    else:
        print("請設定 GEMINI_API_KEY 環境變數")
