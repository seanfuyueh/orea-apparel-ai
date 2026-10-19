)
INSTAGRAM_ACCOUNT_ID = os.environ.get("INSTAGRAM_ACCOUNT_ID", "17841405459290595")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "1144532311567385")
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")  # 專屬粉專 Token (若有設定則優先使用)
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")  # 專屬粉專 Token
IMGUR_CLIENT_ID = os.environ.get("IMGUR_CLIENT_ID", "546c25a59c58ad7")

# ========================================================
@@ -124,19 +124,18 @@ async def publish_post(request: Request, data: dict):
img_res = requests.post(imgur_url, headers=headers, data=payload, timeout=20).json()
if img_res.get("success"):
public_image_url = img_res["data"]["link"]
                    print(f"✅ [Imgur Upload] 圖片成功上傳至圖床，永久公開網址: {public_image_url}")
                    print(f"✅ [Imgur Upload] 圖片成功上傳至圖床: {public_image_url}")
else:
print(f"⚠️ [Imgur Upload Failed]: {img_res}")
except Exception as img_err:
print(f"⚠️ [Imgur Exception]: {str(img_err)}")

results = {}

        # 2. 發布至 Instagram (加入 3 秒緩衝等待，解決 9007 錯誤)
        # 2. 發布至 Instagram
if publish_ig:
if not public_image_url:
results["instagram"] = {"status": "error", "message": "Instagram 必須附帶圖片才能發布貼文"}
                print("❌ [IG Publish Error] 缺少圖床圖片網址")
else:
try:
container_url = f"https://graph.instagram.com/v22.0/{INSTAGRAM_ACCOUNT_ID}/media"
@@ -146,34 +145,27 @@ async def publish_post(request: Request, data: dict):
"access_token": INSTAGRAM_ACCESS_TOKEN
}
c_res = requests.post(container_url, data=container_payload, timeout=20).json()
                    print(f"📸 [IG Container Response]: {c_res}")
creation_id = c_res.get("id")

if creation_id:
                        # ⏳ 等待 3 秒讓 IG 伺服器準備好圖片素材
                        print("⏳ [IG Wait] 等待 3 秒讓 IG 處理圖片素材...")
time.sleep(3)

pub_url = f"https://graph.instagram.com/v22.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
pub_payload = {
"creation_id": creation_id,
"access_token": INSTAGRAM_ACCESS_TOKEN
}
p_res = requests.post(pub_url, data=pub_payload, timeout=20).json()
                        print(f"🚀 [IG Publish Response]: {p_res}")
results["instagram"] = {"status": "success", "data": p_res}
else:
results["instagram"] = {"status": "error", "message": c_res}
except Exception as ig_err:
                    print(f"⚠️ [IG Publish Exception]: {str(ig_err)}")
results["instagram"] = {"status": "error", "message": str(ig_err)}

        # 3. 發布至 Facebook 粉絲專頁 (優先使用獨立設定的 FB_PAGE_ACCESS_TOKEN)
        # 3. 發布至 Facebook 粉絲專頁
if publish_fb:
try:
page_access_token = FB_PAGE_ACCESS_TOKEN
if not page_access_token:
                    # 若未設定獨立粉專 Token，嘗試自動抓取
me_url = f"https://graph.facebook.com/v22.0/me/accounts"
me_params = {"access_token": INSTAGRAM_ACCESS_TOKEN}
me_res = requests.get(me_url, params=me_params, timeout=10).json()
@@ -183,7 +175,7 @@ async def publish_post(request: Request, data: dict):
page_access_token = page.get("access_token")
break
if not page_access_token:
                        page_access_token = INSTAGRAM_ACCESS_TOKEN  # 最後備用
                        page_access_token = INSTAGRAM_ACCESS_TOKEN

if public_image_url:
fb_url = f"https://graph.facebook.com/v22.0/{FB_PAGE_ID}/photos"
@@ -201,21 +193,17 @@ async def publish_post(request: Request, data: dict):

fb_response = requests.post(fb_url, data=fb_payload, timeout=20)
fb_res = fb_response.json()
                print(f"📘 [FB Publish HTTP Status]: {fb_response.status_code}")
                print(f"📘 [FB Publish Response JSON]: {fb_res}")

if fb_response.status_code == 200 and "id" in fb_res:
results["facebook"] = {"status": "success", "data": fb_res}
else:
results["facebook"] = {"status": "error", "message": fb_res}
except Exception as fb_err:
                print(f"🔥 [FB Publish Exception Error]: {str(fb_err)}")
results["facebook"] = {"status": "error", "message": str(fb_err)}

return JSONResponse(content={"status": "complete", "results": results})

except Exception as e:
        print(f"🔥 [Publish General Error]: {str(e)}")
return JSONResponse(status_code=500, content={"error": str(e)})

# ========================================================
@@ -256,8 +244,7 @@ async def get_realtime_trends():
items = response.json()

if not isinstance(items, list) or len(items) == 0:
            error_msg = items.get("error", {}).get("message", "無法取得 IG 數據") if isinstance(items, dict) else "無法取得 IG 貼文數據，請確認 ig_targets.txt 網址或 Apify 狀態。"
            return JSONResponse(status_code=500, content={"error": error_msg})
            return JSONResponse(status_code=500, content={"error": "無法取得 IG 貼文數據"})

sorted_posts = sorted(
items, 
@@ -266,7 +253,6 @@ async def get_realtime_trends():
)[:10]

trend_summary_prompt = "你是一位韓國時尚流行趨勢分析師。以下是實時抓取到的最新熱門 IG 爆款貼文數據與圖片：\n\n"
        
image_parts = []
for idx, post in enumerate(sorted_posts, 1):
likes = post.get('likesCount', 0)
@@ -275,94 +261,29 @@ async def get_realtime_trends():
post_url = post.get('url', '')
display_url = post.get('displayUrl', '')

            trend_summary_prompt += f"【🔥 爆款單品第 {idx} 名】\n"
            trend_summary_prompt += f"- 貼文真實連結: {post_url}\n"
            trend_summary_prompt += f"- 互動數據: 按讚 {likes} | 留言 {comments}\n"
            trend_summary_prompt += f"- 貼文內文: {caption[:150]}...\n\n"
            trend_summary_prompt += f"【🔥 爆款單品第 {idx} 名】\n- 連結: {post_url}\n- 互動: 按讚 {likes} | 留言 {comments}\n- 內文: {caption[:150]}...\n\n"

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
                        image_parts.append(types.Part.from_bytes(data=img_resp.content, mime_type="image/jpeg"))
                except Exception:
                    pass

        trend_summary_prompt += "請根據上述數據與圖片產出一份「東大門流行趨勢與爆款 TOP 10 分析報告」，每款下方必須附上 [📸 查看 Instagram 貼文](連結)。"
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

        ai_response = client.models.generate_content(model='gemini-3.8-flash', contents=contents)
        return JSONResponse(content={"report": ai_response.text})
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