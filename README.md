# Botopne - Ochiq Byudjet Ovoz Berish Boti

Bu Telegram boti fuqarolarga ochiq byudjet loyihalariga ovoz berish imkonini beradi va SQLite ma'lumotlar bazasida ishlaydi.

## 🎯 Asosiy maqsad

Fuqarolarga ochiq byudjet (open budget) loyihalariga oylab/har chorak ovoz berish imkonini berish. Foydalanuvchilar toplagan ball/pul (bonus) orqali rag'batlanadi.

## ✨ Asosiy funksiyalar

### 👤 Foydalanuvchilar uchun:
- 🗳 Loyihalarga ovoz berish
- 💰 Balans va bonuslar
- 👥 Referal tizimi
- 📖 Qo'llanma va yordam
- ℹ️ Profil ma'lumotlari
- 📢 Yangiliklar

### 🛠 Adminlar uchun:
- 📊 Statistika va hisobotlar
- 🗳 Mavsum va loyihalarni boshqarish
- 👥 Foydalanuvchilarni boshqarish
- 💸 Pul chiqarish so'rovlarini tasdiqlash
- ✉️ Mass xabar yuborish
- 📤 Ma'lumotlarni eksport qilish

## 🏗 Loyiha strukturasi

```
botopne/
├── bot.py              # Asosiy bot fayli
├── database.py         # Ma'lumotlar bazasi
├── keyboards.py        # Klaviaturalar
├── messages.py         # Xabarlar (o'zbek/rus)
├── config.py           # Sozlamalar
├── requirements.txt    # Kerakli kutubxonalar
├── env_example.txt     # Muhit o'zgaruvchilari namunasi
└── README.md          # Ushbu fayl
```

## 🚀 O'rnatish va ishga tushirish

### Lokal o'rnatish

#### 1. Kerakli kutubxonalarni o'rnatish
```bash
pip install -r requirements.txt
```

#### 2. Muhit o'zgaruvchilarini sozlash
```bash
# env_example.txt faylini .env ga nusxalang
cp env_example.txt .env

# .env faylini tahrirlang va bot tokenini kiriting
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=your_telegram_id
```

#### 3. Botni ishga tushirish
```bash
python bot.py
```

### Railway da ishga tushirish

#### 1. Railway ga loyihani yuklash
```bash
# Railway CLI o'rnatish
npm install -g @railway/cli

# Railway ga tizimga kirish
railway login

# Yangi loyiha yaratish
railway init

# Loyihani Railway ga yuklash
railway up
```

#### 2. Muhit o'zgaruvchilarini sozlash
Railway dashboard da quyidagi o'zgaruvchilarni qo'shing:
- `BOT_TOKEN` - Telegram bot tokeni
- `ADMIN_IDS` - Admin ID lari (vergul bilan ajratilgan)
- `SUPER_ADMIN_IDS` - Super admin ID lari
- `RAILWAY_ENVIRONMENT` - `true` qiymatini bering
- `WEBHOOK_URL` - Webhook URL (agar kerak bo'lsa)

#### 3. Botni ishga tushirish
Railway avtomatik ravishda botni ishga tushiradi.

## 📱 Bot buyruqlari

- `/start` - Botni ishga tushirish va ro'yxatdan o'tish
- `/help` - Yordam olish
- `/admin` - Admin paneliga kirish (faqat adminlar uchun)

## 🗄 Ma'lumotlar bazasi

Bot SQLite ma'lumotlar bazasida ishlaydi va quyidagi jadvallarni o'z ichiga oladi:

- **users** - Foydalanuvchilar
- **seasons** - Ovoz berish mavsumlari
- **projects** - Loyihalar
- **votes** - Ovozlar
- **withdrawal_requests** - Pul chiqarish so'rovlari
- **balance_history** - Balans tarixi
- **announcements** - Yangiliklar
- **audit_logs** - Audit loglari

## 🔧 Sozlamalar

`config.py` faylida quyidagi sozlamalarni o'zgartirishingiz mumkin:

- Bonus miqdorlari
- Komissiya foizi
- Minimal yechish miqdori
- Ovoz berish cheklovlari
- Hududlar ro'yxati

## 🌐 Til qo'llab-quvvatlash

Bot o'zbek va rus tillarini qo'llab-quvvatlaydi. Foydalanuvchi ro'yxatdan o'tishda tilni tanlaydi.

## 🔒 Xavfsizlik

- Admin huquqlarini tekshirish
- Rate limiting (Redis orqali)
- Anti-spam choralari
- Foydalanuvchi ma'lumotlarini himoya qilish

## 📊 Monitoring va loglar

Bot barcha harakatlarni log qiladi va admin panel orqali monitoring qilish mumkin.

## 🤝 Hissa qo'shish

Loyihaga hissa qo'shish uchun:
1. Repositoryni fork qiling
2. Yangi branch yarating
3. O'zgarishlarni commit qiling
4. Pull request yuboring

## 📞 Yordam

Agar savollaringiz bo'lsa yoki yordam kerak bo'lsa, iltimos bog'laning.

## 📄 Litsenziya

Bu loyiha MIT litsenziyasi ostida tarqatiladi.

---

**Eslatma:** Bot ishga tushirishdan oldin Telegram Bot API dan token olishingiz va .env faylida sozlashingiz kerak.
