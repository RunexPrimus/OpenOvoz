import sqlite3
import json
from datetime import datetime
from config import DATABASE_PATH

class Database:
    def __init__(self):
        self.db_path = DATABASE_PATH
        self.init_database()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Ma'lumotlar bazasi va jadvallarni yaratish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Foydalanuvchilar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                region TEXT,
                language TEXT DEFAULT 'uz',
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                balance INTEGER DEFAULT 0,
                pending_balance INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                total_withdrawn INTEGER DEFAULT 0,
                last_withdrawal_account TEXT,
                is_active BOOLEAN DEFAULT 1,
                is_admin BOOLEAN DEFAULT 0,
                is_super_admin BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Mavsumlar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                max_votes_per_user INTEGER DEFAULT 3,
                is_active BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Loyihalar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                budget INTEGER NOT NULL,
                region TEXT NOT NULL,
                category TEXT,
                image_url TEXT,
                project_url TEXT,
                link TEXT,
                status TEXT DEFAULT 'draft',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (season_id) REFERENCES seasons (id)
            )
        ''')
        
        # Ovozlar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                commission INTEGER NOT NULL,
                net_amount INTEGER NOT NULL,
                method TEXT NOT NULL,
                account_details TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                admin_notes TEXT,
                processed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Balans tarixi
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS balance_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                reference_id INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Yangiliklar
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                language TEXT DEFAULT 'uz',
                is_active BOOLEAN DEFAULT 1,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        ''')
        
        # Audit loglari
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Tasdiqlangan loyihalar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS approved_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                link TEXT NOT NULL,
                status TEXT DEFAULT 'approved',
                approved_by INTEGER NOT NULL,
                approved_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (approved_by) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
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
                    cursor.execute("SELECT id FROM users WHERE referral_code = ?", (referral_id,))
                    if not cursor.fetchone():
                        return referral_id
            
            referral_code = generate_referral_id()
            
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (telegram_id, username, first_name, last_name, phone, region, language, referred_by, referral_code, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (telegram_id, username, first_name, last_name, phone, region, language, referred_by, referral_code, datetime.now()))
            
            user_id = cursor.lastrowid
            
            # Agar referal orqali kelgan bo'lsa, bonus berish
            if referred_by:
                self.add_balance(referred_by, 1000, 'referral_bonus', f'Yangi foydalanuvchi jalb etildi')
                self.add_balance(user_id, 1000, 'referral_bonus', f'Referal orqali ro\'yxatdan o\'tish')
            
            conn.commit()
            return user_id
        except Exception as e:
            print(f"Foydalanuvchi yaratishda xato: {e}")
            return None
        finally:
            conn.close()
    
    def get_user(self, telegram_id):
        """Foydalanuvchini telegram_id bo'yicha olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        user = cursor.fetchone()
        
        conn.close()
        return user
    
    def update_user_language(self, telegram_id, language):
        """Foydalanuvchi tilini yangilash"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE users SET language = ? WHERE telegram_id = ?', (language, telegram_id))
        conn.commit()
        conn.close()
    
    def add_balance(self, user_id, amount, balance_type, description):
        """Foydalanuvchi balansiga qo'shish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Balansni yangilash
            cursor.execute("""
                UPDATE users SET 
                balance = balance + ?,
                total_earned = total_earned + ?,
                updated_at = ?
                WHERE id = ?
            """, (amount, amount, datetime.now(), user_id))
            
            # Balans tarixiga qo'shish
            cursor.execute("""
                INSERT INTO balance_history (user_id, amount, type, description, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, amount, balance_type, description, 'approved', datetime.now()))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Balans qo'shishda xato: {e}")
            return False
        finally:
            conn.close()
    
    def add_payment_record(self, user_id, amount, payment_type, description, status='pending'):
        """To'lov yozuvini qo'shish (balance_history ga)"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO balance_history (user_id, amount, type, description, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, amount, payment_type, description, status, datetime.now()))

            conn.commit()
            return True
        except Exception as e:
            print(f"To'lov yozuvini qo'shishda xato: {e}")
            return False
        finally:
            conn.close()
    
    def update_project_name(self, project_id, new_name):
        """Loyiha nomini yangilash"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Mavsum loyihalaridan qidirish
            cursor.execute("""
                UPDATE projects 
                SET name = ?, updated_at = ?
                WHERE id = ?
            """, (new_name, datetime.now(), project_id))
            
            if cursor.rowcount == 0:
                # Agar mavsum loyihalarida topilmagan bo'lsa, yangi loyihalardan qidirish
                cursor.execute("""
                    UPDATE approved_projects 
                    SET name = ?, updated_at = ?
                    WHERE id = ?
                """, (new_name, datetime.now(), project_id))
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Loyiha nomini yangilashda xato: {e}")
            return False
        finally:
            conn.close()
    
    def update_project_link(self, project_id, new_link):
        """Loyiha havolasini yangilash"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Mavsum loyihalaridan qidirish
            cursor.execute("""
                UPDATE projects 
                SET link = ?, updated_at = ?
                WHERE id = ?
            """, (new_link, datetime.now(), project_id))
            
            if cursor.rowcount == 0:
                # Agar mavsum loyihalarida topilmagan bo'lsa, yangi loyihalardan qidirish
                cursor.execute("""
                    UPDATE approved_projects 
                    SET link = ?, updated_at = ?
                    WHERE id = ?
                """, (new_link, datetime.now(), project_id))
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Loyiha havolasini yangilashda xato: {e}")
            return False
        finally:
            conn.close()
    
    def get_active_season(self):
        """Faol mavsumni olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM seasons 
            WHERE is_active = 1 AND date('now') BETWEEN start_date AND end_date
            ORDER BY start_date DESC LIMIT 1
        ''')
        
        season = cursor.fetchone()
        conn.close()
        return season
    
    def get_projects_by_season(self, season_id, region=None):
        """Mavsum bo'yicha loyihalarni olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if region:
            cursor.execute('''
                SELECT * FROM projects 
                WHERE season_id = ? AND region = ? AND status = 'published'
                ORDER BY name
            ''', (season_id, region))
        else:
            cursor.execute('''
                SELECT * FROM projects 
                WHERE season_id = ? AND status = 'published'
                ORDER BY name
            ''', (season_id,))
        
        projects = cursor.fetchall()
        conn.close()
        return projects
    
    def add_vote(self, user_id, project_id, season_id):
        """Ovoz qo'shish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO votes (user_id, project_id, season_id)
                VALUES (?, ?, ?)
            ''', (user_id, project_id, season_id))
            
            # Ovoz uchun bonus
            self.add_balance(user_id, 500, 'vote_bonus', 'Ovoz berish uchun bonus')
            
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def get_user_votes_count(self, user_id, season_id):
        """Foydalanuvchining mavsumdagi ovozlar sonini olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) as count FROM votes 
            WHERE user_id = ? AND season_id = ?
        ''', (user_id, season_id))
        
        result = cursor.fetchone()
        conn.close()
        return result['count'] if result else 0
    
    def create_withdrawal_request(self, withdrawal_data):
        """Pul chiqarish so'rovini yaratish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO withdrawal_requests (user_id, amount, commission, net_amount, method, account_details, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            
            # Foydalanuvchining balansini kamaytirish
            cursor.execute("""
                UPDATE users SET 
                balance = balance - ?,
                pending_balance = pending_balance + ?,
                last_withdrawal_account = ?,
                updated_at = ?
                WHERE id = ?
            """, (withdrawal_data['amount'], withdrawal_data['amount'], withdrawal_data['account_details'], datetime.now(), withdrawal_data['user_id']))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Pul chiqarish so'rovini yaratishda xato: {e}")
            return False
        finally:
            conn.close()
    
    def get_pending_withdrawals(self):
        """Kutilayotgan pul chiqarish so'rovlarini olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT wr.*, u.username, u.first_name, u.phone
            FROM withdrawal_requests wr
            JOIN users u ON wr.user_id = u.id
            WHERE wr.status = 'pending'
            ORDER BY wr.created_at DESC
        ''')
        
        withdrawals = cursor.fetchall()
        conn.close()
        return withdrawals
    
    def approve_withdrawal(self, withdrawal_id, admin_notes=None):
        """Pul chiqarish so'rovini tasdiqlash"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # So'rov ma'lumotlarini olish
            cursor.execute('''
                SELECT user_id, amount FROM withdrawal_requests WHERE id = ?
            ''', (withdrawal_id,))
            row = cursor.fetchone()
            if not row:
                conn.close()
                return False
            user_id = row['user_id']
            amount = row['amount']
            
            # So'rovni 'approved' qilish
            cursor.execute('''
                UPDATE withdrawal_requests 
                SET status = 'approved', admin_notes = ?, processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (admin_notes, withdrawal_id))
            
            # Foydalanuvchi pending balansini kamaytirish
            cursor.execute('''
                UPDATE users 
                SET pending_balance = CASE 
                    WHEN pending_balance >= ? THEN pending_balance - ? 
                    ELSE 0 END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (amount, amount, user_id))
            
            conn.commit()
            return True
        finally:
            conn.close()
    
    def get_statistics(self):
        """Umumiy statistikalarni olish"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Foydalanuvchilar soni
        cursor.execute('SELECT COUNT(*) as total_users FROM users WHERE is_active = 1')
        total_users = cursor.fetchone()['total_users']
        
        # Bugungi yangi foydalanuvchilar
        cursor.execute('''
            SELECT COUNT(*) as today_users 
            FROM users 
            WHERE DATE(created_at) = DATE('now') AND is_active = 1
        ''')
        today_users = cursor.fetchone()['today_users']
        
        # Jami ovozlar - to'lov qilingan foydalanuvchilar soni
        cursor.execute('SELECT COUNT(DISTINCT user_id) as total_votes FROM balance_history WHERE type = "payment" AND status = "approved"')
        total_votes = cursor.fetchone()['total_votes']
        
        # Jami balans - tasdiqlangan pullar summasi
        cursor.execute('SELECT SUM(amount) as total_balance FROM balance_history WHERE type = "payment" AND status = "approved"')
        total_balance = cursor.fetchone()['total_balance'] or 0
        
        conn.close()
        
        return {
            'total_users': total_users,
            'today_users': today_users,
            'total_votes': total_votes,
            'total_balance': total_balance
        }

    def get_user_by_referral_code(self, referral_code):
        """Referal kod orqali foydalanuvchini topish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, telegram_id, username, first_name, last_name, phone, region, language, 
                       referral_code, referred_by, balance, pending_balance, total_withdrawn, 
                       total_earned, created_at, updated_at
                FROM users WHERE referral_code = ?
            """, (referral_code,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'telegram_id': row[1],
                    'username': row[2],
                    'first_name': row[3],
                    'last_name': row[4],
                    'phone': row[5],
                    'region': row[6],
                    'language': row[7],
                    'referral_code': row[8],
                    'referred_by': row[9],
                    'balance': row[10],
                    'pending_balance': row[11],
                    'total_withdrawn': row[12],
                    'total_earned': row[13],
                    'created_at': row[14],
                    'updated_at': row[15]
                }
            return None
        except Exception as e:
            print(f"Referal kod orqali foydalanuvchi topishda xato: {e}")
            return None
        finally:
            conn.close()

    def get_referral_stats(self, user_id):
        """Foydalanuvchining referal statistikalarini olish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Jalb etilgan foydalanuvchilar soni
            cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,))
            referrals_count = cursor.fetchone()[0]
            
            # Referal orqali olingan bonuslar
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) FROM balance_history 
                WHERE user_id = ? AND type = 'referral_bonus'
            """, (user_id,))
            referral_earnings = cursor.fetchone()[0] or 0
            
            return {
                'referrals_count': referrals_count,
                'referral_earnings': referral_earnings
            }
        except Exception as e:
            print(f"Referal statistikalarini olishda xato: {e}")
            return {'referrals_count': 0, 'referral_earnings': 0}
        finally:
            conn.close()

    def generate_new_referral_code(self, user_id):
        """Foydalanuvchi uchun yangi referal kod yaratish"""
        conn = self.get_connection()
        try:
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
                    cursor.execute("SELECT id FROM users WHERE referral_code = ?", (referral_id,))
                    if not cursor.fetchone():
                        return referral_id
            
            referral_code = generate_referral_id()
            
            # Foydalanuvchiga referal kodni biriktirish
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET referral_code = ? WHERE id = ?
            """, (referral_code, user_id))
            
            conn.commit()
            return referral_code
        except Exception as e:
            print(f"Yangi referal kod yaratishda xato: {e}")
            return None
        finally:
            conn.close()
    
    def create_project(self, project_data):
        """Yangi loyiha yaratish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO projects (season_id, name, description, budget, region, category, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'published', ?)
            """, (
                project_data['season_id'],
                project_data['name'],
                project_data['description'],
                project_data['budget'],
                project_data['region'],
                project_data['category'],
                datetime.now()
            ))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Loyiha yaratishda xato: {e}")
            return False
        finally:
            conn.close()
    
    def get_all_users(self):
        """Barcha foydalanuvchilarni olish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, telegram_id, username, first_name, last_name, phone, region, language, 
                       referral_code, referred_by, balance, pending_balance, total_withdrawn, 
                       total_earned, created_at, updated_at
                FROM users
            """)
            
            users = []
            for row in cursor.fetchall():
                users.append({
                    'id': row[0],
                    'telegram_id': row[1],
                    'username': row[2],
                    'first_name': row[3],
                    'last_name': row[4],
                    'phone': row[5],
                    'region': row[6],
                    'language': row[7],
                    'referral_code': row[8],
                    'referred_by': row[9],
                    'balance': row[10],
                    'pending_balance': row[11],
                    'total_withdrawn': row[12],
                    'total_earned': row[13],
                    'created_at': row[14],
                    'updated_at': row[15]
                })
            return users
        except Exception as e:
            print(f"Barcha foydalanuvchilarni olishda xato: {e}")
            return []
        finally:
            conn.close()
    
    def create_approved_project(self, project_data):
        """Tasdiqlangan loyihani yaratish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO approved_projects (name, link, status, approved_by, approved_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                project_data['name'],
                project_data['link'],
                project_data['status'],
                project_data['approved_by'],
                project_data['approved_at'],
                datetime.now()
            ))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Tasdiqlangan loyiha yaratishda xato: {e}")
            return False
        finally:
            conn.close()
    
    def get_approved_projects(self):
        """Tasdiqlangan loyihalarni olish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, link, status, approved_by, approved_at, created_at
                FROM approved_projects 
                WHERE status = 'approved'
                ORDER BY created_at DESC
            """)
            
            projects = []
            for row in cursor.fetchall():
                projects.append({
                    'id': row[0],
                    'name': row[1],
                    'link': row[2],
                    'status': row[3],
                    'approved_by': row[4],
                    'approved_at': row[5],
                    'created_at': row[6]
                })
            return projects
        except Exception as e:
            print(f"Tasdiqlangan loyihalarni olishda xato: {e}")
            return []
        finally:
            conn.close()

    def complete_withdrawal(self, user_id: int, amount: int):
        """Pul chiqarishni yakunlash va balansni 0 qilish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Balansni 0 qilish va total_withdrawn ni yangilash
            cursor.execute("""
                UPDATE users SET 
                balance = 0,
                pending_balance = 0,
                total_withdrawn = total_withdrawn + ?,
                updated_at = ?
                WHERE id = ?
            """, (amount, datetime.now(), user_id))
            
            # Withdrawal status ni 'completed' qilish
            cursor.execute("""
                UPDATE withdrawal_requests SET 
                status = 'completed',
                processed_at = ?
                WHERE user_id = ? AND status = 'pending'
            """, (datetime.now(), user_id))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Pul chiqarishni yakunlashda xato: {e}")
            return False
        finally:
            conn.close()
    
    def reject_withdrawal(self, user_id: int):
        """Pul chiqarishni rad etish va balansni qaytarish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Eng so'nggi pending withdrawal ni olish
            cursor.execute("""
                SELECT amount FROM withdrawal_requests 
                WHERE user_id = ? AND status = 'pending'
            """, (user_id,))
            
            result = cursor.fetchone()
            if result:
                amount = result[0]
                
                # Balansni qaytarish
                cursor.execute("""
                    UPDATE users SET 
                    balance = balance + ?,
                    pending_balance = 0,
                    updated_at = ?
                    WHERE id = ?
                """, (amount, datetime.now(), user_id))
                
                # Withdrawal status ni 'rejected' qilish
                cursor.execute("""
                    UPDATE withdrawal_requests SET 
                    status = 'rejected',
                    processed_at = ?
                    WHERE user_id = ? AND status = 'pending'
                """, (datetime.now(), user_id))
                
                conn.commit()
                return True
            return False
        except Exception as e:
            print(f"Pul chiqarishni rad etishda xato: {e}")
            return False
        finally:
            conn.close()
    
    def get_withdrawal_notification(self, withdrawal_id: int):
        """Pul chiqarish so'rovini ID bo'yicha olish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Withdrawal ID bo'yicha ma'lumotni olish (foydalanuvchi bilan birga)
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
                WHERE wr.id = ?
            """, (withdrawal_id,))
            
            result = cursor.fetchone()
            if result:
                return {
                    'user_id': result[0],  # user_id
                    'amount': result[1],   # amount
                    'method': result[2],   # method
                    'account_details': result[3],  # account_details
                    'processed_at': result[4],     # processed_at
                    'created_at': result[5],       # created_at
                    'telegram_id': result[6],      # telegram_id
                    'language': result[7] or 'uz' if result[7] else 'uz'  # language
                }
            return None
        except Exception as e:
            print(f"Pul o'tkazish ma'lumotini olishda xato: {e}")
            return None
        finally:
            conn.close()
    
    def get_user_withdrawal_history(self, user_id: int):
        """Foydalanuvchining pul chiqarish tarixini olish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT amount, method, account_details, status, processed_at, created_at
                FROM withdrawal_requests 
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))
            
            withdrawals = []
            for row in cursor.fetchall():
                withdrawals.append({
                    'amount': row[0],
                    'method': row[1],
                    'account_details': row[2],
                    'status': row[3],
                    'processed_at': row[4],
                    'created_at': row[5]
                })
            return withdrawals
        except Exception as e:
            print(f"Pul chiqarish tarixini olishda xato: {e}")
            return []
        finally:
            conn.close()
    
    def get_top_voters(self, limit=10):
        """Eng ko'p ovoz bergan foydalanuvchilarni olish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    u.first_name,
                    u.telegram_id,
                    COUNT(bh.id) as vote_count
                FROM users u
                LEFT JOIN balance_history bh ON u.id = bh.user_id AND bh.type = 'payment' AND bh.status = 'approved'
                WHERE u.is_active = 1
                GROUP BY u.id, u.first_name, u.telegram_id
                HAVING vote_count > 0
                ORDER BY vote_count DESC
                LIMIT ?
            """, (limit,))
            
            top_voters = []
            for row in cursor.fetchall():
                top_voters.append({
                    'first_name': row[0] or 'Noma\'lum',
                    'telegram_id': row[1],
                    'vote_count': row[2]
                })
            return top_voters
        except Exception as e:
            print(f"Eng ko'p ovoz bergan foydalanuvchilarni olishda xato: {e}")
            return []
        finally:
            conn.close()

    def get_all_active_users(self):
        """Barcha faol foydalanuvchilarni olish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT telegram_id, first_name, language
                FROM users
                WHERE is_active = 1
                ORDER BY created_at DESC
            """)
            users = []
            for row in cursor.fetchall():
                users.append({
                    'telegram_id': row[0],
                    'first_name': row[1] or 'Noma\'lum',
                    'language': row[2] or 'uz'
                })
            return users
        except Exception as e:
            print(f"Barcha faol foydalanuvchilarni olishda xato: {e}")
            return []
        finally:
            conn.close()

    def create_announcement(self, title, content, language, created_by):
        """Yangi yangilik yaratish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO announcements (title, content, language, created_by, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (title, content, language, created_by, datetime.now()))
            
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"Yangilik yaratishda xato: {e}")
            return None
        finally:
            conn.close()

    def get_last_announcement(self, language='uz'):
        """Oxirgi yangilikni olish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT title, content, created_at, created_by
                FROM announcements
                WHERE language = ? AND is_active = 1
                ORDER BY created_at DESC
                LIMIT 1
            """, (language,))
            
            result = cursor.fetchone()
            if result:
                return {
                    'title': result[0],
                    'content': result[1],
                    'created_at': result[2],
                    'created_by': result[3]
                }
            return None
        except Exception as e:
            print(f"Oxirgi yangilikni olishda xato: {e}")
            return None
        finally:
            conn.close()

    def get_announcements_count(self, language='uz'):
        """Yangiliklar sonini olish"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*)
                FROM announcements
                WHERE language = ? AND is_active = 1
            """, (language,))
            
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            print(f"Yangiliklar sonini olishda xato: {e}")
            return 0
        finally:
            conn.close()

    def delete_project(self, project_id):
        """Loyihani o'chirish va barcha bog'liq ma'lumotlarni tozalash (ham projects ham approved_projects jadvallaridan)"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Avval projects jadvalidan loyihani qidirish
            cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            project = cursor.fetchone()
            
            if project:
                # Loyiha nomini saqlash (xabar uchun)
                project_name = project['name']
                
                # Bog'liq ovozlarni o'chirish
                cursor.execute("DELETE FROM votes WHERE project_id = ?", (project_id,))
                
                # Loyihani o'chirish
                cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                
                conn.commit()
                return True, project_name
            
            # Agar projects da topilmasa, approved_projects dan qidirish
            cursor.execute("SELECT * FROM approved_projects WHERE id = ?", (project_id,))
            project = cursor.fetchone()
            
            if project:
                # Loyiha nomini saqlash (xabar uchun)
                project_name = project['name']
                
                # approved_projects dan loyihani o'chirish
                cursor.execute("DELETE FROM approved_projects WHERE id = ?", (project_id,))
                
                conn.commit()
                return True, project_name
            
            return False, "Loyiha topilmadi"
            
        except Exception as e:
            print(f"Loyihani o'chirishda xato: {e}")
            return False, f"Xato yuz berdi: {e}"
        finally:
            conn.close()

    def get_project_by_id(self, project_id):
        """ID bo'yicha loyihani olish (ham projects ham approved_projects jadvallaridan)"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Avval projects jadvalidan qidirish
            cursor.execute("""
                SELECT * FROM projects WHERE id = ?
            """, (project_id,))
            
            result = cursor.fetchone()
            if result:
                return dict(result)
            
            # Agar projects da topilmasa, approved_projects dan qidirish
            cursor.execute("""
                SELECT id, name, link, status, approved_by, approved_at, created_at
                FROM approved_projects WHERE id = ?
            """, (project_id,))
            
            result = cursor.fetchone()
            if result:
                return dict(result)
            
            return None
        except Exception as e:
            print(f"Loyihani olishda xato: {e}")
            return None
        finally:
            conn.close()
