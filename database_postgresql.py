import psycopg2
import psycopg2.extras
import json
from datetime import datetime
from config import (
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, 
    POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_URL, DATABASE_PUBLIC_URL
)

class DatabasePostgreSQL:
    def __init__(self):
        self.connection_params = self._get_connection_params()
        self.init_database()
    
    def _get_connection_params(self):
        """PostgreSQL ulanish parametrlarini olish"""
        if POSTGRES_URL:
            return {'dsn': POSTGRES_URL}
        elif DATABASE_PUBLIC_URL:
            return {'dsn': DATABASE_PUBLIC_URL}
        else:
            return {
                'host': POSTGRES_HOST,
                'port': POSTGRES_PORT,
                'database': POSTGRES_DB,
                'user': POSTGRES_USER,
                'password': POSTGRES_PASSWORD
            }
    
    def get_connection(self):
        """PostgreSQL ulanishini olish"""
        try:
            conn = psycopg2.connect(**self.connection_params)
            conn.autocommit = False
            return conn
        except Exception as e:
            print(f"PostgreSQL ulanishda xato: {e}")
            raise
    
    def init_database(self):
        """Ma'lumotlar bazasi va jadvallarni yaratish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Foydalanuvchilar jadvali
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    phone VARCHAR(20),
                    region VARCHAR(100),
                    language VARCHAR(10) DEFAULT 'uz',
                    referral_code VARCHAR(20) UNIQUE,
                    referred_by INTEGER,
                    balance INTEGER DEFAULT 0,
                    pending_balance INTEGER DEFAULT 0,
                    total_earned INTEGER DEFAULT 0,
                    total_withdrawn INTEGER DEFAULT 0,
                    last_withdrawal_account TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_admin BOOLEAN DEFAULT FALSE,
                    is_super_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Mavsumlar jadvali
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS seasons (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    max_votes_per_user INTEGER DEFAULT 3,
                    is_active BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Loyihalar jadvali
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id SERIAL PRIMARY KEY,
                    season_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    budget INTEGER NOT NULL,
                    region VARCHAR(100) NOT NULL,
                    category VARCHAR(100),
                    image_url TEXT,
                    project_url TEXT,
                    link TEXT,
                    status VARCHAR(50) DEFAULT 'draft',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (season_id) REFERENCES seasons (id)
                )
            ''')
            
            # Ovozlar jadvali
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS votes (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    project_id INTEGER NOT NULL,
                    season_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (project_id) REFERENCES projects (id),
                    FOREIGN KEY (season_id) REFERENCES seasons (id),
                    UNIQUE(user_id, project_id, season_id)
                )
            ''')
            
            # Pul chiqarish so'rovlari
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS withdrawal_requests (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    commission INTEGER NOT NULL,
                    net_amount INTEGER NOT NULL,
                    method VARCHAR(50) NOT NULL,
                    account_details TEXT NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    admin_notes TEXT,
                    processed_by INTEGER,
                    processed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (processed_by) REFERENCES users (id)
                )
            ''')
            
            # Sozlamalar jadvali
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(100) UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    description TEXT,
                    updated_by INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (updated_by) REFERENCES users (id)
                )
            ''')
            
            # Balans tarixi
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS balance_history (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    type VARCHAR(100) NOT NULL,
                    description TEXT,
                    reference_id INTEGER,
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # Yangiliklar
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS announcements (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    language VARCHAR(10) DEFAULT 'uz',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_by INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (created_by) REFERENCES users (id)
                )
            ''')
            
            # Audit loglari
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    action VARCHAR(255) NOT NULL,
                    details TEXT,
                    ip_address VARCHAR(45),
                    user_agent TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # Tasdiqlangan loyihalar jadvali
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS approved_projects (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    link TEXT NOT NULL,
                    status VARCHAR(50) DEFAULT 'approved',
                    approved_by INTEGER NOT NULL,
                    approved_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (approved_by) REFERENCES users (id)
                )
            ''')
            
            # Dastlabki sozlamalarni qo'shish
            cursor.execute('''
                INSERT INTO settings (key, value, description) VALUES 
                ('REFERRAL_BONUS', '1000', 'Referal uchun bonus puli'),
                ('VOTE_BONUS', '25000', 'Ovoz berish uchun bonus puli'),
                ('MIN_WITHDRAWAL', '20000', 'Minimal yechish miqdori'),
                ('COMMISSION_RATE', '0.02', 'Komissiya foizi (0.01 = 1%)')
                ON CONFLICT (key) DO NOTHING
            ''')
            
            conn.commit()
            print("PostgreSQL jadvallari muvaffaqiyatli yaratildi!")
            
        except Exception as e:
            conn.rollback()
            print(f"PostgreSQL jadvallarini yaratishda xato: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def create_user(self, telegram_id, username, first_name, last_name, phone, region, language, referred_by=None):
        """Yangi foydalanuvchi yaratish"""
        conn = self.get_connection()
        try:
            # Referal ID yaratish (8 ta belgi)
            import secrets
            import string
            
            def generate_referral_id():
                """Benzersiz referal ID yaratish"""
                while True:
                    # 8 ta belgi: harflar va raqamlar
                    chars = string.ascii_uppercase + string.digits
                    referral_id = ''.join(secrets.choice(chars) for _ in range(8))
                    
                    # Bu ID mavjud emasligini tekshirish
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM users WHERE referral_code = %s", (referral_id,))
                    if not cursor.fetchone():
                        return referral_id
            
            referral_code = generate_referral_id()
            
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (telegram_id, username, first_name, last_name, phone, region, language, referred_by, referral_code, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (telegram_id, username, first_name, last_name, phone, region, language, referred_by, referral_code, datetime.now()))
            
            user_id = cursor.fetchone()[0]
            
            # Agar referal orqali kelgan bo'lsa, bonus berish
            if referred_by:
                self.add_balance(referred_by, 1000, 'referral_bonus', f'Yangi foydalanuvchi jalb etildi')
                self.add_balance(user_id, 1000, 'referral_bonus', f'Referal orqali ro\'yxatdan o\'tish')
            
            conn.commit()
            return user_id
        except Exception as e:
            conn.rollback()
            print(f"Foydalanuvchi yaratishda xato: {e}")
            return None
        finally:
            conn.close()
    
    def get_user(self, telegram_id):
        """Foydalanuvchini telegram_id bo'yicha olish"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute('SELECT * FROM users WHERE telegram_id = %s', (telegram_id,))
            user = cursor.fetchone()
            return dict(user) if user else None
        finally:
            cursor.close()
            conn.close()
    
    def add_balance(self, user_id, amount, balance_type, description):
        """Foydalanuvchi balansiga qo'shish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Balansni yangilash
            cursor.execute("""
                UPDATE users SET 
                balance = balance + %s,
                total_earned = total_earned + %s,
                updated_at = %s
                WHERE id = %s
            """, (amount, amount, datetime.now(), user_id))
            
            # Balans tarixiga qo'shish
            cursor.execute("""
                INSERT INTO balance_history (user_id, amount, type, description, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, amount, balance_type, description, 'approved', datetime.now()))
            
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            print(f"Balans qo'shishda xato: {e}")
            return False
        finally:
            conn.close()
    
    def get_active_season(self):
        """Faol mavsumni olish"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute('''
                SELECT * FROM seasons 
                WHERE is_active = TRUE AND CURRENT_DATE BETWEEN start_date AND end_date
                ORDER BY start_date DESC LIMIT 1
            ''')
            
            season = cursor.fetchone()
            return dict(season) if season else None
        finally:
            cursor.close()
            conn.close()
    
    def get_projects_by_season(self, season_id, region=None):
        """Mavsum bo'yicha loyihalarni olish"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            if region:
                cursor.execute('''
                    SELECT * FROM projects 
                    WHERE season_id = %s AND region = %s AND status = 'published'
                    ORDER BY name
                ''', (season_id, region))
            else:
                cursor.execute('''
                    SELECT * FROM projects 
                    WHERE season_id = %s AND status = 'published'
                    ORDER BY name
                ''', (season_id,))
            
            projects = cursor.fetchall()
            return [dict(project) for project in projects]
        finally:
            cursor.close()
            conn.close()
    
    def get_approved_projects(self):
        """Tasdiqlangan loyihalarni olish"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT id, name, link, status, approved_by, approved_at, created_at
                FROM approved_projects 
                WHERE status = 'approved'
                ORDER BY created_at DESC
            """)
            
            projects = cursor.fetchall()
            return [dict(project) for project in projects]
        finally:
            cursor.close()
            conn.close()
    
    def get_setting(self, key, default=None):
        """Sozlama qiymatini olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT value FROM settings WHERE key = %s", (key,))
            result = cursor.fetchone()
            return result[0] if result else default
        finally:
            cursor.close()
            conn.close()
    
    def update_setting(self, key, value, admin_id):
        """Sozlama qiymatini yangilash"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE settings 
                SET value = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE key = %s
            """, (value, admin_id, key))
            
            if cursor.rowcount > 0:
                conn.commit()
                return True
            return False
        except Exception as e:
            conn.rollback()
            print(f"Sozlama yangilashda xato: {e}")
            return False
        finally:
            conn.close()
    
    def get_statistics(self):
        """Umumiy statistikalarni olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Foydalanuvchilar soni
            cursor.execute('SELECT COUNT(*) as total_users FROM users WHERE is_active = TRUE')
            total_users = cursor.fetchone()[0]
            
            # Bugungi yangi foydalanuvchilar
            cursor.execute('''
                SELECT COUNT(*) as today_users 
                FROM users 
                WHERE DATE(created_at) = CURRENT_DATE AND is_active = TRUE
            ''')
            today_users = cursor.fetchone()[0]
            
            # Jami ovozlar - to'lov qilingan foydalanuvchilar soni
            cursor.execute('SELECT COUNT(DISTINCT user_id) as total_votes FROM balance_history WHERE type = %s AND status = %s', ('payment', 'approved'))
            total_votes = cursor.fetchone()[0]
            
            # Jami balans - tasdiqlangan pullar summasi
            cursor.execute('SELECT COALESCE(SUM(amount), 0) as total_balance FROM balance_history WHERE type = %s AND status = %s', ('payment', 'approved'))
            total_balance = cursor.fetchone()[0] or 0
            
            return {
                'total_users': total_users,
                'today_users': today_users,
                'total_votes': total_votes,
                'total_balance': total_balance
            }
        finally:
            cursor.close()
            conn.close()
    
    def get_referral_stats(self, user_id):
        """Foydalanuvchining referal statistikalarini olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Jalb etilgan foydalanuvchilar soni
            cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by = %s", (user_id,))
            referrals_count = cursor.fetchone()[0]
            
            # Referal orqali olingan bonuslar
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) FROM balance_history 
                WHERE user_id = %s AND type = 'referral_bonus'
            """, (user_id,))
            referral_earnings = cursor.fetchone()[0] or 0
            
            return {
                'referrals_count': referrals_count,
                'referral_earnings': referral_earnings
            }
        finally:
            cursor.close()
            conn.close()
    
    def get_user_by_referral_code(self, referral_code):
        """Referal kod orqali foydalanuvchini topish"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT id, telegram_id, username, first_name, last_name, phone, region, language, 
                       referral_code, referred_by, balance, pending_balance, total_withdrawn, 
                       total_earned, created_at, updated_at
                FROM users WHERE referral_code = %s
            """, (referral_code,))
            
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            cursor.close()
            conn.close()
    
    def get_all_active_users(self):
        """Barcha faol foydalanuvchilarni olish"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT telegram_id, first_name, language
                FROM users
                WHERE is_active = TRUE
                ORDER BY created_at DESC
            """)
            users = cursor.fetchall()
            return [dict(user) for user in users]
        finally:
            cursor.close()
            conn.close()
    
    def create_approved_project(self, project_data):
        """Tasdiqlangan loyihani yaratish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO approved_projects (name, link, status, approved_by, approved_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                project_data['name'],
                project_data['link'],
                project_data['status'],
                project_data['approved_by'],
                project_data['approved_at'],
                datetime.now()
            ))
            
            project_id = cursor.fetchone()[0]
            conn.commit()
            return project_id
        except Exception as e:
            conn.rollback()
            print(f"Tasdiqlangan loyiha yaratishda xato: {e}")
            return None
        finally:
            conn.close()
    
    def create_withdrawal_request(self, withdrawal_data):
        """Pul chiqarish so'rovini yaratish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO withdrawal_requests (user_id, amount, commission, net_amount, method, account_details, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                withdrawal_data['user_id'],
                withdrawal_data['amount'],
                withdrawal_data['commission'],
                withdrawal_data['net_amount'],
                withdrawal_data['method'],
                withdrawal_data['account_details'],
                withdrawal_data['status'],
                datetime.now()
            ))
            
            withdrawal_id = cursor.fetchone()[0]
            
            # Foydalanuvchining balansini kamaytirish
            cursor.execute("""
                UPDATE users SET 
                balance = balance - %s,
                pending_balance = pending_balance + %s,
                last_withdrawal_account = %s,
                updated_at = %s
                WHERE id = %s
            """, (withdrawal_data['amount'], withdrawal_data['amount'], withdrawal_data['account_details'], datetime.now(), withdrawal_data['user_id']))
            
            conn.commit()
            return withdrawal_id
        except Exception as e:
            conn.rollback()
            print(f"Pul chiqarish so'rovini yaratishda xato: {e}")
            return None
        finally:
            conn.close()
    
    def complete_withdrawal(self, user_id, amount):
        """Pul chiqarishni yakunlash va balansni 0 qilish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Balansni 0 qilish va total_withdrawn ni yangilash
            cursor.execute("""
                UPDATE users SET 
                balance = 0,
                pending_balance = 0,
                total_withdrawn = total_withdrawn + %s,
                updated_at = %s
                WHERE id = %s
            """, (amount, datetime.now(), user_id))
            
            # Withdrawal status ni 'completed' qilish
            cursor.execute("""
                UPDATE withdrawal_requests SET 
                status = 'completed',
                processed_at = %s
                WHERE user_id = %s AND status = 'pending'
            """, (datetime.now(), user_id))
            
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            print(f"Pul chiqarishni yakunlashda xato: {e}")
            return False
        finally:
            conn.close()
    
    def reject_withdrawal(self, user_id):
        """Pul chiqarishni rad etish va balansni qaytarish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Eng so'nggi pending withdrawal ni olish
            cursor.execute("""
                SELECT amount FROM withdrawal_requests 
                WHERE user_id = %s AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
            """, (user_id,))
            
            result = cursor.fetchone()
            if result:
                amount = result[0]
                
                # Balansni qaytarish
                cursor.execute("""
                    UPDATE users SET 
                    balance = balance + %s,
                    pending_balance = 0,
                    updated_at = %s
                    WHERE id = %s
                """, (amount, datetime.now(), user_id))
                
                # Withdrawal status ni 'rejected' qilish
                cursor.execute("""
                    UPDATE withdrawal_requests SET 
                    status = 'rejected',
                    processed_at = %s
                    WHERE user_id = %s AND status = 'pending'
                """, (datetime.now(), user_id))
                
                conn.commit()
                return True
            return False
        except Exception as e:
            conn.rollback()
            print(f"Pul chiqarishni rad etishda xato: {e}")
            return False
        finally:
            conn.close()
    
    def get_withdrawal_notification(self, withdrawal_id):
        """Pul chiqarish so'rovini ID bo'yicha olish"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT 
                    wr.user_id,
                    wr.amount,
                    wr.method,
                    wr.account_details,
                    wr.processed_at,
                    wr.created_at,
                    u.telegram_id,
                    u.language
                FROM withdrawal_requests wr
                JOIN users u ON u.id = wr.user_id
                WHERE wr.id = %s
            """, (withdrawal_id,))
            
            result = cursor.fetchone()
            return dict(result) if result else None
        finally:
            cursor.close()
            conn.close()
    
    def get_top_voters(self, limit=10):
        """Eng ko'p ovoz bergan foydalanuvchilarni olish"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT 
                    u.first_name,
                    u.telegram_id,
                    COUNT(bh.id) as vote_count
                FROM users u
                LEFT JOIN balance_history bh ON u.id = bh.user_id AND bh.type = 'payment' AND bh.status = 'approved'
                WHERE u.is_active = TRUE
                GROUP BY u.id, u.first_name, u.telegram_id
                HAVING COUNT(bh.id) > 0
                ORDER BY vote_count DESC
                LIMIT %s
            """, (limit,))
            
            top_voters = cursor.fetchall()
            return [dict(voter) for voter in top_voters]
        finally:
            cursor.close()
            conn.close()
    
    def create_announcement(self, title, content, language, created_by):
        """Yangi yangilik yaratish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO announcements (title, content, language, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (title, content, language, created_by, datetime.now()))
            
            announcement_id = cursor.fetchone()[0]
            conn.commit()
            return announcement_id
        except Exception as e:
            conn.rollback()
            print(f"Yangilik yaratishda xato: {e}")
            return None
        finally:
            conn.close()
    
    def get_last_announcement(self, language='uz'):
        """Oxirgi yangilikni olish"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT title, content, created_at, created_by
                FROM announcements
                WHERE language = %s AND is_active = TRUE
                ORDER BY created_at DESC
                LIMIT 1
            """, (language,))
            
            result = cursor.fetchone()
            return dict(result) if result else None
        finally:
            cursor.close()
            conn.close()
    
    def get_settings_for_admin(self):
        """Admin uchun sozlamalar ro'yxati"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT key, value, description, updated_at 
                FROM settings 
                ORDER BY key
            """)
            settings = cursor.fetchall()
            return [dict(setting) for setting in settings]
        finally:
            cursor.close()
            conn.close()
    
    def get_users_with_pending_balance(self):
        """Pending balansi bo'lgan foydalanuvchilarni olish"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT id, telegram_id, first_name, last_name, pending_balance
                FROM users 
                WHERE pending_balance > 0 AND is_active = TRUE
                ORDER BY pending_balance DESC
            """)
            users = cursor.fetchall()
            return [dict(user) for user in users]
        finally:
            cursor.close()
            conn.close()
    
    def get_comprehensive_report_data(self):
        """To'liq hisobot uchun barcha ma'lumotlarni olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 1. Foydalanuvchilar va ularning ovozlari
            cursor.execute("""
                SELECT 
                    u.id,
                    u.telegram_id,
                    u.username,
                    u.first_name,
                    u.last_name,
                    u.phone,
                    u.region,
                    u.language,
                    u.referral_code,
                    u.balance,
                    u.pending_balance,
                    u.total_earned,
                    u.total_withdrawn,
                    u.created_at,
                    COUNT(v.id) as total_votes,
                    COUNT(DISTINCT v.season_id) as seasons_voted
                FROM users u
                LEFT JOIN votes v ON u.id = v.user_id
                WHERE u.is_active = TRUE
                GROUP BY u.id
                ORDER BY u.created_at DESC
            """)
            users_data = cursor.fetchall()
            
            # 2. Ovoz berish tarixi
            cursor.execute("""
                SELECT 
                    v.id,
                    v.user_id,
                    u.telegram_id,
                    u.first_name,
                    u.last_name,
                    p.name as project_name,
                    s.name as season_name,
                    v.created_at as vote_date
                FROM votes v
                JOIN users u ON v.user_id = u.id
                JOIN projects p ON v.project_id = p.id
                JOIN seasons s ON v.season_id = s.id
                ORDER BY v.created_at DESC
            """)
            votes_data = cursor.fetchall()
            
            # 3. Pul chiqarish so'rovlari
            cursor.execute("""
                SELECT 
                    wr.id,
                    wr.user_id,
                    u.telegram_id,
                    u.first_name,
                    u.last_name,
                    u.phone,
                    wr.amount,
                    wr.commission,
                    wr.net_amount,
                    wr.method,
                    wr.account_details,
                    wr.status,
                    wr.created_at,
                    wr.processed_at
                FROM withdrawal_requests wr
                JOIN users u ON wr.user_id = u.id
                ORDER BY wr.created_at DESC
            """)
            withdrawals_data = cursor.fetchall()
            
            # 4. Balans tarixi
            cursor.execute("""
                SELECT 
                    bh.id,
                    bh.user_id,
                    u.telegram_id,
                    u.first_name,
                    u.last_name,
                    bh.amount,
                    bh.type,
                    bh.description,
                    bh.status,
                    bh.created_at
                FROM balance_history bh
                JOIN users u ON bh.user_id = u.id
                ORDER BY bh.created_at DESC
            """)
            balance_history_data = cursor.fetchall()
            
            # 5. Loyihalar
            cursor.execute("""
                SELECT 
                    p.id,
                    p.name,
                    p.budget,
                    p.region,
                    p.status,
                    s.name as season_name,
                    COUNT(v.id) as total_votes,
                    p.created_at
                FROM projects p
                LEFT JOIN seasons s ON p.season_id = s.id
                LEFT JOIN votes v ON p.id = v.project_id
                GROUP BY p.id
                ORDER BY p.created_at DESC
            """)
            projects_data = cursor.fetchall()
            
            # 6. Tasdiqlangan loyihalar
            cursor.execute("""
                SELECT 
                    ap.id,
                    ap.name,
                    ap.link,
                    ap.status,
                    u.first_name as approved_by_name,
                    ap.approved_at,
                    ap.created_at
                FROM approved_projects ap
                JOIN users u ON ap.approved_by = u.id
                ORDER BY ap.created_at DESC
            """)
            approved_projects_data = cursor.fetchall()
            
            return {
                'users': users_data,
                'votes': votes_data,
                'withdrawals': withdrawals_data,
                'balance_history': balance_history_data,
                'projects': projects_data,
                'approved_projects': approved_projects_data
            }
            
        finally:
            cursor.close()
            conn.close()
