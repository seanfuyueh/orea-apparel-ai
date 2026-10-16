import base64
import os
import time
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from google import genai
from google.genai import types

app = FastAPI()

# 跨來源資源共享 (CORS) 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化 Google Gemini 客戶端 (自動抓取 GEMINI_API_KEY)
client = genai.Client()

# 從 Render 環境變數抓取 APIFY_TOKEN
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")

# ========================================================
# 🚀 處理前端的 AI 生成請求 (支援文字與圖片)
# ========================================================
@app.post("/api/generate")
async def generate_content(data: dict):
    prompt = data.get("prompt", "")
    image_base64 = data.get("imageBase64", None)

    contents = [prompt]
    if image_base64:
        image_bytes = base64.b64decode(image_base64)
        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type="image/jpeg"
        )
        contents.append(image_part)

    # 自動重試機制 (最多重試 3 次)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=contents
            )
            return JSONResponse(content={"candidates": [{"content": {"parts": [{"text": response.text}]}}]})
        except Exception as e:
            if ("503" in str(e) or "UNAVAILABLE" in str(e)) and attempt < max_retries - 1:
                time.sleep(2)
                continue
            return JSONResponse(status_code=500, content={"error": str(e)})

# ========================================================
# 📊 韓國東大門 IG 實時爆款趨勢分析 (TOP 10 產出版)
# ========================================================
@app.post("/api/realtime-trends")
async def get_realtime_trends():
    try:
        if not APIFY_TOKEN:
            return JSONResponse(status_code=500, content={"error": "尚未設定 APIFY_TOKEN"})

        # 1. 自動從根目錄讀取 ig_targets.txt 中的網址清單
        target_file_path = os.path.join(os.path.dirname(__file__), "ig_targets.txt")
        ig_urls = []
        if os.path.exists(target_file_path):
            with open(target_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        ig_urls.append(line)

        # 若檔案不存在或內容空白，則使用預設帳號
        if not ig_urls:
            ig_urls = ["https://www.instagram.com/partysu_official/"]

        # 2. 呼叫 Apify Instagram Scraper (提高至 30 篇以確保數據庫充足)
        apify_url = f"https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items?token={APIFY_TOKEN}"
        payload = {
            "directUrls": ig_urls,
            "resultsLimit": 30,
            "searchType": "user"
        }
        
        response = requests.post(apify_url, json=payload, timeout=60)
        items = response.json()
        
        if not isinstance(items, list) or len(items) == 0:
            return JSONResponse(status_code=500, content={"error": "無法取得 IG 貼文數據，請確認 ig_targets.txt 網址或 Apify 狀態。"})

        # 3. 依照 (愛心數 + 留言數*2) 排序，挑選出流量最高的 TOP 10 爆款貼文
        sorted_posts = sorted(
            items, 
            key=lambda x: (x.get('likesCount', 0) or 0) + (x.get('commentsCount', 0) or 0) * 2, 
            reverse=True
        )[:10]

        # 4. 組成 Prompt 與爆款圖片供 Gemini 分析
        trend_summary_prompt = "你是一位韓國時尚流行趨勢分析師。以下是實時抓取到的最新熱門 IG 爆款貼文數據與圖片：\n\n"
        
        image_parts = []
        for idx, post in enumerate(sorted_posts, 1):
            likes = post.get('likesCount', 0)
            comments = post.get('commentsCount', 0)
            caption = post.get('caption', '無內文')
            post_url = post.get('url', '')
            display_url = post.get('displayUrl', '')

            trend_summary_prompt += f"【🔥 爆款單品第 {idx} 名】\n"
            trend_summary_prompt += f"- 貼文真實連結: {post_url}\n"
            trend_summary_prompt += f"- 互動數據: 按讚 {likes} | 留言 {comments}\n"
            trend_summary_prompt += f"- 貼文內文: {caption[:150]}...\n\n"

            if display_url:
                try:
                    img_resp = requests.get(display_url, timeout=10)
                    if img_resp.status_code == 200:
                        image_part = types.Part.from_bytes(
                            data=img_resp.content,
                            mime_type="image/jpeg"
                        )
                        image_parts.append(image_part)
                except Exception as img_err:
                    print(f"圖片下載失敗: {img_err}")

        trend_summary_prompt += """
請根據上述數據與圖片，產出一份結構清晰的「東大門流行趨勢與爆款 TOP 10 分析報告」。

【⚠️ 格式排版極重要要求】：
請對這 10 款爆款單品（No.1 至 No.10）依次進行單獨分析。**每一款單品講解完畢後，請務必在其分析文字的正下方，直接貼上該單品的 IG 貼文連結按鈕（格式為：`[📸 查看 Instagram 貼文](該篇貼文的真實連結)`）！絕不要統一放在報告最後！**

請嚴格按照以下結構格式撰寫：

### 壹、本週東大門 IG 爆款單品 TOP 10 逐一解析

【🔥 爆款 No.1：(給予精準單品名稱)】
- **互動數據**：(列出按讚數與留言數)
- **視覺與設計亮點**：(分析顏色、面料、剪裁與搭配方式)
- **爆款原因分析**：(為什麼這款能在 IG 上引發話題與高觸及)

[📸 查看 Instagram 貼文](第1篇貼文的真實連結)

---

【🔥 爆款 No.2：(給予精準單品名稱)】
- **互動數據**：(列出按讚數與留言數)
- **視覺與設計亮點**：(分析顏色、面料、剪裁與搭配方式)
- **爆款原因分析**：(為什麼這款能在 IG 上引發話題與高觸及)

[📸 查看 Instagram 貼文](第2篇貼文的真實連結)

---

(請依此類推完整的列出 No.3、No.4、No.5、No.6、No.7、No.8、No.9 至 No.10，每款下方都必須帶有其專屬連結按鈕)

---

### 貳、東大門當季流行趨勢總結與採購建議
1. **整體視覺風格趨勢**：(總結這 10 款爆款的共通點與韓國女性最愛的風格)
2. **賣家選品與行銷建議**：(提供給台灣女裝賣家的採購與粉專/IG 行銷切入點)
"""

        contents = [trend_summary_prompt] + image_parts

        # 5. 呼叫 Gemini 3.8-Flash (含 503 重試)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                ai_response = client.models.generate_content(
                    model='gemini-3.8-flash',
                    contents=contents
                )
                return JSONResponse(content={"report": ai_response.text})
            except Exception as e:
                if ("503" in str(e) or "UNAVAILABLE" in str(e)) and attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return JSONResponse(status_code=500, content={"error": str(e)})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ========================================================
# 🚀 精準檔案路由
# ========================================================
@app.get("/")
@app.get("/index.html")
async def read_index():
    return FileResponse("index.html")

@app.get("/logo.png")
async def read_logo():
    return FileResponse("logo.png", media_type="image/png")

@app.get("/manifest.json")
async def read_manifest():
    return FileResponse("manifest.json", media_type="application/json")

@app.get("/sw.js")
async def read_sw():
    return FileResponse("sw.js", media_type="application/javascript")

# ========================================================
# 啟動設定
# ========================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend:app", host="0.0.0.0", port=port)