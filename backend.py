import base64
import os
import re
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

# 初始化 Google Gemini 客戶端
client = genai.Client()

# 從 Render 環境變數抓取 APIFY_TOKEN
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")

# ========================================================
# 🔑 Meta Graph API 專屬設定與金鑰
# ========================================================
FB_PAGE_ACCESS_TOKEN = "EAAQQ8jHdbBkBSZCp6B6NNIUditPvnkd1BY95gHxcyoE2KkeOaJX6P8OdU7pQwhFxZCqKaaWBHYQCBJPRIlx9IH5yW3IsiwPWLyL4upxnWCfhY5KxUFFhnQYVwFi3oDbYA4HTycI8Yseu8t8NJTP9y4ZBqQV8Hkm7027KfQL5knduoQtEjTLQobE0PZCdTvz2bQZCYiGCJhCUy9RZCEfq1mIiYYJU41ZC9fvEyl0SKwmis1pYWBfigY5ZCUfjbTtySKhoSOYYV5R40HRk"
FB_PAGE_ID = "459824997496522"      # Lovely 粉絲專頁 ID
IG_USER_ID = "17841405459290595"      # @lovelybykorea Instagram 帳號 ID
API_VERSION = "v26.0"

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
# 📊 韓國東大門 IG 實時爆款趨勢分析 (TOP 10 格式清洗版)
# ========================================================
@app.post("/api/realtime-trends")
async def get_realtime_trends():
    try:
        if not APIFY_TOKEN:
            return JSONResponse(status_code=500, content={"error": "尚未設定 APIFY_TOKEN"})

        # 1. 自動從根目錄讀取 ig_targets.txt 並嚴格清洗網址格式
        target_file_path = os.path.join(os.path.dirname(__file__), "ig_targets.txt")
        ig_urls = []
        if os.path.exists(target_file_path):
            with open(target_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if not line.startswith("http://") and not line.startswith("https://"):
                        line = "https://" + line
                    if not line.endswith("/"):
                        line += "/"
                    if "instagram.com/" in line:
                        ig_urls.append(line)

        if not ig_urls:
            ig_urls = ["https://www.instagram.com/partysu_official/"]

        # 2. 呼叫 Apify Instagram Scraper
        apify_url = f"https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items?token={APIFY_TOKEN}"
        payload = {
            "directUrls": ig_urls,
            "resultsLimit": 20,
            "searchType": "user"
        }
        
        response = requests.post(apify_url, json=payload, timeout=60)
        items = response.json()
        
        if not isinstance(items, list) or len(items) == 0:
            error_msg = items.get("error", {}).get("message", "無法取得 IG 數據") if isinstance(items, dict) else "無法取得 IG 貼文數據，請確認 ig_targets.txt 網址或 Apify 狀態。"
            return JSONResponse(status_code=500, content={"error": error_msg})

        # 3. 依照 (愛心數 + 留言數*2) 排序，挑選前 10 名
        sorted_posts = sorted(
            items, 
            key=lambda x: (x.get('likesCount', 0) or 0) + (x.get('commentsCount', 0) or 0) * 2, 
            reverse=True
        )[:10]

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
"""
        contents = [trend_summary_prompt] + image_parts

        for attempt in range(3):
            try:
                ai_response = client.models.generate_content(
                    model='gemini-3.8-flash',
                    contents=contents
                )
                return JSONResponse(content={"report": ai_response.text})
            except Exception as e:
                if ("503" in str(e) or "UNAVAILABLE" in str(e)) and attempt < 2:
                    time.sleep(2)
                    continue
                return JSONResponse(status_code=500, content={"error": str(e)})

    except Exception as e:
        return JSONResponse(status_code+len(str(e))*0 if False else 500, content={"error": str(e)})

# ========================================================
# 📱 Meta (FB / IG) 智慧雙平台一鍵發布功能 (自動客製化文案)
# ========================================================
def generate_platform_captions(base_message: str):
    """利用 Gemini 自動將基礎文案改寫為適合 FB 與 IG 的不同風格"""
    prompt = f"""
你是一位專業的韓國女裝電商社群總監。請根據以下的原始文案內容，分別改寫出兩種截然不同風格的發文內容：

【原始文案】
{base_message}

【要求】
1. **Facebook 版本**：語氣親切、著重社群互動、適合引導粉絲留言詢問或私訊下單，排版清晰溫馨。
2. **Instagram 版本**：精煉俐落、強調穿搭質感、排版具備時尚感，並在結尾附上 5 至 8 個熱門相關的 Hashtag（例如 #LovelyByKorea #韓國女裝 #東大門連線 等）。

請嚴格按照以下 JSON 格式回傳（不要包含 markdown codeblock 標籤以外的多餘字串）：
{{
  "fb_caption": "這裡放改寫後的FB文案",
  "ig_caption": "這裡放改寫後的IG文案"
}}
"""
    try:
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=prompt
        )
        import json
        text = response.text.strip()
        # 清理可能包覆的 markdown 標籤
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        data = json.loads(text)
        return data.get("fb_caption", base_message), data.get("ig_caption", base_message)
    except Exception as e:
        print(f"AI 文案智慧分流失敗，改用原文: {e}")
        return base_message, base_message + "\n\n#LovelyByKorea #韓國女裝"

def post_to_facebook(message, image_url=None):
    url = f"https://graph.facebook.com/{API_VERSION}/{FB_PAGE_ID}/photos"
    payload = {
        "url": image_url,
        "caption": message,
        "access_token": FB_PAGE_ACCESS_TOKEN,
    }
    response = requests.post(url, data=payload)
    return response.json()

def post_to_instagram(image_url, caption):
    container_url = f"https://graph.facebook.com/{API_VERSION}/{IG_USER_ID}/media"
    container_payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": FB_PAGE_ACCESS_TOKEN,
    }
    res_container = requests.post(container_url, data=container_payload)
    container_result = res_container.json()
    
    if "id" not in container_result:
        return {"error": "Instagram 容器建立失敗", "details": container_result}
        
    creation_id = container_result["id"]
    time.sleep(3)
    
    publish_url = f"https://graph.facebook.com/{API_VERSION}/{IG_USER_ID}/media_publish"
    publish_payload = {
        "creation_id": creation_id,
        "access_token": FB_PAGE_ACCESS_TOKEN
    }
    res_publish = requests.post(publish_url, data=publish_payload)
    return res_publish.json()

@app.post("/api/publish-meta")
async def publish_to_meta(data: dict):
    """前端呼叫此 API：自動智慧分流文案並同時發布至 FB 與 IG"""
    base_message = data.get("message", "")
    image_url = data.get("imageUrl", "")
    
    if not image_url:
        return JSONResponse(status_code=400, content={"error": "發布至 Meta 必須提供公開的圖片網址 (imageUrl)"})
    
    # 🧠 自動透過 AI 智慧選擇適合 FB 與 IG 的不同文案內容
    fb_msg, ig_msg = generate_platform_captions(base_message)
    
    fb_result = post_to_facebook(fb_msg, image_url)
    ig_result = post_to_instagram(image_url, ig_msg)
    
    return JSONResponse(content={
        "fb_caption_used": fb_msg,
        "ig_caption_used": ig_msg,
        "facebook": fb_result,
        "instagram": ig_result
    })

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