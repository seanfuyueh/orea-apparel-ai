from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from google import genai
from google.genai import types
import os
import base64

app = FastAPI()

# 跨來源資源共享 (CORS) 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化 Google Gemini 客戶端 (會自動抓取環境變數 GEMINI_API_KEY)
client = genai.Client()

# ========================================================
# 🚀 處理前端的 AI 生成請求 (支援文字與圖片)
# ========================================================
import time
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
                time.sleep(2)  # 等待 2 秒後自動重試
                continue
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