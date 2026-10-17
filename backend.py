import base64
import os
import re
import time
import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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

# 建立並掛載靜態檔案資料夾，用來存放自動生成的發布圖片
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

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
# 🚀 處理前端的 AI 生成請求
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
# 📊 韓國東大門 IG 實時爆款趨勢分析
# ========================================================
@app.post("/api/realtime-trends")
async def get_realtime_trends():
    try:
        if not APIFY_TOKEN:
            return JSONResponse(status_code=500, content={"error": "尚未設定 APIFY_TOKEN"})

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

        apify_url = f"https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items?token={APIFY_TOKEN}"
        payload = {
            "directUrls": ig_urls,
            "resultsLimit": 20,
            "searchType": "user"
        }
        
        response = requests.post(apify_url, json=payload, timeout=60)
        items = response.json()
        
        if not isinstance(items, list) or len(items) == 0:
            return JSONResponse(status_code=500, content={"error": "無法取得 IG 貼文數據"})

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

            trend_summary_prompt += f"【🔥 爆款單品第 {idx} 名】\n- 貼文連結: {post_url}\n- 按讚 {likes} | 留言 {comments}\n- 內文: {caption[:150]}...\n\n"

            if display_url:
                try:
                    img_resp = requests.get(display_url, timeout=10)
                    if img_resp.status_code == 200:
                        image_part = types.Part.from_bytes(data=img_resp.content, mime_type="image/jpeg")
                        image_parts.append(image_part)
                except Exception:
                    pass

        trend_summary_prompt += "請產出一份東大門流行趨勢與爆款 TOP 10 分析報告。"
        contents = [trend_summary_prompt] + image_parts

        ai_response = client.models.generate_content(model='gemini-3.8-flash', contents=contents)
        return JSONResponse(content={"report": ai_response.text})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ========================================================
# 📱 Meta 智慧雙平台一鍵發布功能 (自動處理圖片網址)
# ========================================================
def generate_platform_captions(base_message: str):
    prompt = f"""
你是一位專業的韓國女裝電商社群總監。請根據以下原始文案，改寫為兩種風格：
【原始文案】
{base_message}

【要求】
1. **Facebook 版本**：親切溫馨、著重互動、引導私訊下單。
2. **Instagram 版本**：俐落時尚、表情符號豐富，結尾附上 5-8 個熱門 Hashtag（如 #LovelyByKorea #韓國女裝 #東大門連線）。

請嚴格以 JSON 格式回傳：
{{
  "fb_caption": "...",
  "ig_caption": "..."
}}
"""
    try:
        response = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
        import json
        text = response.text.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        data = json.loads(text)
        return data.get("fb_caption", base_message), data.get("ig_caption", base_message)
    except Exception:
        return base_message, base_message + "\n\n#LovelyByKorea #韓國女裝"

def post_to_facebook(message, image_url):
    url = f"https://graph.facebook.com/{API_VERSION}/{FB_PAGE_ID}/photos"
    payload = {"url": image_url, "caption": message, "access_token": FB_PAGE_ACCESS_TOKEN}
    return requests.post(url, data=payload).json()

def post_to_instagram(image_url, caption):
    container_url = f"https://graph.facebook.com/{API_VERSION}/{IG_USER_ID}/media"
    container_payload = {"image_url": image_url, "caption": caption, "access_token": FB_PAGE_ACCESS_TOKEN}
    res_container = requests.post(container_url, data=container_payload)
    container_result = res_container.json()
    
    if "id" not in container_result:
        return {"error": "Instagram 容器建立失敗", "details": container_result}
        
    creation_id = container_result["id"]
    time.sleep(3)
    
    publish_url = f"https://graph.facebook.com/{API_VERSION}/{IG_USER_ID}/media_publish"
    publish_payload = {"creation_id": creation_id, "access_token": FB_PAGE_ACCESS_TOKEN}
    return requests.post(publish_url, data=publish_payload).json()

@app.post("/api/publish-meta")
async def publish_to_meta(request: Request):
    """前端上傳圖片與文案，後端自動轉存為公開圖片網址並同步發佈至 FB 與 IG"""
    try:
        data = await request.json()
        base_message = data.get("message", "")
        image_base64 = data.get("imageBase64", "")
        
        if not image_base64:
            return JSONResponse(status_code=400, content={"error": "未收到圖片檔案資料"})
        
        # 自動將前端傳來的 Base64 圖片存成實體檔案在 static/ 資料夾中
        filename = f"publish_{int(time.time())}.jpg"
        file_path = os.path.join("static", filename)
        with open(file_path, "wb") as fh:
            fh.write(base64.b64decode(image_base64))
        
        # 自動組出 Render 伺服器的公開圖片網址
        base_url = str(request.base_url).rstrip("/")
        image_url = f"{base_url}/static/{filename}"
        
        # AI 智慧分流文案
        fb_msg, ig_msg = generate_platform_captions(base_message)
        
        # 發佈至 Meta
        fb_result = post_to_facebook(fb_msg, image_url)
        ig_result = post_to_instagram(image_url, ig_msg)
        
        return JSONResponse(content={
            "image_url_used": image_url,
            "fb_caption_used": fb_msg,
            "ig_caption_used": ig_msg,
            "facebook": fb_result,
            "instagram": ig_result
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ========================================================
# 🚀 靜態檔案路由
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend:app", host="0.0.0.0", port=port)