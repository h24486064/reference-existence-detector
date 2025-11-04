from google.genai import types
from google import genai
import json
import re
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
    doi_match = re.search(r'10\.\d{4,9}/[^\s"<>)]+', url)
    if doi_match:
        return doi_match.group(0).rstrip('.,;)')
    return ""

def _get_similarity_threshold(title: str) -> float:
    """根據標題特性動態調整相似度門檻"""
    if len(title) < 30:
        return 0.90  # 短標題要求更高
    elif ':' in title or '：' in title:
        return 0.80  # 有副標題允許較低
    elif re.search(r'[\u4e00-\u9fff]', title):
        return 0.82  # 中文標題稍微放寬
    else:
        return 0.85  # 一般情況

def find_reference_with_gemini_search(row: dict):
    """
    使用 Gemini Search 尋找學術文獻（智能驗證版）
    
    改進點：
    1. **提供完整資訊** - 標題、作者、年份、DOI（如果有）都提供給 AI
    2. **DOI 優先** - 如果原始資料有 DOI，優先用 DOI 搜尋
    3. **AI 智能判斷** - 讓 AI 根據標題相似度、作者匹配、年份一致性綜合判斷
    4. **明確驗證標準** - Prompt 中詳細說明如何驗證結果的準確性
    5. DOI 提取 - 自動從 URL 提取 DOI
    """
    
    if not _API_KEY:
        raise ValueError("API Key 尚未設定，請先呼叫 set_api_key()")
    
    original_title = row.get("title", "").strip()
    author_str = row.get("author", "").strip()
    year = row.get("year", "")
    original_doi = row.get("doi", "").strip()
    
    if not original_title:
        return {"found": 0, "cr_title": "", "cr_doi": "", "verification_url": ""}

    # ========== 智能驗證版 Prompt（優先使用 DOI） ==========
    # 如果有 DOI，在 Prompt 中強調優先使用
    doi_instruction = ""
    if original_doi:
        doi_instruction = f"""
**CRITICAL: This reference already has a DOI: {original_doi}**
**DOI Verification Procedure:**
1. First, search using this DOI directly (https://doi.org/{original_doi})
2. **IMPORTANT**: Check if the paper title from the DOI page matches the target title "{original_title}"
   - If titles are SIMILAR (same paper, minor formatting differences) → Use this DOI result
   - If titles are DIFFERENT (completely different paper) → The DOI is INCORRECT, discard it
3. **If DOI is incorrect or broken**: Fallback to title-based search
   - Search using the exact title: "{original_title}"
   - Find the correct paper and its proper DOI
   - DO NOT use the original incorrect DOI in your response
"""
    
    prompt = f"""You are an expert academic librarian. Find and verify the correct paper for this reference.

**Target Reference:**
- Title: "{original_title}"
- Author: "{author_str}"
- Year: {year}
{f'- DOI: {original_doi} **← USE THIS FIRST**' if original_doi else ''}

{doi_instruction}

**Search Strategy:**
1. **If DOI is provided**: 
   a. Search using the DOI FIRST (e.g., https://doi.org/{original_doi if original_doi else '10.xxxx/xxxxx'})
   b. **Verify title match**: Compare the paper title on the DOI page with target title "{original_title}"
      - If titles match (same paper, allow minor differences) → Accept this DOI
      - If titles DON'T match (different papers) → **DOI is WRONG, discard it**
   c. If DOI is wrong/broken → Use title search instead
2. **If no DOI or DOI is incorrect**: Use the EXACT title in quotes to find the most relevant academic source
3. **Cross-verify**: Check if author surname and year match
4. **Verify link validity**: CRITICAL - Ensure the URL is accessible and leads to the correct paper
   - DO NOT return 404 pages or broken links
   - DO NOT return pages that require login/subscription without providing content
   - Verify the landing page actually contains the paper information
5. **Prioritize trusted sources**: 
   - DOI links (doi.org) - HIGHEST PRIORITY (but only if title matches)
   - Google Scholar (scholar.google.com)
   - Major publishers (sciencedirect.com, springer.com, wiley.com, nature.com, science.org)
   - Academic databases (jstor.org, apa.org, pubmed.ncbi.nlm.nih.gov)
   - University repositories (.edu domains)

**Verification Criteria (ALL must be checked):**
1. **Title similarity**: The found title should be highly similar to the target title
   - Allow minor differences: punctuation, capitalization, subtitle variations
   - Reject if core content words differ significantly
2. **Author match**: At least one author surname should match (if author provided)
3. **Year consistency**: Publication year should match or be within ±1 year (if year provided)
4. **Content relevance**: The paper should be about the same research topic
5. **URL accessibility**: MANDATORY - The URL MUST be accessible and working
   - Before returning a URL, verify it actually works and loads content
   - If you cannot confirm the URL is accessible, DO NOT include it in your response
   - Return empty url if uncertain about accessibility

**Decision Rules:**
- If title similarity is HIGH (>90%) AND (author matches OR year matches) AND URL is confirmed accessible → ACCEPT
- If title similarity is MODERATE (70-90%) AND author matches AND year matches AND URL is confirmed accessible → ACCEPT
- If title similarity is LOW (<70%) OR completely different topic → REJECT
- If URL is NOT accessible or uncertain → REJECT (return empty result or omit url field)
- If unsure or no good match found → REJECT (return empty result)

**Output Format (JSON only, no other text):**
{{
  "title": "Full title as shown on the webpage",
  "url": "Complete URL to the paper (ONLY if you verified it's accessible)",
  "confidence": "high|medium|low",
  "reason": "Brief explanation of why this is the correct match"
}}

**If no confident match found OR URL is not accessible:**
{{
  "title": "",
  "url": "",
  "confidence": "none",
  "reason": "Why no match was found or why URL is not accessible"
}}

**CRITICAL RULES:**
- NEVER return a URL unless you have confirmed it is accessible and leads to the correct paper
- If you find a match but cannot verify the URL works, return empty url field
- Better to return no result than to return a broken or inaccessible URL

**Important:**
- Be CONSERVATIVE: Only return results you are confident about
- When in doubt, return empty result rather than wrong match
- **CRITICAL: If provided DOI leads to a DIFFERENT paper (title mismatch), treat it as INCORRECT and search by title instead**
- **CRITICAL: Verify all URLs are valid and accessible** - Do NOT return broken links, 404 pages, or outdated URLs that no longer point to the correct paper
- Prefer DOI links over other sources (DOI links are most stable) - **BUT ONLY if the DOI title matches the target title**
- Extract the EXACT title from the source webpage
- Test that the URL actually leads to paper content, not just a search result or error page"""

    try:
        client = genai.Client(api_key=_API_KEY)
        tools = types.Tool(googleSearch=types.GoogleSearch())
        config = types.GenerateContentConfig(tools=[tools])

        print(f"  [Gemini Search] 搜尋: {original_title[:60]}...")
        print(f"  [Gemini Search] 作者: {author_str}, 年份: {year}")
        if original_doi:
            print(f"  [Gemini Search] 原始 DOI: {original_doi} (優先使用)")
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        
        # 提取 JSON
        text = response.text
        match = re.search(r'\{.*\}', text, re.DOTALL)

        if not match:
            print(f"  [Gemini Search] ✗ 無法解析回應")
            return {"found": 0, "cr_title": original_title, "cr_doi": "", "verification_url": ""}

        result_json = json.loads(match.group(0))
        found_title = result_json.get("title", "").strip()
        found_url = result_json.get("url", "").strip()
        confidence = result_json.get("confidence", "none").lower()
        reason = result_json.get("reason", "").strip()
        
        # 檢查是否找到結果
        if not found_url or not found_title or confidence == "none":
            print(f"  [Gemini Search] ✗ 未找到匹配")
            if reason:
                print(f"  [Gemini Search] 原因: {reason}")
            return {"found": 0, "cr_title": original_title, "cr_doi": "", "verification_url": ""}
        
        # 檢查信心度（只接受 high 和 medium）
        if confidence not in ["high", "medium"]:
            print(f"  [Gemini Search] ✗ 信心度過低: {confidence}")
            if reason:
                print(f"  [Gemini Search] 原因: {reason}")
            return {"found": 0, "cr_title": original_title, "cr_doi": "", "verification_url": ""}
        
        # 提取 DOI
        extracted_doi = _extract_doi_from_url(found_url)
        
        print(f"  [Gemini Search] ✓ 找到匹配！")
        print(f"  [Gemini Search]   標題: {found_title[:60]}...")
        print(f"  [Gemini Search]   URL: {found_url}")
        print(f"  [Gemini Search]   信心度: {confidence.upper()}")
        if reason:
            print(f"  [Gemini Search]   理由: {reason}")
        if extracted_doi:
            print(f"  [Gemini Search]   DOI: {extracted_doi}")
        
        # 返回驗證過的結果
        return {
            "found": 1,
            "cr_title": found_title,
            "cr_doi": extracted_doi,
            "verification_url": found_url
        }

    except (json.JSONDecodeError, Exception) as e:
        print(f"  [Gemini Search] ✗ 錯誤: {e}")
        return {"found": 0, "cr_title": original_title, "cr_doi": "", "verification_url": ""}