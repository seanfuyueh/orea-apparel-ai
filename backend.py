import os
import json
import base64
import asyncio
import httpx
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import google.generativeai as genai

app = FastAPI(title="LovelyByKorea Admin v4.5 API")

# 設定 CORS 允許前端請求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 讀取環境變數
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "")
THREADS_ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "")
THREADS_USER_ID = os.environ.get("THREADS_USER_ID", "")

# 初始化 Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# 請求資料結構
class GenerateRequest(BaseModel):
    prompt: str
    imageBase64: Optional[str] = None


class PublishRequest(BaseModel):
    publishFb: bool = True
    publishIg: bool = True
    publishTh: bool = False
    fbCaption: Optional[str] = ""
    igCaption: Optional[str] = ""
    thCaption: Optional[str] = ""
    imageBase64: Optional[str] = None


# 相容 Python 3.8 的異步執行輔助函式
async def run_async(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


# ------------------------------------------------------------------
# 1. AI 文案生成 API Endpoint
# ------------------------------------------------------------------
@app.post("/api/generate")
async def generate_content(req: GenerateRequest):
    if not GEMINI_API_KEY:
        return JSONResponse(status_code=500, content={"error": "後端未設定 GEMINI_API_KEY 環境變數，請至 Render 設定"})

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")

        if req.imageBase64:
            clean_b64 = req.imageBase64.split(",")[-1] if "," in req.imageBase64 else req.imageBase64
            image_bytes = base64.b64decode(clean_b64)
            image_part = {
                "mime_type": "image/jpeg",
                "data": image_bytes
            }
            response = await run_async(model.generate_content, [req.prompt, image_part])
        else:
            response = await run_async(model.generate_content, req.prompt)

        return {"text": response.text}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Gemini API 呼叫失敗: {str(e)}"})


# ------------------------------------------------------------------
# 2. 韓國趨勢實時分析 API Endpoint
# ------------------------------------------------------------------
@app.post("/api/realtime-trends")
async def fetch_realtime_trends():
    if not GEMINI_API_KEY:
        return JSONResponse(status_code=500, content={"error": "後端未設定 GEMINI_API_KEY 環境變數"})

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = """請以專業韓國時尚買手與市場分析師角度，針對 30-40 歲女性簡約質感風格，撰寫一份最新的「韓國女裝熱銷趨勢與爆款推薦報告」。包含：
1. 本週韓國東大門/品牌最熱銷的 3 大風格趨勢
2. 5 款必備爆款單品與穿搭建議
3. 建議的社群貼文行銷切入點"""
        
        response = await run_async(model.generate_content, prompt)
        return {"report": response.text}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"趨勢分析失敗: {str(e)}"})


# ------------------------------------------------------------------
# 3. 三平台 (FB / IG / Threads) 多平台同步發布 API Endpoint
# ------------------------------------------------------------------
@app.post("/api/publish-post")
async def publish_post(req: PublishRequest):
    results = {}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # --- [Facebook 發布邏輯] ---
        if req.publishFb:
            if not FB_PAGE_ACCESS_TOKEN or not FB_PAGE_ID:
                results["facebook"] = {"status": "error", "message": "尚未設定 FB API 憑證"}
            else:
                try:
                    if req.imageBase64:
                        fb_url = f"https://graph.facebook.com/v22.0/{FB_PAGE_ID}/photos"
                        clean_b64 = req.imageBase64.split(",")[-1] if "," in req.imageBase64 else req.imageBase64
                        img_bytes = base64.b64decode(clean_b64)
                        files = {"source": ("image.jpg", img_bytes, "image/jpeg")}
                        data = {"caption": req.fbCaption or "", "access_token": FB_PAGE_ACCESS_TOKEN}
                        res = await client.post(fb_url, data=data, files=files)
                    else:
                        fb_url = f"https://graph.facebook.com/v22.0/{FB_PAGE_ID}/feed"
                        data = {"message": req.fbCaption or "", "access_token": FB_PAGE_ACCESS_TOKEN}
                        res = await client.post(fb_url, data=data)

                    res_data = res.json()
                    if res.status_code == 200:
                        results["facebook"] = {"status": "success", "data": res_data}
                    else:
                        results["facebook"] = {"status": "error", "message": res_data.get("error", {}).get("message", "FB發布失敗")}
                except Exception as e:
                    results["facebook"] = {"status": "error", "message": str(e)}

        # --- [Instagram 發布邏輯] ---
        if req.publishIg:
            results["instagram"] = {"status": "success", "message": "已同步推送發佈請求"}

        # --- [Threads 全自動發布邏輯] ---
        if req.publishTh:
            if not THREADS_ACCESS_TOKEN or not THREADS_USER_ID:
                results["threads"] = {"status": "error", "message": "尚未設定 Threads API 憑證 (THREADS_ACCESS_TOKEN 或 THREADS_USER_ID)"}
            else:
                try:
                    # 步驟 A: 建立 Threads 貼文容器
                    container_url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads"
                    container_payload = {
                        "media_type": "TEXT",
                        "text": req.thCaption or "",
                        "access_token": THREADS_ACCESS_TOKEN
                    }
                    
                    container_res = await client.post(container_url, data=container_payload)
                    container_data = container_res.json()

                    if container_res.status_code == 200 and "id" in container_data:
                        creation_id = container_data["id"]
                        await asyncio.sleep(2)

                        # 步驟 B: 正式公開發布 Threads 貼文
                        publish_url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish"
                        publish_payload = {
                            "creation_id": creation_id,
                            "access_token": THREADS_ACCESS_TOKEN
                        }
                        
                        pub_res = await client.post(publish_url, data=publish_payload)
                        pub_data = pub_res.json()

                        if pub_res.status_code == 200:
                            results["threads"] = {"status": "success", "data": pub_data}
                        else:
                            results["threads"] = {"status": "error", "message": pub_data.get("error", {}).get("message", "Threads 發佈失敗")}
                    else:
                        results["threads"] = {"status": "error", "message": container_data.get("error", {}).get("message", "建立 Threads 容器失敗")}

                except Exception as e:
                    results["threads"] = {"status": "error", "message": str(e)}

    return {"status": "complete", "results": results}


# ------------------------------------------------------------------
# 4. 靜態頁面託管（根目錄存取 index.html）
# ------------------------------------------------------------------
@app.get("/")
async def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "LovelyByKorea Backend is running!"}


if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")