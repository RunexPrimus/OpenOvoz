from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from config import REGIONS

def get_main_keyboard(language='uz'):
    """Asosiy klaviatura"""
    if language == 'uz':
        keyboard = [
            ['🗳 Ovoz berish'],
            ['💰 Balans', '👥 Do\'stlarga ulash'],
            ['📖 Qo\'llanma', 'ℹ️ Profil'],
            ['📢 Yangiliklar']
        ]
    else:  # ru
        keyboard = [
            ['🗳 Голосовать'],
            ['💰 Баланс', '👥 Пригласить друзей'],
            ['📖 Инструкция', 'ℹ️ Профиль'],
            ['📢 Новости']
        ]
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_language_keyboard():
    """Til tanlash klaviaturasi"""
    keyboard = [
        [InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_region_keyboard():
    """Hudud tanlash klaviaturasi"""
    keyboard = []
    row = []
    
    for i, (key, name) in enumerate(REGIONS.items()):
        row.append(InlineKeyboardButton(name, callback_data=f"region_{key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:  # Qolgan hududlarni qo'shish
        keyboard.append(row)
    
    return InlineKeyboardMarkup(keyboard)

def get_vote_confirmation_keyboard(project_id):
    """Ovoz tasdiqlash klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Ha", callback_data=f"vote_yes_{project_id}"),
            InlineKeyboardButton("❌ Yo'q", callback_data=f"vote_no_{project_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_balance_keyboard(language='uz'):
    """Balans klaviaturasi"""
    if language == 'uz':
        keyboard = [
            ['💸 Pul chiqarish', '📊 Tarix'],
            ['📋 Qoidalar', '🔙 Orqaga']
        ]
    else:
        keyboard = [
            ['💸 Вывод средств', '📊 История'],
            ['📋 Правила', '🔙 Назад']
        ]
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_withdrawal_method_keyboard(language='uz'):
    """Pul chiqarish usuli klaviaturasi"""
    if language == 'uz':
        keyboard = [
            [InlineKeyboardButton("💳 Karta (Payme/Click/Uzum)", callback_data="withdraw_card")],
            [InlineKeyboardButton("📱 Telefon raqami", callback_data="withdraw_phone")],
            [InlineKeyboardButton("🏦 Hisob raqami", callback_data="withdraw_account")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("💳 Карта (Payme/Click/Uzum)", callback_data="withdraw_card")],
            [InlineKeyboardButton("📱 Номер телефона", callback_data="withdraw_phone")],
            [InlineKeyboardButton("🏦 Номер счета", callback_data="withdraw_account")]
        ]
    
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard(language='uz'):
    """Admin klaviaturasi"""
    if language == 'uz':
        keyboard = [
            ['📊 Statistikalar', '🗳 Mavsum & Loyihalar'],
            ['💰 Pul berish', '📊 Reytinglar'],
            ['📢 Broadcast', '📝 Yangiliklar'],
            ['🔙 Asosiy menyu']
        ]
    else:
        keyboard = [
            ['📊 Статистика', '🗳 Сезоны & Проекты'],
            ['💰 Выплаты', '📊 Рейтинги'],
            ['📢 Рассылка', '📝 Новости'],
            ['🔙 Главное меню']
        ]
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_admin_main_keyboard(language='uz'):
    """Admin foydalanuvchilar uchun asosiy klaviatura (admin panel bilan)"""
    if language == 'uz':
        keyboard = [
            ['🗳 Ovoz berish'],
            ['💰 Balans', '👥 Do\'stlarga ulash'],
            ['📖 Qo\'llanma', 'ℹ️ Profil'],
            ['📢 Yangiliklar', '🛠 Admin panel']
        ]
    else:  # ru
        keyboard = [
            ['🗳 Голосовать'],
            ['💰 Баланс', '👥 Пригласить друзей'],
            ['📖 Инструкция', 'ℹ️ Профиль'],
            ['📢 Новости', '🛠 Панель администратора']
        ]
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_admin_project_management_keyboard():
    """Admin loyiha boshqaruvi klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("➕ Yangi loyiha", callback_data="admin_new_project"),
            InlineKeyboardButton("📝 Loyihalarni tahrirlash", callback_data="admin_edit_projects")
        ],
        [
            InlineKeyboardButton("🗑 Loyihalarni o'chirish", callback_data="admin_delete_projects")
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_user_management_keyboard():
    """Admin foydalanuvchi boshqaruvi klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("🔍 Qidirish", callback_data="admin_search_users"),
            InlineKeyboardButton("📊 Statistika", callback_data="admin_user_stats")
        ],
        [
            InlineKeyboardButton("🚫 Bloklash", callback_data="admin_ban_users"),
            InlineKeyboardButton("✅ Blokdan chiqarish", callback_data="admin_unban_users")
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_withdrawal_action_keyboard(withdrawal_id):
    """Pul chiqarish so'rovini boshqarish klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_withdrawal_{withdrawal_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_withdrawal_{withdrawal_id}")
        ],
        [InlineKeyboardButton("📝 Izoh qo'shish", callback_data=f"note_withdrawal_{withdrawal_id}")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_withdrawals_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_export_keyboard():
    """Eksport klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="export_users"),
            InlineKeyboardButton("🗳 Ovozlar", callback_data="export_votes")
        ],
        [
            InlineKeyboardButton("🏗 Loyihalar", callback_data="export_projects"),
            InlineKeyboardButton("💸 To'lovlar", callback_data="export_payments")
        ],
        [
            InlineKeyboardButton("👥 Referallar", callback_data="export_referrals"),
            InlineKeyboardButton("📊 Umumiy statistika", callback_data="export_stats")
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    """Orqaga qaytish tugmasi"""
    keyboard = [
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard():
    """Bekor qilish tugmasi"""
    keyboard = [
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_edit_keyboard():
    """Loyiha tahrirlashni bekor qilish tugmasi"""
    keyboard = [
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_edit")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_skip_referral_keyboard(language='uz'):
    """Referal o'tkazib yuborish klaviaturasi"""
    if language == 'uz':
        text = "⏭ O'tkazib yuborish"
    else:
        text = "⏭ Пропустить"
    
    keyboard = [[InlineKeyboardButton(text, callback_data="skip_referral")]]
    return InlineKeyboardMarkup(keyboard)

def get_project_approval_keyboard():
    """Loyiha tasdiqlash klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data="approve_project"),
            InlineKeyboardButton("❌ Rad etish", callback_data="reject_project")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_screenshot_keyboard():
    """Screenshot yuborish klaviaturasi (faqat bekor qilish tugmasi)"""
    keyboard = [
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_screenshot")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_project_delete_confirmation_keyboard(project_id):
    """Loyihani o'chirishni tasdiqlash klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Ha, o'chirish", callback_data=f"delete_project_{project_id}"),
            InlineKeyboardButton("❌ Yo'q, bekor qilish", callback_data="cancel_delete_project")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_vote_approval_keyboard(user_id: int, project_id: int):
    """Ovoz berishni tasdiqlash klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"vote_approve_{user_id}_{project_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"vote_reject_{user_id}_{project_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_withdrawal_approval_keyboard(user_id: int, amount: int):
    """Pul chiqarish so'rovini tasdiqlash klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("✅ To'lov amalga oshirildi", callback_data=f"withdrawal_completed_{user_id}_{amount}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"withdrawal_rejected_{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_broadcast_preview_keyboard():
    """Broadcast xabar preview klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Yuborish", callback_data="confirm_broadcast"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_broadcast")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_broadcast_cancel_keyboard():
    """Broadcast bekor qilish klaviaturasi"""
    keyboard = [
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_broadcast")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_news_cancel_keyboard():
    """Yangilik yaratishni bekor qilish klaviaturasi"""
    keyboard = [
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_news")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_withdrawal_action_keyboard(withdrawal_id):
    """Pul chiqarish so'rovini boshqarish klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_withdrawal_{withdrawal_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_withdrawal_{withdrawal_id}")
        ],
        [InlineKeyboardButton("📝 Izoh qo'shish", callback_data=f"note_withdrawal_{withdrawal_id}")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_withdrawals_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_payment_management_keyboard():
    """Pul berish boshqaruvi klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("💰 Pul berish", callback_data="admin_pay_users"),
            InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_payment_settings")
        ],
        [
            InlineKeyboardButton("📊 Tarix", callback_data="admin_payment_history"),
            InlineKeyboardButton("📋 Hisobot", callback_data="admin_payment_report")
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_payment_settings_keyboard():
    """Pul berish sozlamalari klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("👥 Referal bonusi", callback_data="admin_setting_REFERRAL_BONUS"),
            InlineKeyboardButton("🗳 Ovoz bonusi", callback_data="admin_setting_VOTE_BONUS")
        ],
        [
            InlineKeyboardButton("💸 Minimal yechish", callback_data="admin_setting_MIN_WITHDRAWAL"),
            InlineKeyboardButton("📊 Komissiya %", callback_data="admin_setting_COMMISSION_RATE")
        ],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_payment_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_setting_confirmation_keyboard(setting_key):
    """Sozlama tasdiqlash klaviaturasi"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"confirm_setting_{setting_key}"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_setting")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
