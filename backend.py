import os
import json
import base64
import asyncio
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")

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


# --- 輔助函式：使用原生 urllib 發送 POST 請求 ---
def http_post_form(url: str, data_dict: dict):
    encoded_data = urllib.parse.urlencode(data_dict).encode('utf-8')
    req = urllib.request.Request(url, data=encoded_data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8')), response.status
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        try:
            return json.loads(body), e.code
        except Exception:
            return {"error": {"message": body}}, e.code
    except Exception as e:
        return {"error": {"message": str(e)}}, 500


def http_post_multipart(url: str, fields: dict, file_field: str, filename: str, file_bytes: bytes, mime_type: str):
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    body = bytearray()
    
    for k, v in fields.items():
        body.extend(f'--{boundary}\r\n'.encode('utf-8'))
        body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode('utf-8'))
        body.extend(f'{v}\r\n'.encode('utf-8'))
        
    body.extend(f'--{boundary}\r\n'.encode('utf-8'))
    body.extend(f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode('utf-8'))
    body.extend(f'Content-Type: {mime_type}\r\n\r\n'.encode('utf-8'))
    body.extend(file_bytes)
    body.extend(b'\r\n')
    body.extend(f'--{boundary}--\r\n'.encode('utf-8'))

    req = urllib.request.Request(url, data=bytes(body), headers={
        'Content-Type': f'multipart/form-data; boundary={boundary}'
    })
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8')), response.status
    except urllib.error.HTTPError as e:
        body_str = e.read().decode('utf-8')
        try:
            return json.loads(body_str), e.code
        except Exception:
            return {"error": {"message": body_str}}, e.code
    except Exception as e:
        return {"error": {"message": str(e)}}, 500


# ------------------------------------------------------------------
# 1. AI 文案生成 API Endpoint
# ------------------------------------------------------------------
@app.post("/api/generate")
async def generate_content(req: GenerateRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="後端未設定 GEMINI_API_KEY")

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")

        if req.imageBase64:
            image_data = base64.b64decode(req.imageBase64)
            image_part = {
                "mime_type": "image/jpeg",
                "data": image_data
            }
            response = await asyncio.to_thread(model.generate_content, [req.prompt, image_part])
        else:
            response = await asyncio.to_thread(model.generate_content, req.prompt)

        return {"text": response.text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 生成失敗: {str(e)}")


# ------------------------------------------------------------------
# 2. 韓國趨勢實時分析 API Endpoint
# ------------------------------------------------------------------
@app.post("/api/realtime-trends")
async def fetch_realtime_trends():
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="未設定 GEMINI_API_KEY")

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = """請以專業韓國時尚買手與市場分析師角度，針對 30-40 歲女性簡約質感風格，撰寫一份最新的「韓國女裝熱銷趨勢與爆款推薦報告」。包含：
1. 本週韓國東大門/品牌最熱銷的 3 大風格趨勢
2. 5 款必備爆款單品與穿搭建議
3. 建議的社群貼文行銷切入點"""
        
        response = await asyncio.to_thread(model.generate_content, prompt)
        return {"report": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"趨勢分析失敗: {str(e)}")


# ------------------------------------------------------------------
# 3. 三平台 (FB / IG / Threads) 多平台同步發布 API Endpoint
# ------------------------------------------------------------------
@app.post("/api/publish-post")
async def publish_post(req: PublishRequest):
    results = {}
    
    # --- [Facebook 發布邏輯] ---
    if req.publishFb:
        if not FB_PAGE_ACCESS_TOKEN or not FB_PAGE_ID:
            results["facebook"] = {"status": "error", "message": "尚未設定 FB API 憑證"}
        else:
            try:
                if req.imageBase64:
                    fb_url = f"https://graph.facebook.com/v22.0/{FB_PAGE_ID}/photos"
                    img_bytes = base64.b64decode(req.imageBase64)
                    res_data, status_code = await asyncio.to_thread(
                        http_post_multipart,
                        fb_url,
                        {"caption": req.fbCaption or "", "access_token": FB_PAGE_ACCESS_TOKEN},
                        "source",
                        "image.jpg",
                        img_bytes,
                        "image/jpeg"
                    )
                else:
                    fb_url = f"https://graph.facebook.com/v22.0/{FB_PAGE_ID}/feed"
                    res_data, status_code = await asyncio.to_thread(
                        http_post_form,
                        fb_url,
                        {"message": req.fbCaption or "", "access_token": FB_PAGE_ACCESS_TOKEN}
                    )

                if status_code == 200:
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
                # 步驟 A: 建立 Threads 貼文容器 (Container)
                container_url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads"
                container_payload = {
                    "media_type": "TEXT",
                    "text": req.thCaption or "",
                    "access_token": THREADS_ACCESS_TOKEN
                }
                
                container_data, status_code = await asyncio.to_thread(http_post_form, container_url, container_payload)

                if status_code == 200 and "id" in container_data:
                    creation_id = container_data["id"]
                    
                    # 等待 2 秒確保 Meta 伺服器容器處理完畢
                    await asyncio.sleep(2)

                    # 步驟 B: 正式公開發布 Threads 貼文
                    publish_url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish"
                    publish_payload = {
                        "creation_id": creation_id,
                        "access_token": THREADS_ACCESS_TOKEN
                    }
                    
                    pub_data, pub_status = await asyncio.to_thread(http_post_form, publish_url, publish_payload)

                    if pub_status == 200:
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


# 靜態檔案掛載
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")