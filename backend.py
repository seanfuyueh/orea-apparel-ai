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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = genai.Client()

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
INSTAGRAM_ACCESS_TOKEN = os.environ.get(
    "INSTAGRAM_ACCESS_TOKEN",
    "IGAANdMmdoT1pBZAFp5aFAta3FDY3ZAvWW9aSS1aaTg0U29ObGdjZAHlfV29vYjE4TG5MQVJVSWhpa2k5NjZAtR2FNTFgwdTYyNWlOYkNVcDJyeEJvVnN4b0dncEZAwUDlGSzZAoVjlzN3dZAUkJqMUxDZAHVsTC1TTG04YlUzZA2ZAjRHJQQQZDZD"
)
INSTAGRAM_ACCOUNT_ID = os.environ.get("INSTAGRAM_ACCOUNT_ID", "17841405459290595")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "1144532311567385")
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
IMGUR_CLIENT_ID = os.environ.get("IMGUR_CLIENT_ID", "546c25a59c58ad7")

def refresh_instagram_token(current_token: str) -> str:
    if not current_token:
        return current_token
    url = "https://graph.instagram.com/refresh_access_token"
    params = {"grant_type": "ig_refresh_token", "access_token": current_token}
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if "access_token" in data:
            return data["access_token"]
    except Exception as e:
        print(f"⚠️ IG 權杖續期失敗: {e}")
    return current_token

@app.on_event("startup")
async def startup_event():
    global INSTAGRAM_ACCESS_TOKEN
    INSTAGRAM_ACCESS_TOKEN = refresh_instagram_token(INSTAGRAM_ACCESS_TOKEN)

@app.post("/api/generate")
async def generate_content(data: dict):
    user_prompt = data.get("prompt", "")
    image_base64 = data.get("imageBase64", None)

    # 📌 嚴格規定 AI 針對三大平台產出深度差異化與獨立結構的黃金提示詞
    system_strategy_prompt = """
你是一位資深的韓國時尚品牌社群總監。請針對這項商品，規劃 3 個不同的穿搭情境（【情境 A】、【情境 B】、【情境 C】）。
並且在每一個情境底下，必須**完整且獨立**產出以下三種不同平台的專屬文案：

1. 【📘 FB 專屬文案】
- 語氣：專業、詳細、具備強烈的信任感與導購說服力。
- 內容結構：吸睛導購標題 + 詳細材質/版型/穿搭情境說明 + 完整導購引導。

2. 【📸 IG 專屬文案】
- 語氣：視覺導向、精煉、時尚、高級感。
- 內容結構：短而美的主打金句 + 乾淨俐落的穿搭亮點 + 5-8個熱門穿搭 Hashtags。

3. 【🧵 Threads 專屬文案】
- 語氣：極度日常、對話感強、像朋友聊天或老闆娘真實碎碎念、帶有互動感或發問。
- 內容結構：一句直擊心坎的生活化開場 + 輕鬆的商品亮點分享 + 引發粉絲留言互動的結尾。
"""

    full_prompt = f"{user_prompt}\n\n{system_strategy_prompt}"
    contents = [full_prompt]

    if image_base64:
        image_bytes = base64.b64decode(image_base64)
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

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

@app.post("/api/publish-post")
async def publish_post(request: Request, data: dict):
    try:
        publish_fb = data.get("publishFb", False)
        publish_ig = data.get("publishIg", False)
        fb_caption = data.get("fbCaption", "")
        ig_caption = data.get("igCaption", "")
        image_base64 = data.get("imageBase64", None)

        if not publish_fb and not publish_ig:
            return JSONResponse(status_code=400, content={"error": "請至少選擇一個發布平台"})

        public_image_url = None
        if image_base64:
            try:
                imgur_url = "https://api.imgur.com/3/image"
                headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
                payload = {"image": image_base64, "type": "base64"}
                img_res = requests.post(imgur_url, headers=headers, data=payload, timeout=20).json()
                if img_res.get("success"):
                    public_image_url = img_res["data"]["link"]
            except Exception:
                pass

        results = {}
        if publish_ig:
            if not public_image_url:
                results["instagram"] = {"status": "error", "message": "Instagram 必須附帶圖片"}
            else:
                try:
                    c_res = requests.post(f"https://graph.instagram.com/v22.0/{INSTAGRAM_ACCOUNT_ID}/media", data={"image_url": public_image_url, "caption": ig_caption, "access_token": INSTAGRAM_ACCESS_TOKEN}, timeout=20).json()
                    creation_id = c_res.get("id")
                    if creation_id:
                        time.sleep(3)
                        p_res = requests.post(f"https://graph.instagram.com/v22.0/{INSTAGRAM_ACCOUNT_ID}/media_publish", data={"creation_id": creation_id, "access_token": INSTAGRAM_ACCESS_TOKEN}, timeout=20).json()
                        results["instagram"] = {"status": "success", "data": p_res}
                    else:
                        results["instagram"] = {"status": "error", "message": c_res}
                except Exception as e:
                    results["instagram"] = {"status": "error", "message": str(e)}

        if publish_fb:
            try:
                page_token = FB_PAGE_ACCESS_TOKEN or INSTAGRAM_ACCESS_TOKEN
                fb_url = f"https://graph.facebook.com/v22.0/{FB_PAGE_ID}/photos" if public_image_url else f"https://graph.facebook.com/v22.0/{FB_PAGE_ID}/feed"
                fb_payload = {"url": public_image_url, "message": fb_caption, "access_token": page_token} if public_image_url else {"message": fb_caption, "access_token": page_token}
                fb_res = requests.post(fb_url, data=fb_payload, timeout=20).json()
                if "id" in fb_res:
                    results["facebook"] = {"status": "success", "data": fb_res}
                else:
                    results["facebook"] = {"status": "error", "message": fb_res}
            except Exception as e:
                results["facebook"] = {"status": "error", "message": str(e)}

        return JSONResponse(content={"status": "complete", "results": results})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/realtime-trends")
async def get_realtime_trends():
    try:
        if not APIFY_TOKEN:
            return JSONResponse(status_code=500, content={"error": "尚未設定 APIFY_TOKEN"})
        apify_url = f"https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items?token={APIFY_TOKEN}"
        response = requests.post(apify_url, json={"directUrls": ["https://www.instagram.com/partysu_official/"], "resultsLimit": 10}, timeout=60)
        items = response.json()
        ai_response = client.models.generate_content(model='gemini-3.8-flash', contents=[f"分析以下 IG 數據並產出趨勢報告：{items}"])
        return JSONResponse(content={"report": ai_response.text})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/")
@app.get("/index.html")
async def read_index():
    return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))