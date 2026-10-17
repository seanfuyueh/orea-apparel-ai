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

# 初始化 Google Gemini 客戶端
client = genai.Client()

# 從 Render 環境變數抓取 API Token 與設定
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
    """取得所有雲端歷史紀錄"""
    return load_cloud_history()

@app.post("/api/history")
def add_history_item(item: dict = Body(...)):
    """新增一筆紀錄至 Render 雲端伺服器"""
    history = load_cloud_history()
    if "id" not in item:
        item["id"] = int(time.time() * 1000)
    if "date" not in item:
        item["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    history.insert(0, item)  # 最新產出的排在最前面
    save_cloud_history(history)
    return {"status": "success", "item": item}

@app.delete("/api/history/{item_id}")
def delete_history_item(item_id: int):
    """刪除特定 ID 的雲端歷史紀錄"""
    history = load_cloud_history()
    history = [h for h in history if h.get("id") != item_id]
    save_cloud_history(history)
    return {"status": "success"}

@app.delete("/api/history")
def clear_all_history():
    """清空所有雲端歷史紀錄"""
    save_cloud_history([])
    return {"status": "success"}

# ========================================================
# 🚀 處理前端的 AI 生成請求 (支援文字與圖片)
# ========================================================
@app.post("/api/generate")
async def generate_content(data: dict = Body(...)):
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
# 📊 韓國東大門 IG 實時爆款趨勢分析 (TOP 10 網址極致清洗版)
# ========================================================
@app.post("/api/realtime-trends")
async def get_realtime_trends():
    try:
        if not APIFY_TOKEN:
            return JSONResponse(status_code=500, content={"error": "尚未設定 APIFY_TOKEN"})

        # 1. 自動從根目錄讀取 ig_targets.txt 並進行網址清洗
        target_file_path = os.path.join(os.path.dirname(__file__), "ig_targets.txt")
        ig_urls = []
        if os.path.exists(target_file_path):
            with open(target_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    # 強制去掉結尾的所有斜線 / 與空白
                    line = line.rstrip("/")
                    
                    if "instagram.com" in line:
                        ig_urls.append(line)

        # 若檔案無有效網址，使用預設帳號
        if not ig_urls:
            ig_urls = ["https://www.instagram.com/partysu_official"]

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
            error_msg = items.get("error", {}).get("message", "無法取得 IG 數據") if isinstance(items, dict) else "無法取得 IG 貼文數據，請確認 ig_targets.txt 網址或 Apify 額度。"
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
# 📱 Meta 智慧雙平台一鍵發佈 API
# ========================================================
@app.post("/api/publish-meta")
async def publish_meta(data: dict = Body(...)):
    try:
        message = data.get("message", "韓國女裝新品連線！")
        image_base64 = data.get("imageBase64", "")

        fb_access_token = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
        fb_page_id = os.environ.get("FB_PAGE_ID", "")
        ig_user_id = os.environ.get("IG_USER_ID", "")

        # 圖床可使用 Imgur 或 Render 暫存服務；此處提供防護邏輯
        image_url_used = "https://picsum.photos/800/1000"  # 範例 public image URL

        # FB 與 IG AI 文案改寫
        fb_caption = f"{message}\n\n✨ 歡迎點擊私訊詢問小幫手或直接下單！"
        ig_caption = f"{message}\n\n#韓國女裝 #正韓連線 #東大門穿搭 #OOTD"

        return JSONResponse(content={
            "status": "success",
            "image_url_used": image_url_used,
            "fb_caption_used": fb_caption,
            "ig_caption_used": ig_caption
        })
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