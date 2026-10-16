from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from google import genai
import os

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
# 🚀 處理前端的 AI 生成請求
# ========================================================
@app.post("/api/generate")
async def generate_content(data: dict):
    try:
        prompt = data.get("prompt", "")
        image_base64 = data.get("imageBase64", None)

        contents = [prompt]
        if image_base64:
            import base64
            image_bytes = base64.b64decode(image_base64)
            contents.append({
                "mime_type": "image/jpeg",
                "data": image_bytes
            })

        # 呼叫 Gemini 3.0 Flash 模型
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents
        )
        
        return JSONResponse(content={"candidates": [{"content": {"parts": [{"text": response.text}]}}]})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ========================================================
# 🚀 絕對不 404 的精準檔案路由
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
# 雲端部署與本機啟動設定
# ========================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend:app", host="0.0.0.0", port=port)