import logging
import hashlib
import secrets
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, Contact, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from database import Database
from keyboards import *
from messages import get_message
from config import *
import asyncio
import telegram

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation holatlari
CHOOSING_LANGUAGE = 0
ENTERING_PHONE = 1
ENTERING_REGION = 2
MAIN_MENU = 3
CHOOSING_CATEGORY = 4
NEW_PROJECT_NAME = 5
NEW_PROJECT_LINK = 6
NEW_PROJECT_APPROVAL = 7
ADMIN_MENU = 8
SCREENSHOT_REQUEST = 11
SCREENSHOT_RECEIVED = 12
SCREENSHOT_VERIFICATION = 13
WITHDRAWAL_ACCOUNT = 14
EDIT_PROJECT_NAME = 15
EDIT_PROJECT_LINK = 16
EDIT_PROJECT_APPROVAL = 17
BROADCAST_MESSAGE = 18
NEWS_TITLE = 19
NEWS_CONTENT = 20
NEWS_APPROVAL = 21

class BotopneBot:
    def __init__(self):
        self.db = Database()
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Handlerlarni sozlash"""
        
        # Conversation handler - ro'yxatdan o'tish
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                CHOOSING_LANGUAGE: [
                    CallbackQueryHandler(self.language_selected, pattern='^lang_')
                ],
                ENTERING_PHONE: [
                    MessageHandler(filters.CONTACT, self.phone_received),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.phone_text_received)
                ],
                ENTERING_REGION: [
                    CallbackQueryHandler(self.region_selected, pattern='^region_')
                ],
                MAIN_MENU: [
                    MessageHandler(filters.Regex('^🗳 Ovoz berish$|^🗳 Голосовать$'), self.vote_menu),
                    MessageHandler(filters.Regex('^💰 Balans$|^💰 Баланс$'), self.balance_menu),
                    MessageHandler(filters.Regex('^👥 Do\'stlarga ulash$|^👥 Пригласить друзей$'), self.referral_menu),
                    MessageHandler(filters.Regex('^📖 Qo\'llanma$|^📖 Инструкция$'), self.help_menu),
                    MessageHandler(filters.Regex('^ℹ️ Profil$|^ℹ️ Профиль$'), self.profile_menu),
                    MessageHandler(filters.Regex('^📢 Yangiliklar$|^📢 Новости$'), self.news_menu),
                    MessageHandler(filters.Regex('^🛠 Admin panel$|^🛠 Панель администратора$'), self.admin_menu),
                    MessageHandler(filters.Regex('^🔙 Orqaga$|^🔙 Назад$'), self.back_to_main),
                    MessageHandler(filters.Regex('^💸 Pul chiqarish$|^💸 Вывод средств$'), self.withdrawal_menu),
                    MessageHandler(filters.Regex('^📊 Tarix$|^📊 История$'), self.balance_history),
                    MessageHandler(filters.Regex('^📋 Qoidalar$|^📋 Правила$'), self.rules_menu)
                ],
                WITHDRAWAL_ACCOUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.withdrawal_account_received),
                    CallbackQueryHandler(self.button_callback, pattern='^back$')
                ]
            },
            fallbacks=[CommandHandler('start', self.start)]
        )
        
        # Callback query handler
        callback_handler = CallbackQueryHandler(self.button_callback)
        
        # Admin conversation handler
        admin_conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^🛠 Admin panel$|^🛠 Панель администратора$'), self.admin_menu)],
            states={
                ADMIN_MENU: [
                    MessageHandler(filters.Regex('^📊 Statistikalar$|^📊 Статистика$'), self.admin_statistics),
                    MessageHandler(filters.Regex('^🗳 Mavsum & Loyihalar$|^🗳 Сезоны & Проекты$'), self.admin_projects),
                    MessageHandler(filters.Regex('^📊 Reytinglar$|^📊 Рейтинги$'), self.admin_ratings),
                    MessageHandler(filters.Regex('^📝 Yangiliklar$|^📝 Новости$'), self.start_news_creation),
                    MessageHandler(filters.Regex('🔙 Asosiy menyu$|^🔙 Главное меню$'), self.back_to_main)
                ]
            },
            fallbacks=[MessageHandler(filters.Regex('🔙 Asosiy menyu$|^🔙 Главное меню$'), self.back_to_main)]
        )
        
        # Yangi loyiha qo'shish conversation handler
        new_project_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_new_project, pattern='^admin_new_project$')],
            states={
                NEW_PROJECT_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.project_name_received)
                ],
                NEW_PROJECT_LINK: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.project_link_received)
                ],
                NEW_PROJECT_APPROVAL: [
                    CallbackQueryHandler(self.project_approval_received, pattern='^(approve|reject)_project$')
                ]
            },
            fallbacks=[CallbackQueryHandler(self.cancel_new_project, pattern='^cancel$')]
        )
        
        # Screenshot verification conversation handler
        screenshot_conv_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.handle_approved_project_vote, pattern='^vote_project_\d+$')
            ],
            states={
                SCREENSHOT_REQUEST: [
                    MessageHandler(filters.PHOTO, self.screenshot_received),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.screenshot_text_received)
                ],
                SCREENSHOT_RECEIVED: [
                    MessageHandler(filters.PHOTO, self.screenshot_verification),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.screenshot_text_received)
                ],
                SCREENSHOT_VERIFICATION: [
                    MessageHandler(filters.PHOTO, self.screenshot_final_verification),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.screenshot_text_received)
                ]
            },
            fallbacks=[CallbackQueryHandler(self.cancel_screenshot, pattern='^cancel_screenshot$')]
        )
        
        # Loyiha tahrirlash conversation handler
        edit_project_conv_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.start_edit_project, pattern='^edit_(name|link)_\d+$')
            ],
            states={
                EDIT_PROJECT_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.edit_project_name_received)
                ],
                EDIT_PROJECT_LINK: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.edit_project_link_received)
                ],
                EDIT_PROJECT_APPROVAL: [
                    CallbackQueryHandler(self.edit_project_approval_received, pattern='^(approve|reject)_edit$')
                ]
            },
            fallbacks=[CallbackQueryHandler(self.cancel_edit_project, pattern='^cancel_edit$')]
        )
        
        # Admin handlerlar - conversation handler emas, oddiy handlerlar
        admin_handlers = [
            MessageHandler(filters.Regex('^📊 Statistikalar$|^📊 Статистика$'), self.admin_statistics),
            MessageHandler(filters.Regex('^🗳 Mavsum & Loyihalar$|^🗳 Сезоны & Проекты$'), self.admin_projects),
            MessageHandler(filters.Regex('^📊 Reytinglar$|^📊 Рейтинги$'), self.admin_ratings),
            MessageHandler(filters.Regex('^📝 Yangiliklar$|^📝 Новости$'), self.start_news_creation),
            MessageHandler(filters.Regex('^🔙 Asosiy menyu$|^🔙 Главное меню$'), self.back_to_main)
        ]
        
        # Broadcast conversation handler
        broadcast_conv_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex('^📢 Broadcast$|^📢 Рассылка$'), self.start_broadcast)
            ],
            states={
                BROADCAST_MESSAGE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.broadcast_text_received),
                    MessageHandler(filters.PHOTO, self.broadcast_photo_received),
                    MessageHandler(filters.VIDEO, self.broadcast_video_received),
                    MessageHandler(filters.Document.ALL, self.broadcast_document_received),
                    MessageHandler(filters.FORWARDED, self.broadcast_forwarded_received),
                    MessageHandler(filters.Regex('^❌ Bekor qilish$'), self.cancel_broadcast)
                ]
            },
            fallbacks=[MessageHandler(filters.Regex('^❌ Bekor qilish$'), self.cancel_broadcast)]
        )

        # Yangilik yaratish conversation handler
        news_conv_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex('^📝 Yangiliklar$|^📝 Новости$'), self.start_news_creation)
            ],
            states={
                NEWS_TITLE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.news_title_received),
                    CallbackQueryHandler(self.cancel_news_creation, pattern='^cancel_news$')
                ],
                NEWS_CONTENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.news_content_received),
                    CallbackQueryHandler(self.cancel_news_creation, pattern='^cancel_news$')
                ],
                NEWS_APPROVAL: [
                    CallbackQueryHandler(self.news_approval_received, pattern='^(approve|reject)_news$')
                ]
            },
            fallbacks=[CallbackQueryHandler(self.cancel_news_creation, pattern='^cancel_news$')]
        )
        
        # Handlerlarni qo'shish
        self.application.add_handler(conv_handler)
        # Yangi loyiha qo'shish conversation handlerni umumiy callbackdan OLDIN qo'shamiz
        self.application.add_handler(new_project_conv_handler)
        # Screenshot verification conversation handlerni qo'shamiz
        self.application.add_handler(screenshot_conv_handler)
        # Loyiha tahrirlash conversation handlerni qo'shamiz
        self.application.add_handler(edit_project_conv_handler)
        # Umumiy callback handler oxirroqda turadi, aks holda yuqoridagi conversation ishlamay qoladi
        self.application.add_handler(callback_handler)
        # self.application.add_handler(admin_conv_handler)  # Conversation handler emas
        
        # Admin handlerlarni qo'shish
        for handler in admin_handlers:
            self.application.add_handler(handler)
        
        # Qo'shimcha handlerlar
        self.application.add_handler(CommandHandler('help', self.help_command))
        self.application.add_handler(CommandHandler('admin', self.admin_command))
        self.application.add_handler(CommandHandler('profile', self.profile_command))
        self.application.add_handler(CommandHandler('balance', self.balance_command))
        
        # Add handlers to application
        self.application.add_handler(admin_conv_handler)
        self.application.add_handler(edit_project_conv_handler)
        self.application.add_handler(broadcast_conv_handler)
        self.application.add_handler(news_conv_handler)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Botni ishga tushirish"""
        user = update.effective_user
        
        # Referal kodni tekshirish
        referral_code = None
        if context.args and context.args[0].startswith('ref_'):
            referral_code = context.args[0][4:]  # 'ref_' ni olib tashlash
        
        # Foydalanuvchi mavjudligini tekshirish
        existing_user = self.db.get_user(user.id)
        if existing_user:
            # Mavjud foydalanuvchi uchun asosiy menyu
            language = existing_user['language']
            
            # Admin foydalanuvchilar uchun admin klaviatura
            if user.id in ADMIN_IDS or user.id in SUPER_ADMIN_IDS:
                keyboard = get_admin_main_keyboard(language)
            else:
                keyboard = get_main_keyboard(language)
            
            await update.message.reply_text(
                get_message('main_menu', language),
                reply_markup=keyboard
            )
            return MAIN_MENU
        
        # Yangi foydalanuvchi uchun til tanlash
        if referral_code:
            # Referal kodni context ga saqlash
            context.user_data['referral_code'] = referral_code
            await update.message.reply_text(
                f"🎉 Do'stingiz orqali keldingiz! Referal kodi: {referral_code}",
                reply_markup=get_language_keyboard()
            )
        else:
            await update.message.reply_text(
                get_message('welcome'),
                reply_markup=get_language_keyboard()
            )
        return CHOOSING_LANGUAGE
    
    async def language_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Til tanlanganda"""
        query = update.callback_query
        await query.answer()
        
        language = query.data.split('_')[1]
        context.user_data['language'] = language
        
        # Telefon raqam so'rash
        keyboard = [[KeyboardButton(get_message('phone_share_button', language), request_contact=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await query.edit_message_text(get_message('phone_request', language))
        await query.message.reply_text(
            get_message('phone_request', language),
            reply_markup=reply_markup
        )
        
        return ENTERING_PHONE
    
    async def phone_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Telefon raqam qabul qilinganda (Contact orqali)"""
        contact = update.message.contact
        context.user_data['phone'] = contact.phone_number
        
        # Hudud tanlash
        await update.message.reply_text(
            get_message('region_request', context.user_data['language']),
            reply_markup=get_region_keyboard()
        )
        
        return ENTERING_REGION
    
    async def phone_text_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Telefon raqam matn ko'rinishida kiritilganda"""
        phone = update.message.text
        if not phone.startswith('+'):
            phone = '+' + phone
        
        context.user_data['phone'] = phone
        
        # Hudud tanlash
        await update.message.reply_text(
            get_message('region_request', context.user_data['language']),
            reply_markup=get_region_keyboard()
        )
        
        return ENTERING_REGION
    
    async def region_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Hudud tanlanganda"""
        query = update.callback_query
        await query.answer()
        
        region = query.data.split('_')[1]
        context.user_data['region'] = region
        
        # Referal so'ramaymiz, to'g'ridan to'g'ri ro'yxatdan o'tishni yakunlaymiz
        await self.complete_registration(update, context)
        return MAIN_MENU
    
    async def skip_referral(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Referal o'tkazib yuborish"""
        query = update.callback_query
        await query.answer()
        
        await self.complete_registration(update, context)
        return MAIN_MENU
    
    async def referral_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Referal kod kiritilganda"""
        referral_code = update.message.text
        context.user_data['referral_code'] = referral_code
        
        await self.complete_registration(update, context)
        return MAIN_MENU
    
    async def complete_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ro'yxatdan o'tishni yakunlash"""
        user = update.effective_user
        language = context.user_data['language']
        
        # Referal kodini tekshirish
        referred_by = None
        if 'referral_code' in context.user_data:
            referral_code = context.user_data['referral_code']
            # Referal kodni tekshirish
            referrer = self.db.get_user_by_referral_code(referral_code)
            if referrer:
                referred_by = referrer['id']
                # Referal va yangi foydalanuvchiga bonus berish
                self.db.add_balance(referrer['id'], REFERRAL_BONUS, 'referral_bonus', f'Yangi foydalanuvchi jalb etildi')
        
        # Foydalanuvchini bazaga qo'shish
        user_id = self.db.create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=context.user_data['phone'],
            region=context.user_data['region'],
            language=language,
            referred_by=referred_by
        )
        
        if user_id:
            # Yangi foydalanuvchiga bonus berish
            if referred_by:
                self.db.add_balance(user_id, REFERRAL_BONUS, 'referral_bonus', f'Referal orqali ro\'yxatdan o\'tish')
            
            # Admin foydalanuvchilar uchun admin klaviatura
            if user.id in ADMIN_IDS or user.id in SUPER_ADMIN_IDS:
                keyboard = get_admin_main_keyboard(language)
            else:
                keyboard = get_main_keyboard(language)
            
            # Callback query yoki message ni tekshirish
            if hasattr(update, 'callback_query') and update.callback_query:
                # Callback query uchun yangi xabar yuborish (edit_message_text ReplyKeyboardMarkup bilan ishlamaydi)
                await context.bot.send_message(
                    chat_id=user.id,
                    text=get_message('registration_complete', language),
                    reply_markup=keyboard
                )
                # Eski xabarni o'chirish
                try:
                    await update.callback_query.delete_message()
                except:
                    pass
            elif hasattr(update, 'message') and update.message:
                await update.message.reply_text(
                    get_message('registration_complete', language),
                    reply_markup=keyboard
                )
            else:
                # Agar hech qaysi ham mavjud bo'lmasa, yangi xabar yuborish
                await context.bot.send_message(
                    chat_id=user.id,
                    text=get_message('registration_complete', language),
                    reply_markup=keyboard
                )
        else:
            # Xato xabari
            if hasattr(update, 'callback_query') and update.callback_query:
                # Callback query uchun yangi xabar yuborish
                await context.bot.send_message(
                    chat_id=user.id,
                    text=get_message('error_occurred', language),
                    reply_markup=get_main_keyboard(language)
                )
                # Eski xabarni o'chirish
                try:
                    await update.callback_query.delete_message()
                except:
                    pass
            elif hasattr(update, 'message') and update.message:
                await update.message.reply_text(
                    get_message('error_occurred', language),
                    reply_markup=get_main_keyboard(language)
                )
            else:
                # Agar hech qaysi ham mavjud bo'lmasa, yangi xabar yuborish
                await context.bot.send_message(
                    chat_id=user.id,
                    text=get_message('error_occurred', language),
                    reply_markup=get_main_keyboard(language)
                )
    
    async def vote_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ovoz berish menyusi"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Loyihalarni olish (mavsum bo'yicha)
        projects = []
        active_season = self.db.get_active_season()
        if active_season:
            projects = self.db.get_projects_by_season(active_season['id'], db_user['region'])
        
        # Yangi qo'shilgan loyihalarni ham olish
        approved_projects = self.db.get_approved_projects()
        
        if not projects and not approved_projects:
            await update.message.reply_text(
                get_message('no_data', language)
            )
            return MAIN_MENU
        
        # Loyihalar ro'yxatini ko'rsatish
        message = get_message('select_project', language) + '\n\n'
        
        # Mavsum loyihalari
        if projects:
            message += "📅 *Mavsum loyihalari:*\n"
            for project in projects:
                message += f"🏗 {project['name']}\n"
                message += f"💰 {project['budget']:,} so'm\n"
                message += f"🏘 {project['region']}\n\n"
        
        # Yangi qo'shilgan loyihalar
        if approved_projects:
            message += "🆕 *Yangi qo'shilgan loyihalar:*\n"
            for project in approved_projects:
                message += f"🏗 {project['name']}\n"
                message += f"🔗 {project['link']}\n\n"
        
        message += "🗳 *Ovoz berish uchun quyidagi tugmalardan birini bosing:*"
        
        # Ovoz berish tugmalari bilan klaviatura yaratish
        keyboard = []
        
        # Mavsum loyihalari uchun tugmalar
        if projects:
            for project in projects:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🗳 {project['name']} uchun ovoz berdim",
                        callback_data=f"vote_project_{project['id']}"
                    ),
                    InlineKeyboardButton(
                        f"🔗 {project['name']} havolasini ochish",
                        url=project.get('link', '#')  # Agar link bo'lsa ochadi
                    )
                ])
        
        # Yangi loyihalar uchun tugmalar
        if approved_projects:
            for project in approved_projects:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🗳 {project['name']} uchun ovoz berdim",
                        callback_data=f"vote_project_{project['id']}"
                    ),
                    InlineKeyboardButton(
                        f"🔗 {project['name']} havolasini ochish",
                        url=project['link']
                    )
                ])
        
        # Orqaga qaytish tugmasi
        keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="back")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def balance_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Balans menyusi"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Balans ma'lumotlarini olish
        balance_info = get_message('balance_info', language, **{
            'balance': db_user['balance'],
            'pending': db_user['pending_balance'],
            'withdrawn': db_user['total_withdrawn'],
            'earned': db_user['total_earned']
        })
        
        await update.message.reply_text(
            balance_info,
            reply_markup=get_balance_keyboard(language)
        )
    
    async def withdrawal_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pul chiqarish menyusi"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        if db_user['balance'] < MIN_WITHDRAWAL:
            await update.message.reply_text(
                get_message('insufficient_balance', language)
            )
            return MAIN_MENU
        
        # Foiz hisobini avtomatik qilish
        commission_amount = int(db_user['balance'] * COMMISSION_RATE)
        net_amount = db_user['balance'] - commission_amount
        
        # Ma'lumotlarni ko'rsatish
        withdrawal_info = f"💰 *Balans:* {db_user['balance']:,} so'm\n"
        withdrawal_info += f"💸 *Komissiya ({int(COMMISSION_RATE * 100)}%):* {commission_amount:,} so'm\n"
        withdrawal_info += f"✅ *Chiqariladigan summa:* {net_amount:,} so'm\n\n"
        withdrawal_info += f"📱 *Pulni chiqarish uchun quyidagi usullardan birini tanlang:*"
        
        # Inline tugmalar bilan klaviatura
        keyboard = [
            [
                InlineKeyboardButton("💳 Karta raqami", callback_data="withdraw_card"),
                InlineKeyboardButton("📱 Telefon raqami", callback_data="withdraw_phone")
            ],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            withdrawal_info,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        # Conversation state ni WITHDRAWAL_ACCOUNT ga o'tkazish uchun
        # Bu yerda ConversationHandler.END qaytarmaymiz, chunki keyin handle_withdrawal da state o'zgartiramiz
        
        # Conversation state ni WITHDRAWAL_ACCOUNT ga o'tkazish
        return WITHDRAWAL_ACCOUNT
    
    async def referral_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Referal menyusi"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Referal statistikalarini olish
        referral_stats = self.db.get_referral_stats(db_user['id'])
        
        # Referal kodni tekshirish
        referral_code = db_user['referral_code']
        if not referral_code:
            # Agar referal kod yo'q bo'lsa, yangi yaratish
            referral_code = self.db.generate_new_referral_code(db_user['id'])
        
        # Referal ma'lumotlarini olish
        referral_link = f"https://t.me/{context.bot.username}?start=ref_{referral_code}"
        
        referral_info = get_message('referral_info', language, **{
            'referral_link': referral_link,
            'referrals_count': referral_stats['referrals_count'],
            'referral_earnings': referral_stats['referral_earnings']
        })
        
        await update.message.reply_text(referral_info)
    
    async def help_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yordam menyusi"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        help_text = get_message('help_text', language, **{
            'max_votes': MAX_VOTES_PER_SEASON,
            'vote_bonus': VOTE_BONUS,
            'referral_bonus': REFERRAL_BONUS,
            'referral_vote_bonus': VOTE_BONUS,
            'min_withdrawal': MIN_WITHDRAWAL,
            'commission': int(COMMISSION_RATE * 100)
        })
        
        await update.message.reply_text(help_text)
    
    async def profile_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Profil menyusi"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Referal statistikalarini olish
        referral_stats = self.db.get_referral_stats(db_user['id'])
        
        # Referal kodni tekshirish
        referral_code = db_user['referral_code']
        if not referral_code:
            # Agar referal kod yo'q bo'lsa, yangi yaratish
            referral_code = self.db.generate_new_referral_code(db_user['id'])
        
        # Ovozlar sonini olish
        active_season = self.db.get_active_season()
        total_votes = 0
        if active_season:
            total_votes = self.db.get_user_votes_count(db_user['id'], active_season['id'])
        
        profile_info = get_message('profile_info', language=language, **{
            'first_name': db_user['first_name'],
            'last_name': db_user['last_name'] or '',
            'username': db_user['username'] or 'N/A',
            'phone': db_user['phone'],
            'region': db_user['region'],
            'user_language': db_user['language'],
            'referral_code': referral_code,
            'referrals_count': referral_stats['referrals_count'],
            'total_votes': total_votes,
            'total_earned': db_user['total_earned']
        })
        
        await update.message.reply_text(profile_info)
    
    async def news_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yangiliklar menyusi"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Oxirgi yangilikni bazadan olish
        last_announcement = self.db.get_last_announcement(language)
        
        if last_announcement:
            # Yangilikni ko'rsatish
            await update.message.reply_text(
                get_message('news_display', language, **{
                    'title': last_announcement['title'],
                    'content': last_announcement['content'],
                    'created_at': last_announcement['created_at']
                }),
                parse_mode='Markdown'
            )
        else:
            # Yangiliklar yo'q
            await update.message.reply_text(
                get_message('news_empty', language)
            )
    
    async def balance_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Balans tarixi"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Balans tarixini ko'rsatish
        await update.message.reply_text(
            get_message('no_data', language)  # Hozirda tarix ko'rsatilmaydi
        )
    
    async def rules_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Qoidalar menyusi"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Qoidalarni ko'rsatish
        await update.message.reply_text(
            get_message('help_text', language, **{
                'max_votes': MAX_VOTES_PER_SEASON,
                'vote_bonus': VOTE_BONUS,
                'referral_bonus': REFERRAL_BONUS,
                'referral_vote_bonus': VOTE_BONUS,
                'min_withdrawal': MIN_WITHDRAWAL,
                'commission': int(COMMISSION_RATE * 100)
            })
        )
    
    async def admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin menyusi"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await update.message.reply_text(
            get_message('admin_menu', language),
            reply_markup=get_admin_keyboard(language)
        )
        
        return ADMIN_MENU
    
    async def admin_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin statistikalari"""
        user = update.effective_user
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return
        stats = self.db.get_statistics()
        stats_text = get_message('statistics_title', 'uz', **stats)
        await update.message.reply_text(
            stats_text,
            reply_markup=get_back_keyboard()
        )
    
    async def admin_ratings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin reytinglari - eng ko'p ovoz bergan foydalanuvchilar"""
        user = update.effective_user
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        top_voters = self.db.get_top_voters(10)
        if not top_voters:
            await update.message.reply_text(
                "📊 *Reytinglar*\n\n"
                "Hali hech kim ovoz bermagan.",
                parse_mode='Markdown',
                reply_markup=get_back_keyboard()
            )
            return
        
        ratings_text = "📊 *Eng ko'p ovoz bergan foydalanuvchilar*\n\n"
        for i, voter in enumerate(top_voters, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}️⃣"
            name = voter['first_name']
            telegram_id = voter['telegram_id']
            vote_count = voter['vote_count']
            ratings_text += f"{emoji} *{name}*\n"
            ratings_text += f"   🆔 ID: `{telegram_id}`\n"
            ratings_text += f"   🗳 Ovozlar: {vote_count} ta\n\n"
        
        await update.message.reply_text(
            ratings_text,
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )

    async def start_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast xabar yuborishni boshlash"""
        user = update.effective_user
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await update.message.reply_text(
            get_message('broadcast_start', language),
            parse_mode='Markdown',
            reply_markup=get_broadcast_cancel_keyboard()
        )
        
        return BROADCAST_MESSAGE

    async def broadcast_text_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Matn xabar qabul qilinganda"""
        return await self.handle_broadcast_message(update, context, 'text', update.message.text)

    async def broadcast_photo_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Rasm qabul qilinganda"""
        photo = update.message.photo[-1]  # Eng yuqori sifatli rasm
        caption = update.message.caption or ""
        return await self.handle_broadcast_message(update, context, 'photo', photo, caption)

    async def broadcast_video_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Video qabul qilinganda"""
        video = update.message.video
        caption = update.message.caption or ""
        return await self.handle_broadcast_message(update, context, 'video', video, caption)

    async def broadcast_document_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Hujjat qabul qilinganda"""
        document = update.message.document
        caption = update.message.caption or ""
        return await self.handle_broadcast_message(update, context, 'document', document, caption)

    async def broadcast_forwarded_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Forward qilingan xabar qabul qilinganda"""
        # Forward qilingan xabarni tekshirish va caption ni qisqartirish
        message = update.message
        caption = ""
        
        # Agar xabar caption ga ega bo'lsa, uni qisqartirish
        if message.caption:
            caption = message.caption
            # Telegram API cheklovi: caption 1024 belgidan oshmasligi kerak
            if len(caption) > 1024:
                caption = caption[:1021] + "..."
        
        # Agar xabar matnli bo'lsa, uni ham tekshirish
        if message.text and len(message.text) > 4096:
            # Matn juda uzun bo'lsa, uni qisqartirish
            context.user_data['original_text'] = message.text
            context.user_data['text_truncated'] = True
        
        return await self.handle_broadcast_message(update, context, 'forwarded', message, caption)

    async def handle_broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, message_type, content, caption=""):
        """Broadcast xabarni qayta ishlash"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Xabarni context'ga saqlash
        context.user_data['broadcast_type'] = message_type
        context.user_data['broadcast_content'] = content
        context.user_data['broadcast_caption'] = caption
        context.user_data['broadcast_message'] = update.message
        
        # Preview ko'rsatish
        preview_text = get_message('broadcast_preview', language)
        
        if message_type == 'text':
            preview_text += f"\n\n{content}"
        elif message_type in ['photo', 'video', 'document']:
            preview_text += f"\n\n📎 Fayl turi: {message_type.title()}"
            if caption:
                preview_text += f"\n📝 Izoh: {caption}"
        elif message_type == 'forwarded':
            preview_text += f"\n\n📤 Forward qilingan xabar"
            if update.message.text:
                text_preview = update.message.text
                if len(text_preview) > 100:
                    text_preview = text_preview[:97] + "..."
                preview_text += f"\n📝 Matn: {text_preview}"
            if caption:
                preview_text += f"\n📝 Caption: {caption}"
            if context.user_data.get('text_truncated'):
                preview_text += "\n⚠️ *Eslatma:* Matn juda uzun bo'lgani uchun qisqartirildi"
        
        await update.message.reply_text(
            preview_text,
            parse_mode='Markdown',
            reply_markup=get_broadcast_preview_keyboard()
        )
        
        return ConversationHandler.END

    async def confirm_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast xabarni tasdiqlash va yuborish"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await query.edit_message_text(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Yuborish jarayonini boshlash
        await query.edit_message_text(get_message('broadcast_sending', language))
        
        # Barcha foydalanuvchilarni olish
        all_users = self.db.get_all_active_users()
        if not all_users:
            await query.edit_message_text(get_message('broadcast_no_users', language))
            return
        
        sent_count = 0
        failed_count = 0
        blocked_count = 0
        
        # Xabarni yuborish
        for user_data in all_users:
            try:
                if context.user_data['broadcast_type'] == 'text':
                    await context.bot.send_message(
                        chat_id=user_data['telegram_id'],
                        text=context.user_data['broadcast_content'],
                        parse_mode='Markdown'
                    )
                    sent_count += 1
                elif context.user_data['broadcast_type'] == 'photo':
                    await context.bot.send_photo(
                        chat_id=user_data['telegram_id'],
                        photo=context.user_data['broadcast_content'].file_id,
                        caption=context.user_data['broadcast_caption'],
                        parse_mode='Markdown'
                    )
                    sent_count += 1
                elif context.user_data['broadcast_type'] == 'video':
                    await context.bot.send_video(
                        chat_id=user_data['telegram_id'],
                        video=context.user_data['broadcast_content'].file_id,
                        caption=context.user_data['broadcast_caption'],
                        parse_mode='Markdown'
                    )
                    sent_count += 1
                elif context.user_data['broadcast_type'] == 'document':
                    await context.bot.send_document(
                        chat_id=user_data['telegram_id'],
                        document=context.user_data['broadcast_content'].file_id,
                        caption=context.user_data['broadcast_caption'],
                        parse_mode='Markdown'
                    )
                    sent_count += 1
                elif context.user_data['broadcast_type'] == 'forwarded':
                    try:
                        # Forward qilingan xabarni yuborish
                        await context.bot.forward_message(
                            chat_id=user_data['telegram_id'],
                            from_chat_id=context.user_data['broadcast_message'].chat_id,
                            message_id=context.user_data['broadcast_message'].message_id
                        )
                        sent_count += 1
                    except telegram.error.BadRequest as e:
                        if "Message caption is too long" in str(e):
                            # Agar caption juda uzun bo'lsa, uni qisqartirib yuborish
                            message = context.user_data['broadcast_message']
                            if message.photo:
                                await context.bot.send_photo(
                                    chat_id=user_data['telegram_id'],
                                    photo=message.photo[-1].file_id,
                                    caption=context.user_data.get('broadcast_caption', '')[:1024] if context.user_data.get('broadcast_caption') else None
                                )
                            elif message.video:
                                await context.bot.send_video(
                                    chat_id=user_data['telegram_id'],
                                    video=message.video.file_id,
                                    caption=context.user_data.get('broadcast_caption', '')[:1024] if context.user_data.get('broadcast_caption') else None
                                )
                            elif message.document:
                                await context.bot.send_document(
                                    chat_id=user_data['telegram_id'],
                                    document=message.document.file_id,
                                    caption=context.user_data.get('broadcast_caption', '')[:1024] if context.user_data.get('broadcast_caption') else None
                                )
                            elif message.text:
                                # Matn juda uzun bo'lsa, uni qismlarga bo'lib yuborish
                                text = context.user_data.get('original_text', message.text)
                                if len(text) > 4096:
                                    # Matnni 4096 belgidan kichik qismlarga bo'lish
                                    chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
                                    for chunk in chunks:
                                        await context.bot.send_message(
                                            chat_id=user_data['telegram_id'],
                                            text=chunk
                                        )
                                        await asyncio.sleep(0.1)
                                else:
                                    await context.bot.send_message(
                                        chat_id=user_data['telegram_id'],
                                        text=text
                                    )
                            sent_count += 1
                        else:
                            # Boshqa xatoliklar
                            failed_count += 1
                            print(f"Forward xatoligi: {e}")
                    except Exception as e:
                        failed_count += 1
                        print(f"Forward xatoligi: {e}")
                
                # Kichik kechikish
                await asyncio.sleep(0.05)
                
            except telegram.error.Forbidden:
                # Foydalanuvchi botni bloklagan
                blocked_count += 1
            except Exception as e:
                # Boshqa xatoliklar
                failed_count += 1
                print(f"Broadcast xatoligi: {e}")
        
        # Natijani ko'rsatish
        result_text = get_message('broadcast_success', language).format(
            sent_count=sent_count,
            failed_count=failed_count,
            blocked_count=blocked_count
        )
        
        await query.edit_message_text(
            result_text,
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
        
        # Context'ni tozalash
        context.user_data.clear()

    async def cancel_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast xabarni bekor qilish"""
        user = update.effective_user or update.callback_query.from_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                get_message('broadcast_cancelled', language),
                reply_markup=get_back_keyboard()
            )
        else:
            await update.message.reply_text(
                get_message('broadcast_cancelled', language),
                reply_markup=get_back_keyboard()
            )
        
        # Context'ni tozalash
        context.user_data.clear()
        return ConversationHandler.END

    async def start_news_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yangilik yaratishni boshlash"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return ConversationHandler.END
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await update.message.reply_text(
            get_message('news_creation_start', language),
            parse_mode='Markdown',
            reply_markup=get_news_cancel_keyboard()
        )
        
        return NEWS_TITLE

    async def news_title_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yangilik sarlavhasi qabul qilinganda"""
        title = update.message.text
        context.user_data['news_title'] = title
        
        await update.message.reply_text(
            get_message('news_content_request', language),
            parse_mode='Markdown',
            reply_markup=get_news_cancel_keyboard()
        )
        
        return NEWS_CONTENT

    async def news_content_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yangilik matni qabul qilinganda"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        content = update.message.text
        title = context.user_data['news_title']
        
        # Content ni context ga saqlash
        context.user_data['news_content'] = content
        
        # Yangilik preview ko'rsatish
        preview_text = get_message('news_preview', language, **{
            'title': title,
            'content': content
        })
        
        # Tasdiqlash klaviaturasi
        keyboard = [
            [
                InlineKeyboardButton("✅ Saqlash", callback_data="approve_news"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data="reject_news")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            preview_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        return NEWS_APPROVAL

    async def news_approval_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yangilik tasdiqlash yoki rad etish"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        if query.data == "approve_news":
            # Yangilikni saqlash
            title = context.user_data['news_title']
            content = context.user_data.get('news_content', '')
            
            # Bazaga saqlash
            announcement_id = self.db.create_announcement(
                title=title,
                content=content,
                language=language,
                created_by=db_user['id']
            )
            
            if announcement_id:
                await query.edit_message_text(
                    get_message('news_saved', language),
                    reply_markup=get_back_keyboard()
                )
            else:
                await query.edit_message_text(
                    get_message('news_save_error', language),
                    reply_markup=get_back_keyboard()
                )
        else:
            # Bekor qilish
            await query.edit_message_text(
                get_message('news_cancelled', language),
                reply_markup=get_back_keyboard()
            )
        
        # Context'ni tozalash
        context.user_data.clear()
        return ConversationHandler.END

    async def cancel_news_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yangilik yaratishni bekor qilish"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await query.edit_message_text(
            get_message('news_cancelled', language),
            reply_markup=get_back_keyboard()
        )
        
        # Context'ni tozalash
        context.user_data.clear()
        return ConversationHandler.END
    
    async def admin_withdrawals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin pul chiqarish so'rovlari"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return
        
        # Kutilayotgan so'rovlarni olish
        withdrawals = self.db.get_pending_withdrawals()
        
        if not withdrawals:
            await update.message.reply_text(
                get_message('no_data', 'uz'),
                reply_markup=get_back_keyboard()
            )
            return
        
        # Birinchi so'rovni ko'rsatish
        withdrawal = withdrawals[0]
        withdrawal_text = get_message('withdrawal_request_detail', 'uz', **{
            'id': withdrawal['id'],
            'user_name': withdrawal['first_name'],
            'phone': withdrawal['phone'],
            'amount': withdrawal['amount'],
            'commission': withdrawal['commission'],
            'net_amount': withdrawal['net_amount'],
            'method': withdrawal['method'],
            'account_details': withdrawal['account_details'],
            'created_at': withdrawal['created_at']
        })
        
        await update.message.reply_text(
            withdrawal_text,
            reply_markup=get_withdrawal_action_keyboard(withdrawal['id'])
        )
    
    async def admin_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin loyiha boshqaruvi"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return
        
        await update.message.reply_text(
            "🗳 Loyiha boshqaruvi",
            reply_markup=get_admin_project_management_keyboard()
        )
    
    async def admin_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin foydalanuvchi boshqaruvi"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return
        
        await update.message.reply_text(
            "👥 Foydalanuvchi boshqaruvi",
            reply_markup=get_admin_user_management_keyboard()
        )
    
    async def admin_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin broadcast"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return
        
        await update.message.reply_text(
            get_message('broadcast_message', 'uz'),
            reply_markup=get_cancel_keyboard()
        )
    
    async def admin_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin sozlamalar"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return
        
        await update.message.reply_text(
            "⚙️ Sozlamalar",
            reply_markup=get_back_keyboard()
        )
    
    async def admin_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin eksport"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return
        
        await update.message.reply_text(
            "📤 Eksport",
            reply_markup=get_export_keyboard()
        )
    
    async def admin_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin loglar"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return
        
        await update.message.reply_text(
            "🧾 Loglar/Audit",
            reply_markup=get_back_keyboard()
        )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tugma bosilganda"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith('vote_'):
            if data.startswith('vote_approve_') or data.startswith('vote_reject_'):
                # Admin ovoz berishni tasdiqlash yoki rad etish
                await self.handle_vote_approval(update, context)
            else:
                # Mavsum loyihalari uchun ovoz berish
                await self.handle_vote(update, context, data)
        elif data.startswith('withdraw_'):
            if data in ['withdraw_card', 'withdraw_phone']:
                await self.handle_withdrawal(update, context)
            else:
                await self.handle_withdrawal(update, context)
        elif data.startswith('withdrawal_completed_'):
            await self.handle_withdrawal_completed(update, context)
        elif data.startswith('withdrawal_rejected_'):
            await self.handle_withdrawal_rejected(update, context)
        elif data.startswith('approve_withdrawal_'):
            await self.approve_withdrawal(update, context)
        elif data == 'back':
            await self.back_to_main(update, context)
        elif data == 'admin_edit_projects':
            await self.admin_edit_projects(update, context)
        elif data == 'admin_delete_projects':
            await self.admin_delete_projects(update, context)
        elif data == 'admin_seasons':
            await self.admin_seasons(update, context)
        elif data == 'admin_rating':
            await self.admin_rating(update, context)
        elif data == 'admin_back':
            await self.admin_menu(update, context)
        elif data == 'cancel_edit':
            return await self.cancel_edit_project(update, context)
        elif data == 'confirm_broadcast':
            return await self.confirm_broadcast(update, context)
        elif data == 'cancel_broadcast':
            return await self.cancel_broadcast(update, context)
        elif data.startswith('confirm_delete_project_'):
            await self.confirm_delete_project(update, context)
        elif data.startswith('delete_project_'):
            await self.delete_project_confirmed(update, context)
        elif data == 'cancel_delete_project':
            await self.cancel_delete_project(update, context)
        elif data == 'back':
            await query.answer()
            await query.edit_message_text(
                get_message('back_to_main', language),
                reply_markup=get_back_keyboard()
            )
    
    async def handle_approved_project_vote(self, update: Update, context: ContextTypes.DEFAULT_TYPE, project_id: int | None = None):
        """Yangi loyihalar uchun ovoz berish"""
        query = update.callback_query
        await query.answer()  # Callback query ni javoblash
        
        # Agar project_id berilmagan bo'lsa, callback_data dan olinadi
        if project_id is None and query and getattr(query, 'data', None):
            try:
                project_id = int(query.data.split('_')[2])
            except Exception:
                await query.edit_message_text("Xato: loyiha ID topilmadi.")
                return ConversationHandler.END
        
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Loyihani bazadan olish
        approved_projects = self.db.get_approved_projects()
        project = None
        for p in approved_projects:
            if p['id'] == project_id:
                project = p
                break
        
        if not project:
            await query.answer("Loyiha topilmadi!")
            return
        
        # Avval loyiha havolasini ko'rsatish va screenshot so'rash
        context.user_data['voted_project_id'] = project_id
        context.user_data['voted_project_name'] = project['name']
        context.user_data['voted_project_link'] = project['link']
        
        await query.edit_message_text(
            f"🏗 *{project['name']}* loyihasi uchun ovoz berdingiz!\n\n"
            f"🔗 *Loyiha havolasi:* {project['link']}\n\n"
            f"📸 *Ovoz berganingizni tasdiqlovchi screenshot yuboring!*\n\n"
            f"📱 Screenshot da quyidagilar ko'rinishi kerak:\n"
            f"• Kelgan SMS xabari\n"
            f"• Ovoz berilgan holat\n"
            f"• Loyiha havolasi ochilgan\n\n"
            f"📤 Skrinshot rasmni yuboring!",
            parse_mode='Markdown',
            reply_markup=get_screenshot_keyboard()
        )
        
        return SCREENSHOT_REQUEST
    
    async def start_screenshot_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Screenshot so'rashni boshlash"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await query.edit_message_text(
            f"📸 *Ovoz berganingizni tasdiqlovchi screenshot yuboring!*\n\n"
            f"📱 Screenshot da quyidagilar ko'rinishi kerak:\n"
            f"• Kelgan SMS xabari\n"
            f"• Ovoz berilgan holat\n"
            f"• Loyiha havolasi ochilgan\n\n"
            f"📤 Skrinshot rasmni yuboring!",
            parse_mode='Markdown',
            reply_markup=get_screenshot_keyboard()
        )
        
        return SCREENSHOT_REQUEST
    
    async def screenshot_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Birinchi screenshot qabul qilinganda"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Rasmni saqlash
        photo = update.message.photo[-1]  # Eng yuqori sifatli rasm
        context.user_data['screenshot_1'] = photo.file_id
        
        await update.message.reply_text(
            f"⚠️ *Iltimos, ovoz berganingizni aniq tasdiqlovchi screenshot yuboring!*\n\n"
            f"📱 Screenshot da quyidagilar aniq ko'rinishi kerak:\n"
            f"• Kelgan SMS xabari\n"
            f"• Ovoz berilgan holat\n"
            f"• Loyiha havolasi ochilgan\n"
            f"• Ovoz berish tasdiqlanishi\n\n"
            f"📤 Skrinshot rasmni yuboring!",
            parse_mode='Markdown',
            reply_markup=get_screenshot_keyboard()
        )
        
        return SCREENSHOT_RECEIVED
    
    async def screenshot_verification(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ikkinchi screenshot qabul qilinganda"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Rasmni saqlash
        photo = update.message.photo[-1]
        context.user_data['screenshot_2'] = photo.file_id
        
        await update.message.reply_text(
            f"✅ *Ma'lumotlar tekshirish uchun Admin ga yuborildi!*\n\n"
            f"💰 *Tez orada ovoz bergan bo'lsangiz hisobingiz to'ldiriladi!*\n\n"
            f"📋 *Yuborilgan ma'lumotlar:*\n"
            f"• Foydalanuvchi: {user.first_name} {user.last_name or ''}\n"
            f"• Loyiha: {context.user_data.get('voted_project_name', 'N/A')}\n"
            f"• Screenshotlar: 2 ta\n\n"
            f"⏳ Admin tasdiqlashini kuting...",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
        
        # Admin kanaliga yuborish
        await self.send_vote_verification_to_admin(update, context)
        
        # Context ni tozalash
        context.user_data.clear()
        return ConversationHandler.END
    
    async def screenshot_final_verification(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Uchinchi screenshot qabul qilinganda"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Rasmni saqlash
        photo = update.message.photo[-1]
        context.user_data['screenshot_3'] = photo.file_id
        
        await update.message.reply_text(
            f"✅ *Ma'lumotlar tekshirish uchun Admin ga yuborildi!*\n\n"
            f"💰 *Tez orada ovoz bergan bo'lsangiz hisobingiz to'ldiriladi!*\n\n"
            f"📋 *Yuborilgan ma'lumotlar:*\n"
            f"• Foydalanuvchi: {user.first_name} {user.last_name or ''}\n"
            f"• Loyiha: {context.user_data.get('voted_project_name', 'N/A')}\n"
            f"• Screenshotlar: 3 ta\n\n"
            f"⏳ Admin tasdiqlashini kuting...",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
        
        # Admin kanaliga yuborish
        await self.send_vote_verification_to_admin(update, context)
        
        # Context ni tozalash
        context.user_data.clear()
        return ConversationHandler.END
    
    async def screenshot_text_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Matn yuborilganda screenshot so'rash"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await update.message.reply_text(
            f"❌ *Iltimos, rasm yuboring!*\n\n"
            f"📸 Screenshot da quyidagilar ko'rinishi kerak:\n"
            f"• Kelgan SMS xabari\n"
            f"• Ovoz berilgan holat\n"
            f"• Loyiha havolasi ochilgan\n\n"
            f"📤 Skrinshot rasmni yuboring!",
            parse_mode='Markdown',
            reply_markup=get_screenshot_keyboard()
        )
        
        return context.user_data.get('current_state', SCREENSHOT_REQUEST)
    
    async def cancel_screenshot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Screenshot bekor qilish"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await query.edit_message_text(
            f"❌ *Screenshot yuborish bekor qilindi!*\n\n"
            f"⚠️ Ovoz berish uchun screenshot talab qilinadi.\n"
            f"Keyinroq qayta urinib ko'ring.",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
        
        # Context ni tozalash
        context.user_data.clear()
        return ConversationHandler.END
    
    async def send_vote_verification_to_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ovoz berish tasdiqlashini admin kanaliga yuborish"""
        try:
            user = update.effective_user
            db_user = self.db.get_user(user.id)
            
            # Admin kanal ID sini config dan olish
            admin_channel_id = ADMIN_CHANNEL_ID
            if not admin_channel_id:
                print("Admin kanal ID topilmadi!")
                return
            
            # Ma'lumotlarni tayyorlash
            user_info = f"👤 *Foydalanuvchi:* {user.first_name} {user.last_name or ''}\n"
            user_info += f"🆔 *ID:* {user.id}\n"
            user_info += f"📱 *Username:* @{user.username or 'N/A'}\n"
            phone = db_user['phone'] if ('phone' in db_user.keys() and db_user['phone']) else 'N/A'
            region = db_user['region'] if ('region' in db_user.keys() and db_user['region']) else 'N/A'
            user_info += f"📞 *Telefon:* {phone}\n"
            user_info += f"🏘 *Hudud:* {region}\n\n"
            
            project_info = f"🏗 *Loyiha:* {context.user_data.get('voted_project_name', 'N/A')}\n"
            project_info += f"🔗 *Havola:* {context.user_data.get('voted_project_link', 'N/A')}\n\n"
            
            screenshot_info = f"📸 *Screenshotlar:* {len([k for k in context.user_data.keys() if k.startswith('screenshot_')])} ta\n\n"
            
            message_text = f"🗳 *YANGI OVOZ BERISH TASDIQLASHI*\n\n"
            message_text += user_info + project_info + screenshot_info
            message_text += f"⏰ *Vaqt:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            message_text += f"✅ *Tasdiqlash uchun tugmani bosing:*"
            
            # Screenshotlarni yuborish
            media_group = []
            for i in range(1, 4):
                screenshot_key = f'screenshot_{i}'
                if screenshot_key in context.user_data:
                    media_group.append(InputMediaPhoto(
                        media=context.user_data[screenshot_key],
                        caption=f"Screenshot {i}" if i == 1 else ""
                    ))
            
            # Screenshotlarni yuborish
            if media_group:
                await self.application.bot.send_media_group(
                    chat_id=admin_channel_id,
                    media=media_group
                )
            
            # Asosiy xabarni yuborish
            await self.application.bot.send_message(
                chat_id=admin_channel_id,
                text=message_text,
                parse_mode='Markdown',
                reply_markup=get_vote_approval_keyboard(user.id, context.user_data.get('voted_project_id') or 0)
            )
            
            print(f"Ovoz berish tasdiqlashi admin kanaliga yuborildi: {user.id}")
            
        except Exception as e:
            print(f"Admin kanaliga yuborishda xato: {e}")
            import traceback
            traceback.print_exc()
    
    async def handle_vote_approval(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin ovoz berishni tasdiqlash yoki rad etish"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        action, user_id, project_id = data.split('_')[1:]
        user_id = int(user_id)
        project_id = int(project_id)
        
        if action == 'approve':
            # Foydalanuvchining database ID sini olish
            db_user = self.db.get_user(user_id)
            if not db_user:
                await query.edit_message_text(
                    f"❌ *Xato yuz berdi!*\n\n"
                    f"Foydalanuvchi topilmadi: {user_id}",
                    parse_mode='Markdown'
                )
                return
            
            # Ovoz berishni tasdiqlash va bonus berish
            success = self.db.add_balance(db_user['id'], VOTE_BONUS, 'vote_bonus', f'Loyiha uchun ovoz berish tasdiqlandi')
            
            # Ovoz berishni balance_history ga qo'shish (payment type bilan)
            if success:
                self.db.add_payment_record(db_user['id'], VOTE_BONUS, 'payment', f'Loyiha uchun ovoz berish tasdiqlandi', 'approved')
            
            if success:
                # Foydalanuvchiga xabar yuborish
                try:
                    await self.application.bot.send_message(
                        chat_id=user_id,
                        text=f"🎉 *Ovoz berishingiz tasdiqlandi!*\n\n"
                             f"💰 *Bonus:* {VOTE_BONUS} so'm\n"
                             f"✅ *Hisobingiz to'ldirildi!*\n\n"
                             f"Rahmat! Loyihani qo'llab-quvvatlaganingiz uchun!",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    print(f"Foydalanuvchiga xabar yuborishda xato: {e}")
                
                # Admin xabarini yangilash
                await query.edit_message_text(
                    f"✅ *Ovoz berish tasdiqlandi!*\n\n"
                    f"👤 Foydalanuvchi: {user_id}\n"
                    f"💰 Bonus: {VOTE_BONUS} so'm\n"
                    f"✅ Hisob to'ldirildi",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(
                    f"❌ *Xato yuz berdi!*\n\n"
                    f"Ovoz berishni tasdiqlashda muammo bo'ldi.",
                    parse_mode='Markdown'
                )
        
        elif action == 'reject':
            # Ovoz berishni rad etish
            await query.edit_message_text(
                f"❌ *Ovoz berish rad etildi!*\n\n"
                f"👤 Foydalanuvchi: {user_id}\n"
                f"⚠️ Screenshotlar yetarli emas yoki noto'g'ri",
                parse_mode='Markdown'
            )
            
            # Foydalanuvchiga xabar yuborish
            try:
                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ *Ovoz berishingiz rad etildi!*\n\n"
                         f"⚠️ Screenshotlar yetarli emas yoki noto'g'ri.\n"
                         f"📸 Iltimos, aniq screenshot yuboring.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"Foydalanuvchiga xabar yuborishda xato: {e}")
    
    async def handle_vote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ovoz berishni boshqarish"""
        query = update.callback_query
        data = query.data
        
        if data.startswith('vote_yes_'):
            project_id = int(data.split('_')[2])
            await self.process_vote(update, context, project_id, True)
        elif data.startswith('vote_no_'):
            await query.edit_message_text(
                get_message('operation_cancelled', 'uz'),
                reply_markup=get_back_keyboard()
            )
    
    async def process_vote(self, update: Update, context: ContextTypes.DEFAULT_TYPE, project_id: int, confirmed: bool):
        """Ovozni qayta ishlash"""
        query = update.callback_query
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        if not confirmed:
            return
        
        # Ovoz berish logikasi
        active_season = self.db.get_active_season()
        if not active_season:
            await query.edit_message_text(
                get_message('no_active_season', language),
                reply_markup=get_back_keyboard()
            )
            return
        
        # Ovoz cheklovlarini tekshirish
        votes_count = self.db.get_user_votes_count(db_user['id'], active_season['id'])
        if votes_count >= MAX_VOTES_PER_SEASON:
            await query.edit_message_text(
                get_message('vote_limit_reached', language, max_votes=MAX_VOTES_PER_SEASON),
                reply_markup=get_back_keyboard()
            )
            return
        
        # Ovoz qo'shish
        success = self.db.add_vote(db_user['id'], project_id, active_season['id'])
        
        if success:
            await query.edit_message_text(
                get_message('vote_success', language, bonus=VOTE_BONUS),
                reply_markup=get_back_keyboard()
            )
        else:
            await query.edit_message_text(
                get_message('vote_already', language),
                reply_markup=get_back_keyboard()
            )
    
    async def handle_withdrawal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pul chiqarish usulini tanlash"""
        query = update.callback_query
        await query.answer()
        
        method = query.data.split('_')[1]
        context.user_data['withdrawal_method'] = method
        
        # Foydalanuvchi ma'lumotlarini olish
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Foiz hisobini avtomatik qilish
        commission_amount = int(db_user['balance'] * COMMISSION_RATE)
        net_amount = db_user['balance'] - commission_amount
        
        method_names = {
            'card': 'karta raqami',
            'phone': 'telefon raqami'
        }
        
        format_examples = {
            'card': 'Masalan: 8600123456789012 (16 xonali raqam)',
            'phone': 'Masalan: +998901234567 (+998 + 9 xonali raqam)'
        }
        
        # Ma'lumotlarni ko'rsatish
        withdrawal_info = f"💰 *Balans:* {db_user['balance']:,} so'm\n"
        withdrawal_info += f"💸 *Komissiya ({int(COMMISSION_RATE * 100)}%):* {commission_amount:,} so'm\n"
        withdrawal_info += f"✅ *Chiqariladigan summa:* {net_amount:,} so'm\n\n"
        withdrawal_info += f"📝 *Iltimos, {method_names.get(method, method)}ni kiriting:*\n"
        withdrawal_info += f"📋 {format_examples.get(method, '')}"
        
        # Context ga ma'lumotlarni saqlash
        context.user_data['withdrawal_amount'] = db_user['balance']
        context.user_data['commission_amount'] = commission_amount
        context.user_data['net_amount'] = net_amount
        
        await query.edit_message_text(
            withdrawal_info,
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        
        return WITHDRAWAL_ACCOUNT
    
    async def approve_withdrawal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pul chiqarish so'rovini tasdiqlash"""
        query = update.callback_query
        await query.answer()
        
        withdrawal_id = int(query.data.split('_')[2])
        
        # So'rovni tasdiqlash
        self.db.approve_withdrawal(withdrawal_id)
        
        # Foydalanuvchiga pul o'tkazilgani bo'yicha xabar yuborish
        try:
            withdrawal_info = self.db.get_withdrawal_notification(withdrawal_id)
            print(f"DEBUG: withdrawal_info = {withdrawal_info}")  # Debug uchun
            if withdrawal_info and 'telegram_id' in withdrawal_info:
                telegram_id = withdrawal_info['telegram_id']
                language = withdrawal_info['language'] if 'language' in withdrawal_info else 'uz'
                print(f"DEBUG: telegram_id = {telegram_id}, language = {language}")  # Debug uchun
                
                # Foydalanuvchiga xabar matni
                notification_text = get_message('withdrawal_completed', language).format(
                    amount=withdrawal_info['amount'],
                    method=withdrawal_info['method'],
                    account=withdrawal_info['account_details'],
                    date=(withdrawal_info['processed_at'] or withdrawal_info['created_at'])
                )
                print(f"DEBUG: notification_text = {notification_text}")  # Debug uchun
                
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=notification_text
                )
                print(f"DEBUG: Xabar yuborildi! chat_id={telegram_id}")  # Debug uchun
            else:
                print(f"DEBUG: withdrawal_info yoki telegram_id topilmadi: {withdrawal_info}")
        except Exception as e:
            print(f"Foydalanuvchiga xabar yuborishda xato: {e}")
            import traceback
            traceback.print_exc()  # To'liq xatolik ma'lumotini ko'rsatish
        
        await query.edit_message_text(
            get_message('withdrawal_approved', 'uz'),
            reply_markup=get_back_keyboard()
        )
    
    async def reject_withdrawal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pul chiqarish so'rovini rad etish"""
        query = update.callback_query
        await query.answer()
        
        withdrawal_id = int(query.data.split('_')[2])
        
        # So'rovni rad etish
        # Bu yerda rad etish logikasi bo'lishi kerak
        
        await query.edit_message_text(
            get_message('withdrawal_rejected', 'uz'),
            reply_markup=get_back_keyboard()
        )
    
    async def back_to_main(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Asosiy menyuga qaytish"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Admin foydalanuvchilar uchun admin klaviatura
        if user.id in ADMIN_IDS or user.id in SUPER_ADMIN_IDS:
            keyboard = get_admin_main_keyboard(language)
        else:
            keyboard = get_main_keyboard(language)
        
        text = get_message('main_menu', language)
        
        if update.callback_query:
            # Callback dan kelgan bo'lsa, edit qilib, alohida yangi xabar jo'natamiz (reply_markup bilan)
            try:
                await update.callback_query.edit_message_text(text)
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=keyboard)
            except Exception:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=keyboard)
        else:
            await update.message.reply_text(text, reply_markup=keyboard)
        
        return MAIN_MENU
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yordam buyrug'i"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language'] if db_user else 'uz'
        
        await update.message.reply_text(
            get_message('commands_help', language),
            parse_mode='Markdown'
        )
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin buyrug'i"""
        await self.admin_menu(update, context)
    
    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Profil ma'lumotlari buyrug'i"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        
        if not db_user:
            await update.message.reply_text("❌ Siz ro'yxatdan o'tmagansiz!")
            return
        
        language = db_user['language']
        
        # Referal statistikalarini olish
        referral_stats = self.db.get_referral_stats(db_user['id'])
        
        # Ovozlar sonini olish (mavsum bo'yicha)
        active_season = self.db.get_active_season()
        total_votes = 0
        if active_season:
            total_votes = self.db.get_user_votes_count(db_user['id'], active_season['id'])
        
        profile_text = get_message('profile_command', language, **{
            'first_name': db_user['first_name'] or 'Noma\'lum',
            'last_name': db_user['last_name'] or '',
            'username': db_user['username'] or 'Noma\'lum',
            'phone': db_user['phone'] or 'Noma\'lum',
            'region': db_user['region'] or 'Noma\'lum',
            'user_language': 'O\'zbekcha' if language == 'uz' else 'Русский',
            'referral_code': db_user['referral_code'] or 'Noma\'lum',
            'referrals_count': referral_stats['referrals_count'],
            'total_votes': total_votes,
            'total_earned': db_user['total_earned']
        })
        
        await update.message.reply_text(
            profile_text,
            parse_mode='Markdown'
        )
    
    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Balans ma'lumotlari buyrug'i"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        
        if not db_user:
            await update.message.reply_text("❌ Siz ro'yxatdan o'tmagansiz!")
            return
        
        language = db_user['language']
        
        balance_text = get_message('balance_command', language, **{
            'balance': db_user['balance'],
            'pending': db_user['pending_balance'],
            'withdrawn': db_user['total_withdrawn'],
            'earned': db_user['total_earned']
        })
        
        await update.message.reply_text(
            balance_text,
            parse_mode='Markdown'
        )
    
    async def admin_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin loyiha boshqaruvi"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.message.reply_text(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await update.message.reply_text(
            get_message('admin_projects_menu', language),
            reply_markup=get_admin_project_management_keyboard()
        )
    
    async def admin_new_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yangi loyiha qo'shish - eski versiya"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.callback_query.answer(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await update.callback_query.edit_message_text(
            get_message('admin_new_project_form', language),
            reply_markup=get_back_keyboard()
        )
    
    async def start_new_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yangi loyiha qo'shishni boshlash"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.callback_query.answer(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Loyiha nomini so'rash
        await update.callback_query.edit_message_text(
            get_message('project_name_request', language),
            reply_markup=get_cancel_keyboard()
        )
        
        return NEW_PROJECT_NAME
    
    async def project_name_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyiha nomi qabul qilinganda"""
        project_name = update.message.text
        context.user_data['project_name'] = project_name
        
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Loyiha havolasini so'rash
        await update.message.reply_text(
            get_message('project_link_request', language),
            reply_markup=get_cancel_keyboard()
        )
        
        return NEW_PROJECT_LINK
    
    async def project_link_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyiha havolasi qabul qilinganda"""
        project_link = update.message.text
        context.user_data['project_link'] = project_link
        
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Admin tasdiqlash uchun ma'lumotlarni ko'rsatish
        project_info = get_message('project_approval_request', language, **{
            'project_name': context.user_data['project_name'],
            'project_link': context.user_data['project_link']
        })
        
        await update.message.reply_text(
            project_info,
            reply_markup=get_project_approval_keyboard()
        )
        
        return NEW_PROJECT_APPROVAL
    
    async def project_approval_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyiha tasdiqlash yoki rad etish"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        action = query.data.split('_')[0]  # 'approve' yoki 'reject'
        
        if action == 'approve':
            # Loyihani tasdiqlash va barcha foydalanuvchilarga yuborish
            project_name = context.user_data['project_name']
            project_link = context.user_data['project_link']
            
            # Loyihani bazaga saqlash
            project_data = {
                'name': project_name,
                'link': project_link,
                'status': 'approved',
                'approved_by': user.id,
                'approved_at': datetime.now()
            }
            
            success = self.db.create_approved_project(project_data)
            
            if success:
                # Barcha foydalanuvchilarga xabar yuborish
                await self.broadcast_project_to_all_users(project_name, project_link, language)
                
                await query.edit_message_text(
                    get_message('project_approved_success', language),
                    reply_markup=get_back_keyboard()
                )
            else:
                await query.edit_message_text(
                    get_message('project_approval_failed', language),
                    reply_markup=get_back_keyboard()
                )
        else:
            # Loyihani rad etish
            await query.edit_message_text(
                get_message('project_rejected', language),
                reply_markup=get_back_keyboard()
            )
        
        # Context ni tozalash
        context.user_data.clear()
        return ConversationHandler.END
    
    async def cancel_new_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yangi loyiha qo'shishni bekor qilish"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await update.callback_query.edit_message_text(
            get_message('project_creation_cancelled', language),
            reply_markup=get_back_keyboard()
        )
        
        # Context ni tozalash
        context.user_data.clear()
        return ConversationHandler.END
    
    async def admin_edit_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyihalarni tahrirlash"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.callback_query.answer(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Mavjud loyihalarni olish
        active_season = self.db.get_active_season()
        projects = []
        if active_season:
            projects = self.db.get_projects_by_season(active_season['id'])
        
        # Yangi qo'shilgan loyihalarni ham olish
        approved_projects = self.db.get_approved_projects()
        
        if not projects and not approved_projects:
            await update.callback_query.edit_message_text(
                get_message('admin_no_projects', language),
                reply_markup=get_back_keyboard()
            )
            return
        
        # Loyihalar ro'yxatini ko'rsatish
        projects_text = "📋 *Mavjud loyihalar:*\n\n"
        
        # Mavsum loyihalari
        if projects:
            projects_text += "📅 *Mavsum loyihalari:*\n"
            for project in projects:
                projects_text += f"🏗 *{project['name']}*\n"
                projects_text += f"💰 {project['budget']:,} so'm\n"
                projects_text += f"🏘 {project['region']}\n"
                projects_text += f"🆔 ID: {project['id']}\n\n"
        
        # Yangi qo'shilgan loyihalar
        if approved_projects:
            projects_text += "🆕 *Yangi qo'shilgan loyihalar:*\n"
            for project in approved_projects:
                projects_text += f"🏗 *{project['name']}*\n"
                projects_text += f"🔗 {project['link']}\n"
                projects_text += f"🆔 ID: {project['id']}\n\n"
        
        projects_text += "✏️ *Tahrirlash uchun quyidagi tugmalardan birini bosing:*"
        
        # Tahrirlash tugmalari bilan klaviatura yaratish
        keyboard = []
        
        # Mavsum loyihalari uchun tugmalar
        if projects:
            for project in projects:
                keyboard.append([
                    InlineKeyboardButton(
                        f"✏️ {project['name']} nomini tahrirlash",
                        callback_data=f"edit_name_{project['id']}"
                    )
                ])
                keyboard.append([
                    InlineKeyboardButton(
                        f"🔗 {project['name']} havolasini tahrirlash",
                        callback_data=f"edit_link_{project['id']}"
                    )
                ])
        
        # Yangi loyihalar uchun tugmalar
        if approved_projects:
            for project in approved_projects:
                keyboard.append([
                    InlineKeyboardButton(
                        f"✏️ {project['name']} nomini tahrirlash",
                        callback_data=f"edit_name_{project['id']}"
                    )
                ])
                keyboard.append([
                    InlineKeyboardButton(
                        f"🔗 {project['name']} havolasini tahrirlash",
                        callback_data=f"edit_link_{project['id']}"
                    )
                ])
        
        # Orqaga qaytish tugmasi
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            projects_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def admin_seasons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mavsumlarni boshqarish"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.callback_query.answer(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await update.callback_query.edit_message_text(
            get_message('admin_seasons_menu', language),
            reply_markup=get_back_keyboard()
        )
    
    async def admin_rating(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reytinglarni ko'rish"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.callback_query.answer(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await update.callback_query.edit_message_text(
            get_message('admin_rating_menu', language),
            reply_markup=get_back_keyboard()
        )
    
    async def broadcast_project_to_all_users(self, project_name: str, project_link: str, language: str):
        """Loyihani barcha foydalanuvchilarga yuborish"""
        try:
            # Barcha foydalanuvchilarni olish
            users = self.db.get_all_users()
            
            message = get_message('new_project_announcement', language, **{
                'project_name': project_name,
                'project_link': project_link
            })
            
            success_count = 0
            for user in users:
                try:
                    await self.application.bot.send_message(
                        chat_id=user['telegram_id'],
                        text=message,
                        parse_mode='Markdown'
                    )
                    success_count += 1
                except Exception as e:
                    print(f"Foydalanuvchiga xabar yuborishda xato: {e}")
                    continue
            
            print(f"Loyiha {success_count} ta foydalanuvchiga yuborildi")
            
        except Exception as e:
            print(f"Loyihani yuborishda xato: {e}")
    
    async def withdrawal_account_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pul chiqarish uchun hisob ma'lumotlari qabul qilinganda"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        account_details = update.message.text
        withdrawal_method = context.user_data.get('withdrawal_method')
        
        # Format tekshirish
        if withdrawal_method == 'card':
            # Karta raqami tekshirish - faqat raqamlar va 16 xonali
            if not account_details.isdigit() or len(account_details) != 16:
                await update.message.reply_text(
                    "❌ *Noto'g'ri karta raqami!*\n\n"
                    "Karta raqami faqat raqamlardan iborat bo'lishi va 16 xonali bo'lishi kerak.\n"
                    "Masalan: 8600123456789012\n\n"
                    "Iltimos, to'g'ri formatda kiriting:",
                    parse_mode='Markdown',
                    reply_markup=get_cancel_keyboard()
                )
                return WITHDRAWAL_ACCOUNT
        
        elif withdrawal_method == 'phone':
            # Telefon raqami tekshirish - +998 va 9 xonali raqam
            if not account_details.startswith('+998') or len(account_details) != 13 or not account_details[4:].isdigit():
                await update.message.reply_text(
                    "❌ *Noto'g'ri telefon raqami!*\n\n"
                    "Telefon raqami quyidagi formatda bo'lishi kerak:\n"
                    "Masalan: +998901234567\n\n"
                    "Iltimos, to'g'ri formatda kiriting:",
                    parse_mode='Markdown',
                    reply_markup=get_cancel_keyboard()
                )
                return WITHDRAWAL_ACCOUNT
        
        # Pul chiqarish so'rovini yaratish
        withdrawal_data = {
            'user_id': db_user['id'],
            'amount': context.user_data['withdrawal_amount'],
            'commission': context.user_data['commission_amount'],
            'net_amount': context.user_data['net_amount'],
            'method': withdrawal_method,
            'account_details': account_details,
            'status': 'pending'
        }
        
        success = self.db.create_withdrawal_request(withdrawal_data)
        
        if success:
            # Foydalanuvchiga tasdiqlash xabari
            confirmation_message = f"✅ *Rahmat! To'lovingiz tez orada o'tkaziladi!*\n\n"
            confirmation_message += f"💰 *Miqdor:* {context.user_data['withdrawal_amount']:,} so'm\n"
            confirmation_message += f"💸 *Komissiya:* {context.user_data['commission_amount']:,} so'm\n"
            confirmation_message += f"✅ *Chiqariladigan:* {context.user_data['net_amount']:,} so'm\n"
            confirmation_message += f"📱 *Usul:* {withdrawal_method}\n"
            confirmation_message += f"📝 *Hisob:* {account_details}\n\n"
            confirmation_message += f"⏳ Admin to'lovni amalga oshirgandan so'ng sizga xabar yuboradi..."
            
            await update.message.reply_text(
                confirmation_message,
                parse_mode='Markdown',
                reply_markup=get_back_keyboard()
            )
            
            # Admin kanaliga yuborish
            await self.send_withdrawal_request_to_admin(update, context, withdrawal_data)
        else:
            await update.message.reply_text(
                "❌ *Xato yuz berdi!*\n\nPul chiqarish so'rovi yaratilmadi. Iltimos, qayta urinib ko'ring.",
                parse_mode='Markdown',
                reply_markup=get_back_keyboard()
            )
        
        # Context ni tozalash
        context.user_data.clear()
        return ConversationHandler.END

    async def send_withdrawal_request_to_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE, withdrawal_data: dict):
        """Pul chiqarish so'rovini admin kanaliga yuborish"""
        try:
            user = update.effective_user
            db_user = self.db.get_user(user.id)
            
            # Admin kanal ID sini config dan olish
            admin_channel_id = ADMIN_CHANNEL_ID
            if not admin_channel_id:
                print("Admin kanal ID topilmadi!")
                return
            
            # Ma'lumotlarni tayyorlash
            user_info = f"👤 *Foydalanuvchi:* {user.first_name} {user.last_name or ''}\n"
            user_info += f"🆔 *ID:* {user.id}\n"
            user_info += f"📱 *Username:* @{user.username or 'N/A'}\n"
            phone = db_user['phone'] if ('phone' in db_user.keys() and db_user['phone']) else 'N/A'
            region = db_user['region'] if ('region' in db_user.keys() and db_user['region']) else 'N/A'
            user_info += f"📞 *Telefon:* {phone}\n"
            user_info += f"🏘 *Hudud:* {region}\n\n"
            
            withdrawal_info = f"💰 *PUL CHIQARISH SO'ROVI*\n\n"
            withdrawal_info += f"💳 *Miqdor:* {withdrawal_data['amount']:,} so'm\n"
            withdrawal_info += f"💸 *Komissiya:* {withdrawal_data['commission']:,} so'm\n"
            withdrawal_info += f"✅ *Chiqariladigan:* {withdrawal_data['net_amount']:,} so'm\n"
            withdrawal_info += f"📱 *Usul:* {withdrawal_data['method']}\n"
            withdrawal_info += f"📝 *Hisob:* {withdrawal_data['account_details']}\n\n"
            
            message_text = f"💸 *YANGI PUL CHIQARISH SO'ROVI*\n\n"
            message_text += user_info + withdrawal_info
            message_text += f"⏰ *Vaqt:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            message_text += f"✅ *To'lovni amalga oshirgandan so'ng tasdiqlang:*"
            
            # Admin kanaliga yuborish
            await self.application.bot.send_message(
                chat_id=admin_channel_id,
                text=message_text,
                parse_mode='Markdown',
                reply_markup=get_withdrawal_approval_keyboard(user.id, withdrawal_data['amount'])
            )
            
            print(f"Pul chiqarish so'rovi admin kanaliga yuborildi: {user.id}")
            
        except Exception as e:
            print(f"Admin kanaliga yuborishda xato: {e}")
            import traceback
            traceback.print_exc()

    async def handle_withdrawal_completed(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin to'lovni amalga oshirganini tasdiqlaganda"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = int(data.split('_')[2])
        amount = int(data.split('_')[3])
        
        # Foydalanuvchining database ID sini olish
        db_user = self.db.get_user(user_id)
        if not db_user:
            await query.edit_message_text(
                f"❌ *Xato yuz berdi!*\n\n"
                f"Foydalanuvchi topilmadi: {user_id}",
                parse_mode='Markdown'
            )
            return
        
        # Balansni 0 qilish va to'lovni tasdiqlash
        success = self.db.complete_withdrawal(db_user['id'], amount)
        
        if success:
            # Foydalanuvchiga xabar yuborish
            try:
                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🎉 *To'lov muofaqiyatli amalga oshirildi!*\n\n"
                        f"💰 *To'lov summasi:* {amount:,} so'm\n"
                        f"✅ *Hisobingizdan chiqarildi*\n"
                        f"💳 *Karta:* {db_user['last_withdrawal_account'] if ('last_withdrawal_account' in db_user.keys() and db_user['last_withdrawal_account']) else 'N/A'}\n\n"
                        f"Rahmat!"
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"Foydalanuvchiga xabar yuborishda xato: {e}")
            
            # Admin xabarini yangilash
            await query.edit_message_text(
                f"✅ *To'lov tasdiqlandi!*\n\n"
                f"👤 Foydalanuvchi: {user_id}\n"
                f"💰 Miqdor: {amount:,} so'm\n"
                f"✅ Balans 0 qilindi\n"
                f"📱 Foydalanuvchiga xabar yuborildi",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"❌ *Xato yuz berdi!*\n\n"
                f"To'lovni tasdiqlashda muammo bo'ldi.",
                parse_mode='Markdown'
            )
    
    async def handle_withdrawal_rejected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin to'lovni rad etganda"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = int(data.split('_')[2])
        
        # Foydalanuvchining database ID sini olish
        db_user = self.db.get_user(user_id)
        if not db_user:
            await query.edit_message_text(
                f"❌ *Xato yuz berdi!*\n\n"
                f"Foydalanuvchi topilmadi: {user_id}",
                parse_mode='Markdown'
            )
            return
        
        # Rad etish va balansni qaytarish
        success = self.db.reject_withdrawal(db_user['id'])
        
        if success:
            # Foydalanuvchiga xabar yuborish
            try:
                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ *Pul chiqarish so'rovingiz rad etildi!*\n\n"
                         f"⚠️ Iltimos, ma'lumotlaringizni tekshiring va qayta urinib ko'ring.\n"
                         f"💰 Balansingiz qaytarildi.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"Foydalanuvchiga xabar yuborishda xato: {e}")
            
            # Admin xabarini yangilash
            await query.edit_message_text(
                f"❌ *To'lov rad etildi!*\n\n"
                f"👤 Foydalanuvchi: {user_id}\n"
                f"💰 Balans qaytarildi\n"
                f"📱 Foydalanuvchiga xabar yuborildi",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"❌ *Xato yuz berdi!*\n\n"
                f"To'lovni rad etishda muammo bo'ldi.",
                parse_mode='Markdown'
            )
    
    async def cancel_new_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yangi loyiha qo'shishni bekor qilish"""
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await update.callback_query.edit_message_text(
            get_message('project_creation_cancelled', language),
            reply_markup=get_back_keyboard()
        )
        
        # Context ni tozalash
        context.user_data.clear()
        return ConversationHandler.END
    
    async def start_edit_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyiha tahrirlashni boshlash"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await query.edit_message_text(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Callback data dan ma'lumotlarni olish
        data = query.data.split('_')
        edit_type = data[1]  # 'name' yoki 'link'
        project_id = int(data[2])
        
        # Context ga ma'lumotlarni saqlash
        context.user_data['edit_type'] = edit_type
        context.user_data['project_id'] = project_id
        
        # Loyihani bazadan olish
        project = None
        
        # Mavsum loyihalaridan qidirish
        active_season = self.db.get_active_season()
        if active_season:
            projects = self.db.get_projects_by_season(active_season['id'])
            for p in projects:
                if p['id'] == project_id:
                    project = p
                    break
        
        # Agar topilmagan bo'lsa, yangi loyihalardan qidirish
        if not project:
            approved_projects = self.db.get_approved_projects()
            for p in approved_projects:
                if p['id'] == project_id:
                    project = p
                    break
        
        if not project:
            await query.edit_message_text(
                "❌ *Xato yuz berdi!*\n\nLoyiha topilmadi.",
                parse_mode='Markdown',
                reply_markup=get_back_keyboard()
            )
            return
        
        # Context ga loyiha ma'lumotlarini saqlash
        context.user_data['project_name'] = project['name']
        context.user_data['project_link'] = project.get('link', '')
        
        if edit_type == 'name':
            # Loyiha nomini tahrirlash
            await query.edit_message_text(
                f"✏️ *Loyiha nomini tahrirlash*\n\n"
                f"🏗 *Hozirgi nom:* {project['name']}\n\n"
                f"📝 *Yangi nomni kiriting:*",
                parse_mode='Markdown',
                reply_markup=get_cancel_edit_keyboard()
            )
            return EDIT_PROJECT_NAME
        
        elif edit_type == 'link':
            # Loyiha havolasini tahrirlash
            current_link = project.get('link', 'Havola yo\'q')
            await query.edit_message_text(
                f"🔗 *Loyiha havolasini tahrirlash*\n\n"
                f"🏗 *Loyiha:* {project['name']}\n"
                f"🔗 *Hozirgi havola:* {current_link}\n\n"
                f"📝 *Yangi havolani kiriting:*",
                parse_mode='Markdown',
                reply_markup=get_cancel_edit_keyboard()
            )
            return EDIT_PROJECT_LINK
    
    async def edit_project_name_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyiha nomi tahrirlanganda"""
        new_name = update.message.text
        context.user_data['new_name'] = new_name
        
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Admin tasdiqlash uchun ma'lumotlarni ko'rsatish
        project_name = context.user_data['project_name']
        
        edit_info = f"✏️ *Loyiha nomini tahrirlash*\n\n"
        edit_info += f"🏗 *Eski nom:* {project_name}\n"
        edit_info += f"🏗 *Yangi nom:* {new_name}\n\n"
        edit_info += f"✅ *Tasdiqlash uchun tugmani bosing:*"
        
        # Tasdiqlash tugmalari
        keyboard = [
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data="approve_edit"),
                InlineKeyboardButton("❌ Rad etish", callback_data="reject_edit")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            edit_info,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        return EDIT_PROJECT_APPROVAL
    
    async def edit_project_link_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyiha havolasi tahrirlanganda"""
        new_link = update.message.text
        context.user_data['new_link'] = new_link
        
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Admin tasdiqlash uchun ma'lumotlarni ko'rsatish
        project_name = context.user_data['project_name']
        old_link = context.user_data['project_link']
        
        edit_info = f"🔗 *Loyiha havolasini tahrirlash*\n\n"
        edit_info += f"🏗 *Loyiha:* {project_name}\n"
        edit_info += f"🔗 *Eski havola:* {old_link}\n"
        edit_info += f"🔗 *Yangi havola:* {new_link}\n\n"
        edit_info += f"✅ *Tasdiqlash uchun tugmani bosing:*"
        
        # Tasdiqlash tugmalari
        keyboard = [
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data="approve_edit"),
                InlineKeyboardButton("❌ Rad etish", callback_data="reject_edit")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            edit_info,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        return EDIT_PROJECT_APPROVAL
    
    async def edit_project_approval_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyiha tahrirlashni tasdiqlash yoki rad etish"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        action = query.data.split('_')[0]  # 'approve' yoki 'reject'
        
        if action == 'approve':
            # Loyihani tahrirlash
            project_id = context.user_data['project_id']
            edit_type = context.user_data['edit_type']
            
            success = False
            
            if edit_type == 'name':
                new_name = context.user_data['new_name']
                success = self.db.update_project_name(project_id, new_name)
                
                if success:
                    # Barcha foydalanuvchilarga yangilangan loyiha haqida xabar yuborish
                    await self.broadcast_project_update_to_all_users(
                        project_id, 
                        f"Loyiha nomi yangilandi: {new_name}", 
                        language
                    )
                    
                    await query.edit_message_text(
                        f"✅ *Loyiha nomi yangilandi!*\n\n"
                        f"🏗 *Yangi nom:* {new_name}\n"
                        f"📱 Barcha foydalanuvchilarga xabar yuborildi",
                        parse_mode='Markdown',
                        reply_markup=get_back_keyboard()
                    )
                else:
                    await query.edit_message_text(
                        f"❌ *Xato yuz berdi!*\n\n"
                        f"Loyiha nomini yangilashda muammo bo'ldi.",
                        parse_mode='Markdown',
                        reply_markup=get_back_keyboard()
                    )
            
            elif edit_type == 'link':
                new_link = context.user_data['new_link']
                success = self.db.update_project_link(project_id, new_link)
                
                if success:
                    # Barcha foydalanuvchilarga yangilangan loyiha haqida xabar yuborish
                    await self.broadcast_project_update_to_all_users(
                        project_id, 
                        f"Loyiha havolasi yangilandi: {new_link}", 
                        language
                    )
                    
                    await query.edit_message_text(
                        f"✅ *Loyiha havolasi yangilandi!*\n\n"
                        f"🔗 *Yangi havola:* {new_link}\n"
                        f"📱 Barcha foydalanuvchilarga xabar yuborildi",
                        parse_mode='Markdown',
                        reply_markup=get_back_keyboard()
                    )
                else:
                    await query.edit_message_text(
                        f"❌ *Xato yuz berdi!*\n\n"
                        f"Loyiha havolasini yangilashda muammo bo'ldi.",
                        parse_mode='Markdown',
                        reply_markup=get_back_keyboard()
                    )
        else:
            # Loyihani rad etish
            await query.edit_message_text(
                f"❌ *Loyiha tahrirlash rad etildi!*\n\n"
                f"O'zgarishlar saqlanmadi.",
                parse_mode='Markdown',
                reply_markup=get_back_keyboard()
            )
        
        # Context ni tozalash
        context.user_data.clear()
        return ConversationHandler.END
    
    async def cancel_edit_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyiha tahrirlashni bekor qilish"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await query.edit_message_text(
            f"❌ *Loyiha tahrirlash bekor qilindi!*\n\n"
            f"O'zgarishlar saqlanmadi.",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
        
        # Context ni tozalash
        context.user_data.clear()
        return ConversationHandler.END
    
    async def broadcast_project_update_to_all_users(self, project_id: int, update_message: str, language: str):
        """Loyiha yangilanishi haqida barcha foydalanuvchilarga xabar yuborish"""
        try:
            # Barcha foydalanuvchilarni olish
            users = self.db.get_all_users()
            
            message = f"🔄 *LOYIHA YANGILANDI!*\n\n{update_message}\n\n"
            message += f"📱 Yangi ma'lumotlarni ko'rish uchun botni qayta ishga tushiring."
            
            success_count = 0
            for user in users:
                try:
                    await self.application.bot.send_message(
                        chat_id=user['telegram_id'],
                        text=message,
                        parse_mode='Markdown'
                    )
                    success_count += 1
                except Exception as e:
                    print(f"Foydalanuvchiga xabar yuborishda xato: {e}")
                    continue
            
            print(f"Loyiha yangilanishi {success_count} ta foydalanuvchiga yuborildi")
            
        except Exception as e:
            print(f"Loyiha yangilanishini yuborishda xato: {e}")

    async def admin_delete_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyihalarni o'chirish menyusi"""
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await update.callback_query.answer(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Mavjud loyihalarni olish
        active_season = self.db.get_active_season()
        projects = []
        if active_season:
            projects = self.db.get_projects_by_season(active_season['id'])
        
        # Yangi qo'shilgan loyihalarni ham olish
        approved_projects = self.db.get_approved_projects()
        
        if not projects and not approved_projects:
            await update.callback_query.edit_message_text(
                get_message('no_projects_to_delete', language),
                reply_markup=get_back_keyboard()
            )
            return
        
        # Loyihalar ro'yxatini ko'rsatish
        projects_text = get_message('admin_delete_projects_menu', language) + "\n\n"
        
        # Mavsum loyihalari
        if projects:
            projects_text += "📅 *Mavsum loyihalari:*\n"
            for project in projects:
                projects_text += f"🏗 *{project['name']}*\n"
                projects_text += f"💰 {project['budget']:,} so'm\n"
                projects_text += f"🏘 {project['region']}\n"
                projects_text += f"🆔 ID: {project['id']}\n\n"
        
        # Yangi qo'shilgan loyihalar
        if approved_projects:
            projects_text += "🆕 *Yangi qo'shilgan loyihalar:*\n"
            for project in approved_projects:
                projects_text += f"🏗 *{project['name']}*\n"
                projects_text += f"🔗 {project['link']}\n"
                projects_text += f"🆔 ID: {project['id']}\n\n"
        
        projects_text += "🗑 *O'chirish uchun quyidagi tugmalardan birini bosing:*"
        
        # O'chirish tugmalari bilan klaviatura yaratish
        keyboard = []
        
        # Mavsum loyihalari uchun tugmalar
        if projects:
            for project in projects:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🗑 {project['name']} ni o'chirish",
                        callback_data=f"confirm_delete_project_{project['id']}"
                    )
                ])
        
        # Yangi loyihalar uchun tugmalar
        if approved_projects:
            for project in approved_projects:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🗑 {project['name']} ni o'chirish",
                        callback_data=f"confirm_delete_project_{project['id']}"
                    )
                ])
        
        # Orqaga qaytish tugmasi
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            projects_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    async def confirm_delete_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyihani o'chirishni tasdiqlash"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await query.edit_message_text(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Loyiha ID ni olish
        project_id = int(query.data.split('_')[3])
        
        # Loyihani bazadan olish
        project = self.db.get_project_by_id(project_id)
        if not project:
            await query.edit_message_text(
                get_message('project_not_found', language),
                reply_markup=get_back_keyboard()
            )
            return
        
        # Tasdiqlash xabari
        confirmation_text = get_message('project_delete_confirmation', language, project_name=project['name'])
        
        await query.edit_message_text(
            confirmation_text,
            parse_mode='Markdown',
            reply_markup=get_project_delete_confirmation_keyboard(project_id)
        )

    async def cancel_delete_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyihani o'chirishni bekor qilish"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        await query.edit_message_text(
            get_message('project_delete_cancelled', language),
            reply_markup=get_back_keyboard()
        )

    async def delete_project_confirmed(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Loyihani o'chirishni amalga oshirish"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        
        # Admin huquqlarini tekshirish
        if user.id not in ADMIN_IDS and user.id not in SUPER_ADMIN_IDS:
            await query.edit_message_text(get_message('admin_access_denied', 'uz'))
            return
        
        db_user = self.db.get_user(user.id)
        language = db_user['language']
        
        # Loyiha ID ni olish
        project_id = int(query.data.split('_')[2])
        
        # Loyihani o'chirish
        success, result = self.db.delete_project(project_id)
        
        if success:
            project_name = result
            # Muvaffaqiyatli o'chirish xabari
            success_message = get_message('project_deleted_success', language, project_name=project_name)
            
            await query.edit_message_text(
                success_message,
                parse_mode='Markdown',
                reply_markup=get_back_keyboard()
            )
            
            # Barcha foydalanuvchilarga loyiha o'chirilgani haqida xabar yuborish
            await self.broadcast_project_deletion_to_all_users(project_name, language)
            
        else:
            error_message = get_message('project_delete_error', language, error=result)
            
            await query.edit_message_text(
                error_message,
                parse_mode='Markdown',
                reply_markup=get_back_keyboard()
            )

    async def broadcast_project_deletion_to_all_users(self, project_name: str, language: str):
        """Loyiha o'chirilgani haqida barcha foydalanuvchilarga xabar yuborish"""
        try:
            # Barcha foydalanuvchilarni olish
            users = self.db.get_all_active_users()
            
            message = f"🗑 *LOYIHA O'CHIRILDI!*\n\n"
            message += f"🏗 **{project_name}** loyihasi admin tomonidan o'chirildi.\n\n"
            message += f"⚠️ Bu loyiha endi ovoz berish uchun mavjud emas.\n"
            message += f"📱 Yangi ma'lumotlarni ko'rish uchun botni qayta ishga tushiring."
            
            success_count = 0
            for user in users:
                try:
                    await self.application.bot.send_message(
                        chat_id=user['telegram_id'],
                        text=message,
                        parse_mode='Markdown'
                    )
                    success_count += 1
                except Exception as e:
                    print(f"Foydalanuvchiga xabar yuborishda xato: {e}")
                    continue
            
            print(f"Loyiha o'chirilgani haqida {success_count} ta foydalanuvchiga xabar yuborildi")
            
        except Exception as e:
            print(f"Loyiha o'chirilgani haqida xabar yuborishda xato: {e}")

    def run(self):
        """Botni ishga tushirish"""
        # Railway uchun webhook yoki polling
        import os
        port = int(os.environ.get('PORT', 8080))
        
        # Railway da ishlayotganda webhook ishlatamiz
        if os.environ.get('RAILWAY_ENVIRONMENT'):
            # Webhook sozlamalari
            webhook_url = os.environ.get('WEBHOOK_URL')
            if webhook_url:
                self.application.run_webhook(
                    listen='0.0.0.0',
                    port=port,
                    webhook_url=webhook_url
                )
            else:
                # Webhook URL yo'q bo'lsa polling ishlatamiz
                self.application.run_polling()
        else:
            # Lokal ishlayotganda polling ishlatamiz
            self.application.run_polling()

if __name__ == '__main__':
    bot = BotopneBot()
    bot.run()
