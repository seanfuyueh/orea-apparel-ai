import base64
import os
import re
import time
import uuid
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

# 初始化 Google Gemini 客戶端
client = genai.Client()

# 從 Render 環境變數抓取 APIFY_TOKEN 與 Instagram 存取設定
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
INSTAGRAM_ACCESS_TOKEN = os.environ.get(
    "INSTAGRAM_ACCESS_TOKEN",
    "IGAANdMmdoT1pBZAFp5aFAta3FDY3ZAvWW9aSS1aaTg0U29ObGdjZAHlfV29vYjE4TG5MQVJVSWhpa2k5NjZAtR2FNTFgwdTYyNWlOYkNVcDJyeEJvVnN4b0dncEZAwUDlGSzZAoVjlzN3dZAUkJqMUxDZAHVsTC1TTG04YlUzZA2ZAjRHJQQQZDZD"
)
INSTAGRAM_ACCOUNT_ID = os.environ.get("INSTAGRAM_ACCOUNT_ID", "17841405459290595")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "1144532311567385")

# 建立並掛載圖片公開暫存目錄 (A 方案：自動產生 Meta 可存取的公開圖片網址)
TEMP_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "temp_uploads")
os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)
app.mount("/temp_uploads", StaticFiles(directory=TEMP_UPLOAD_DIR), name="temp_uploads")

# ========================================================
# 🔄 Instagram 權杖自動續期機制 (方案 A：自動延長 60 天)
# ========================================================
def refresh_instagram_token(current_token: str) -> str:
    """自動呼叫 Meta API 將 60 天長效權杖重新延長 60 天"""
    if not current_token:
        return current_token
    
    url = "https://graph.instagram.com/refresh_access_token"
    params = {
        "grant_type": "ig_refresh_token",
        "access_token": current_token
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if "access_token" in data:
            print("✅ [Instagram API] 成功自動延長 IG 權杖期限（重新倒數 60 天）")
            return data["access_token"]
        else:
            print(f"ℹ️ [Instagram API] 權杖續期回應: {data}")
    except Exception as e:
        print(f"⚠️ [Instagram API] 權杖自動續期失敗，繼續使用現有權杖: {e}")
    return current_token

@app.on_event("startup")
async def startup_event():
    """伺服器啟動時自動執行權杖續期"""
    global INSTAGRAM_ACCESS_TOKEN
    INSTAGRAM_ACCESS_TOKEN = refresh_instagram_token(INSTAGRAM_ACCESS_TOKEN)

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
# 📱 雙平台（FB / IG）一鍵貼文 API 接口
# ========================================================
@app.post("/api/publish-post")
async def publish_post(request: Request, data: dict):
    try:
        publish_fb = data.get("publishFb", False)
        publish_ig = data.get("publishIg", False)
        fb_caption = data.get("fbCaption", "")
        ig_caption = data.get("igCaption", "")
        image_base64 = data.get("imageBase64", None)

        if not publish_fb and not publish_ig:
            return JSONResponse(status_code=400, content={"error": "請至少選擇一個發布平台 (FB 或 IG)"})

        # 1. 處理圖片暫存並取得公網 URL
        public_image_url = None
        temp_file_path = None
        if image_base64:
            img_filename = f"{uuid.uuid4().hex}.jpg"
            temp_file_path = os.path.join(TEMP_UPLOAD_DIR, img_filename)
            img_data = base64.b64decode(image_base64)
            with open(temp_file_path, "wb") as f:
                f.write(img_data)
            
            # 組成可供 Meta Graph API 下載的公開 URL
            base_url = str(request.base_url).rstrip("/")
            public_image_url = f"{base_url}/temp_uploads/{img_filename}"

        results = {}

        # 2. 發布至 Instagram
        if publish_ig:
            if not public_image_url:
                results["instagram"] = {"status": "error", "message": "Instagram 必須附帶圖片才能發布貼文"}
            else:
                try:
                    # 建立媒體容器
                    container_url = f"https://graph.instagram.com/v22.0/{INSTAGRAM_ACCOUNT_ID}/media"
                    container_payload = {
                        "image_url": public_image_url,
                        "caption": ig_caption,
                        "access_token": INSTAGRAM_ACCESS_TOKEN
                    }
                    c_res = requests.post(container_url, data=container_payload, timeout=20).json()
                    creation_id = c_res.get("id")

                    if creation_id:
                        # 發佈媒體
                        pub_url = f"https://graph.instagram.com/v22.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
                        pub_payload = {
                            "creation_id": creation_id,
                            "access_token": INSTAGRAM_ACCESS_TOKEN
                        }
                        p_res = requests.post(pub_url, data=pub_payload, timeout=20).json()
                        results["instagram"] = {"status": "success", "data": p_res}
                    else:
                        results["instagram"] = {"status": "error", "message": c_res}
                except Exception as ig_err:
                    results["instagram"] = {"status": "error", "message": str(ig_err)}

        # 3. 發布至 Facebook 粉絲專頁
        if publish_fb:
            try:
                if public_image_url:
                    fb_url = f"https://graph.facebook.com/v22.0/{FB_PAGE_ID}/photos"
                    fb_payload = {
                        "url": public_image_url,
                        "message": fb_caption,
                        "access_token": INSTAGRAM_ACCESS_TOKEN
                    }
                else:
                    fb_url = f"https://graph.facebook.com/v22.0/{FB_PAGE_ID}/feed"
                    fb_payload = {
                        "message": fb_caption,
                        "access_token": INSTAGRAM_ACCESS_TOKEN
                    }
                fb_res = requests.post(fb_url, data=fb_payload, timeout=20).json()
                results["facebook"] = {"status": "success", "data": fb_res}
            except Exception as fb_err:
                results["facebook"] = {"status": "error", "message": str(fb_err)}

        # 4. 發布完畢後自動清理暫存圖檔
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass

        return JSONResponse(content={"status": "complete", "results": results})

    except Exception as e:
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
請對這 10 款爆款單品依次進行單獨分析。**每一款單品講解完畢後，請務必在其分析文字的正下方，直接貼上該單品的 IG 貼文連結按鈕（格式為：`[📸 查看 Instagram 貼文](該篇貼文的真實連結)`）！絕不要統一放在報告最後！**

請嚴格按照以下結構格式撰寫：

### 壹、本週東大門 IG 爆款單品 TOP 10 逐一解析

【🔥 爆款 No.1：(給予精準單品名稱)】
- **互動數據**：(列出按讚數與留言數)
- **視覺與設計亮點**：(分析顏色、面料、剪裁與搭配方式)
- **爆款原因分析**：(為什麼這款能在 IG 上引發話題與高觸及)

[📸 查看 Instagram 貼文](第1篇貼文的真實連結)

---

(請依此類推完整的列出 No.2 至 No.10，每款下方都必須帶有其專屬連結按鈕)

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
        print(f"Realtime trend error: {e}")
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