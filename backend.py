import base64
import json
import os
import time
from datetime import datetime
import requests
from fastapi import FastAPI, Body
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

client = genai.Client()

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
HISTORY_FILE = "history.json"

# ========================================================
# 📂 雲端歷史紀錄 (Render 持久化 JSON 儲存)
# ========================================================
def load_cloud_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"歷史紀錄讀取失敗: {e}")
            return []
    return []

def save_cloud_history(history_data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"歷史紀錄儲存失敗: {e}")

@app.get("/api/history")
def get_history():
    return load_cloud_history()

@app.post("/api/history")
def add_history_item(item: dict = Body(...)):
    history = load_cloud_history()
    if "id" not in item:
        item["id"] = int(time.time() * 1000)
    if "date" not in item:
        item["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history.insert(0, item)
    save_cloud_history(history)
    return {"status": "success", "item": item}

@app.delete("/api/history/{item_id}")
def delete_history_item(item_id: int):
    history = load_cloud_history()
    history = [h for h in history if h.get("id") != item_id]
    save_cloud_history(history)
    return {"status": "success"}

@app.delete("/api/history")
def clear_all_history():
    save_cloud_history([])
    return {"status": "success"}

# ========================================================
# 🚀 處理前端的 AI 生成請求 (支援文字與圖片 + 3次重試)
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

        apify_url = f"https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items?token={APIFY_TOKEN}"
        payload = {
            "directUrls": ["https://www.instagram.com/partysu_official/"],
            "resultsLimit": 15,
            "searchType": "user"
        }
        
        response = requests.post(apify_url, json=payload, timeout=60)
        items = response.json()
        
        if not isinstance(items, list) or len(items) == 0:
            return JSONResponse(status_code=500, content={"error": "無法取得 IG 貼文數據，請確認 Apify 額度或帳號狀態。"})

        sorted_posts = sorted(
            items, 
            key=lambda x: (x.get('likesCount', 0) or 0) + (x.get('commentsCount', 0) or 0) * 2, 
            reverse=True
        )[:3]

        trend_summary_prompt = "你是一位韓國時尚流行趨勢分析師。以下是從韓國熱門 IG 帳號 @partysu_official 實時抓取到的本週最高流量貼文數據與圖片：\n\n"
        
        image_parts = []
        for idx, post in enumerate(sorted_posts, 1):
            likes = post.get('likesCount', 0)
            comments = post.get('commentsCount', 0)
            caption = post.get('caption', '無內文')
            post_url = post.get('url', '')
            display_url = post.get('displayUrl', '')

            trend_summary_prompt += f"【🔥 爆款第 {idx} 名】\n"
            trend_summary_prompt += f"- 貼文連結: {post_url}\n"
            trend_summary_prompt += f"- 按讚數: {likes} | 留言數: {comments}\n"
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
請根據上述真實高流量貼文與圖片，產出一份「東大門流行趨勢與爆款分析報告」：
1. 視覺風格分析：總結這幾款爆款商品的共通設計亮點（顏色、面料、剪裁）。
2. 爆款原因分析：為什麼這幾篇貼文在 IG 上能獲得高按讚數與高互動？
3. 明確列出這 3 篇爆款貼文的真實 IG 連結與按讚數供用戶查驗。
"""

        contents = [trend_summary_prompt] + image_parts

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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend:app", host="0.0.0.0", port=port)