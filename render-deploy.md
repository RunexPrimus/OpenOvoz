# Render'ga Deploy Qilish Yo'riqnomasi

## 1. GitHub'ga kodni yuklang
```bash
git add .
git commit -m "Bot ready for deployment"
git push origin main
```

## 2. Render'da yangi servis yarating
1. [render.com](https://render.com) ga kiring
2. "New +" tugmasini bosing
3. "Web Service" ni tanlang
4. GitHub repository'ni ulang

## 3. Sozlamalar
- **Name**: marketbot
- **Environment**: Python
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python bot.py`
- **Plan**: Free

## 4. Environment Variables qo'shing
Render'da quyidagi environment variables'ni qo'shing:

### **Majburiy:**
- `BOT_TOKEN`: Telegram bot tokeni (@BotFather dan)
- `ADMIN_IDS`: Admin Telegram ID lar (vergul bilan ajrating, masalan: 123456789,987654321)
- `SUPER_ADMIN_IDS`: Super Admin ID lar (vergul bilan ajrating)
- `ADMIN_CHANNEL_ID`: Admin kanal ID (ovoz berish tasdiqlashlari uchun)

### **Ixtiyoriy:**
- `DATABASE_PATH`: Database fayl yo'li (default: botopne.db)

## 5. Deploy qiling
"Create Web Service" tugmasini bosing va kutib turing.

## 6. Test qiling
Bot avtomatik ishga tushadi va 24/7 ishlaydi!
