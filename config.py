import os
from dotenv import load_dotenv

load_dotenv()

# Bot sozlamalari
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]
SUPER_ADMIN_IDS = [int(id) for id in os.getenv('SUPER_ADMIN_IDS', '').split(',') if id]

# Railway PostgreSQL Configuration
# Railway avtomatik DATABASE_URL ni beradi (ENG MUHIM!)
DATABASE_URL = os.getenv('DATABASE_URL', None)
DATABASE_PUBLIC_URL = os.getenv('DATABASE_PUBLIC_URL', None)

# Fallback uchun individual parametrlar (faqat local development uchun)
# Railway da bu parametrlar ishlatilmaydi
POSTGRES_HOST = os.getenv('PGHOST', 'localhost')
POSTGRES_PORT = int(os.getenv('PGPORT', 5432))
POSTGRES_DB = os.getenv('PGDATABASE', 'railway')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('PGPASSWORD', '')

# Debug uchun
print(f"Railway Environment Variables:")
print(f"DATABASE_URL: {'Mavjud' if DATABASE_URL else 'Yo\'q'}")
print(f"DATABASE_PUBLIC_URL: {'Mavjud' if DATABASE_PUBLIC_URL else 'Yo\'q'}")
print(f"PGHOST: {POSTGRES_HOST}")
print(f"PGPORT: {POSTGRES_PORT}")
print(f"PGDATABASE: {POSTGRES_DB}")

# Bonus va komissiya (database dan olinadi, default qiymatlar)
REFERRAL_BONUS = 1000  # Referal uchun bonus (default)
VOTE_BONUS = 25000       # Ovoz berish uchun bonus (default)
MIN_WITHDRAWAL = 20000 # Minimal yechish miqdori (default)
COMMISSION_RATE = 0.02 # 2% komissiya (default)

# Ovoz berish cheklovlari
MAX_VOTES_PER_SEASON = 10  # Har mavsumda maksimal ovozlar
VOTE_COOLDOWN = 3600      # Ovozlar orasidagi vaqt (sekund)

# Til sozlamalari
SUPPORTED_LANGUAGES = ['uz', 'ru']
DEFAULT_LANGUAGE = 'uz'

# Hududlar
REGIONS = {
    'toshkent': 'Toshkent',
    'andijon': 'Andijon',
    'buxoro': 'Buxoro',
    'fargona': 'Farg\'ona',
    'jizzax': 'Jizzax',
    'namangan': 'Namangan',
    'navoiy': 'Navoiy',
    'qashqadaryo': 'Qashqadaryo',
    'samarqand': 'Samarqand',
    'sirdaryo': 'Sirdaryo',
    'surxondaryo': 'Surxondaryo',
    'xorazm': 'Xorazm',
    'qoraqalpogiston': 'Qoraqalpog\'iston'
}

# Admin kanal ID - ovoz berish tasdiqlashlari uchun
ADMIN_CHANNEL_ID = int(os.getenv('ADMIN_CHANNEL_ID', -1002796086920))
