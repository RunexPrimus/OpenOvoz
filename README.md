# Botopne Bot - Railway Deployment

## 🚀 Railway ga o'rnatish

### 1. Railway da yangi service yarating
- [Railway.app](https://railway.app) ga kiring
- "New Project" → "Deploy from GitHub repo"
- O'zingizning GitHub repository ni tanlang

### 2. Environment Variables sozlang
Railway da quyidagi environment variables larni qo'shing:

```bash
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=123456789,987654321
SUPER_ADMIN_IDS=123456789
ADMIN_CHANNEL_ID=-1002796086920
```

### 3. PostgreSQL Database qo'shing
- Railway da "New" → "Database" → "Add PostgreSQL"
- Database avtomatik sozlanadi

### 4. Deploy qiling
- GitHub ga push qiling
- Railway avtomatik deploy qiladi

## 📁 Fayllar tuzilishi

```
botopneUZim/
├── bot.py                 # Asosiy bot kodi
├── config.py             # Konfiguratsiya
├── database_postgresql.py # PostgreSQL database
├── database_unified.py   # Database interface
├── keyboards.py          # Telegram klaviaturalar
├── messages.py           # Xabarlar
├── requirements.txt      # Python paketlar
├── Procfile             # Railway deployment
└── runtime.txt          # Python versiyasi
```

## 🔧 Xususiyatlar

- ✅ PostgreSQL database
- ✅ Telegram Bot API
- ✅ Admin panel
- ✅ Referral sistema
- ✅ Ovoz berish
- ✅ Balans boshqaruvi
- ✅ Excel hisobotlar
- ✅ Ko'p tilli qo'llab-quvvatlash (O'zbek, Rus)

## 📊 Performance

- **Concurrent users**: 10,000+ foydalanuvchiga xizmat ko'rsatadi
- **Database**: PostgreSQL - professional va ishonchli
- **Architecture**: Scalable va maintainable

## 🚀 Ishga tushirish

Bot Railway da avtomatik ishga tushadi. Faqat environment variables larni to'g'ri sozlashingiz kerak.
