from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

# 初始化 Google Gemini 客戶端
client = genai.Client()

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
    # 自動抓取雲端主機分配的 PORT，若在本地端執行則預設使用 8000
    port = int(os.environ.get("PORT", 8000))
    # 採用雲端建議的 "主機名稱:實例名稱" 字串格式啟動
    uvicorn.run("backend:app", host="0.0.0.0", port=port)
