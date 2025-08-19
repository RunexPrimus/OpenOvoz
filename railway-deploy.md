# Railway da Botopne Botini ishga tushirish

## 🚀 1-bosqich: Railway ga tizimga kirish

### Railway CLI o'rnatish
```bash
npm install -g @railway/cli
```

### Tizimga kirish
```bash
railway login
```

## 🏗 2-bosqich: Yangi loyiha yaratish

### Yangi loyiha yaratish
```bash
railway init
```

### Loyiha nomini tanlash
- Loyiha nomi: `botopne-bot`
- Template: `Empty Project`

## 📤 3-bosqich: Loyihani Railway ga yuklash

### Git repository ni Railway ga ulash
```bash
railway link
```

### Loyihani yuklash
```bash
railway up
```

## ⚙️ 4-bosqich: Muhit o'zgaruvchilarini sozlash

Railway dashboard da quyidagi o'zgaruvchilarni qo'shing:

### Asosiy sozlamalar
```
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_IDS=123456789,987654321
SUPER_ADMIN_IDS=123456789
RAILWAY_ENVIRONMENT=true
```

### Ixtiyoriy sozlamalar
```
WEBHOOK_URL=https://your-domain.railway.app/webhook
DATABASE_PATH=/tmp/botopne.db
REDIS_HOST=your_redis_host
REDIS_PORT=6379
REDIS_DB=0
```

## 🔧 5-bosqich: Botni ishga tushirish

### Avtomatik ishga tushirish
Railway avtomatik ravishda botni ishga tushiradi.

### Loglarni ko'rish
```bash
railway logs
```

### Bot holatini tekshirish
```bash
railway status
```

## 📱 6-bosqich: Botni sinab ko'rish

### Telegram da botni tekshirish
1. `/start` buyrug'ini yuboring
2. Bot javob berishini tekshiring
3. Admin panelini sinab ko'ring

## 🚨 Xatoliklar va yechimlar

### Bot ishlamayapti
```bash
# Loglarni ko'rish
railway logs

# Botni qayta ishga tushirish
railway up
```

### Muhit o'zgaruvchilari topilmadi
- Railway dashboard da o'zgaruvchilarni tekshiring
- `.env` faylini Railway ga yuklamang

### Database xatoliklari
- SQLite faylini `/tmp/` papkasida saqlang
- Railway ephemeral filesystem ni hisobga oling

## 🔄 Yangilashlar

### Yangi versiyani yuklash
```bash
git add .
git commit -m "Yangilangan versiya"
git push
railway up
```

### Botni qayta ishga tushirish
```bash
railway up
```

## 📊 Monitoring

### Loglarni kuzatish
```bash
railway logs --follow
```

### Resurslarni kuzatish
Railway dashboard da:
- CPU va RAM foydalanilishini
- Network trafikni
- Disk foydalanilishini kuzating

## 💡 Maslahatlar

1. **Muhit o'zgaruvchilari**: Hech qachon `.env` faylini git ga qo'shmang
2. **Database**: SQLite faylini `/tmp/` papkasida saqlang
3. **Loglar**: Muntazam ravishda loglarni tekshiring
4. **Backup**: Muhim ma'lumotlarni backup qiling
5. **Monitoring**: Bot holatini muntazam tekshiring

## 🆘 Yordam

Agar muammolar bo'lsa:
1. Railway loglarini tekshiring
2. Bot kodini sinab ko'ring
3. Railway support ga murojaat qiling
4. Telegram bot API xatoliklarini tekshiring
