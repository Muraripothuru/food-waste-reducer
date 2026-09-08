import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os
import hashlib
import secrets


class FoodDatabase:
    _instance = None
    _conn = None

    def __new__(cls, db_path: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = None):
        if self._initialized:
            return
        self._initialized = True
        
        if db_path is None:
            if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
                db_path = ":memory:"
            else:
                db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "food_waste.db")
        
        self.db_path = db_path
        self._connect()
        self._init_db()

    def _connect(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def _get_conn(self):
        if self._conn is None:
            self._connect()
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT DEFAULT '',
                salt TEXT DEFAULT '',
                full_name TEXT DEFAULT '',
                avatar_color TEXT DEFAULT '#6366f1',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_login TEXT,
                provider TEXT DEFAULT '',
                provider_id TEXT DEFAULT ''
            );
            
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                default_shelf_life_days INTEGER NOT NULL,
                storage_tip TEXT DEFAULT '',
                icon TEXT DEFAULT 'fa-box'
            );
            
            CREATE TABLE IF NOT EXISTS food_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                purchase_date TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                quantity REAL DEFAULT 1,
                unit TEXT DEFAULT 'pcs',
                storage_location TEXT DEFAULT 'fridge',
                notes TEXT DEFAULT '',
                is_consumed INTEGER DEFAULT 0,
                is_wasted INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (category_id) REFERENCES categories(id)
            );
            
            CREATE TABLE IF NOT EXISTS waste_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                food_item_id INTEGER NOT NULL,
                waste_date TEXT NOT NULL,
                reason TEXT DEFAULT 'expired',
                estimated_cost REAL DEFAULT 0,
                notes TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (food_item_id) REFERENCES food_items(id)
            );
            
            CREATE TABLE IF NOT EXISTS shopping_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_name TEXT NOT NULL,
                category TEXT,
                quantity REAL DEFAULT 1,
                unit TEXT DEFAULT 'pcs',
                is_purchased INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                endpoint TEXT NOT NULL,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        
        for table in ["food_items", "waste_log", "shopping_list"]:
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            if "user_id" not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
        
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        if "provider" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN provider TEXT DEFAULT ''")
        if "provider_id" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN provider_id TEXT DEFAULT ''")
        
        conn.commit()
        self._seed_categories()

    def _seed_categories(self):
        conn = self._get_conn()
        categories = [
            ("Dairy", 7, "Keep at 4C or below", "fa-cheese"),
            ("Meat", 3, "Store in coldest part of fridge", "fa-drumstick-bite"),
            ("Seafood", 2, "Use within 1-2 days of purchase", "fa-fish"),
            ("Vegetables", 5, "Store in crisper drawer", "fa-carrot"),
            ("Fruits", 7, "Keep separate - some release ethylene", "fa-apple-whole"),
            ("Bread", 5, "Freeze for longer storage", "fa-bread-slice"),
            ("Grains", 180, "Store in airtight containers", "fa-seedling"),
            ("Canned Goods", 365, "Store in cool, dry place", "fa-can"),
            ("Frozen", 90, "Keep at -18C or below", "fa-snowflake"),
            ("Beverages", 30, "Check best-before date", "fa-glass-water"),
            ("Snacks", 30, "Store in cool, dry place", "fa-cookie"),
            ("Condiments", 90, "Refrigerate after opening", "fa-bottle-droplet"),
            ("Leftovers", 3, "Consume within 3 days", "fa-plate-wheat"),
            ("Bakery", 4, "Freeze if not consuming within 2 days", "fa-cake-candles"),
            ("Other", 7, "Check packaging for guidance", "fa-box"),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO categories (name, default_shelf_life_days, storage_tip, icon) VALUES (?, ?, ?, ?)",
            categories
        )
        conn.commit()

    def get_categories(self) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
        return [dict(row) for row in rows]

    def get_category_by_name(self, name: str) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM categories WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def add_item(self, name: str, category: str, purchase_date: str, expiry_date: str,
                 quantity: float = 1, unit: str = "pcs", storage_location: str = "fridge",
                 notes: str = "", user_id: int = None) -> int:
        cat = self.get_category_by_name(category)
        cat_id = cat["id"] if cat else self._get_or_create_category(category)
        conn = self._get_conn()
        cursor = conn.execute("""
            INSERT INTO food_items (user_id, name, category_id, purchase_date, expiry_date,
                                   quantity, unit, storage_location, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, name, cat_id, purchase_date, expiry_date, quantity, unit, storage_location, notes))
        conn.commit()
        return cursor.lastrowid

    def _get_or_create_category(self, name: str) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
        if row:
            return row["id"]
        cursor = conn.execute(
            "INSERT INTO categories (name, default_shelf_life_days, storage_tip, icon) VALUES (?, 7, 'Check packaging', 'fa-box')",
            (name,)
        )
        conn.commit()
        return cursor.lastrowid

    def get_all_items(self, user_id: int = None) -> List[Dict]:
        conn = self._get_conn()
        if user_id:
            rows = conn.execute("""
                SELECT f.*, c.name as category_name, c.default_shelf_life_days, c.icon as category_icon
                FROM food_items f
                JOIN categories c ON f.category_id = c.id
                WHERE f.user_id = ? AND f.is_consumed = 0 AND f.is_wasted = 0
                ORDER BY f.expiry_date ASC
            """, (user_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT f.*, c.name as category_name, c.default_shelf_life_days, c.icon as category_icon
                FROM food_items f
                JOIN categories c ON f.category_id = c.id
                WHERE f.is_consumed = 0 AND f.is_wasted = 0
                ORDER BY f.expiry_date ASC
            """).fetchall()
        return [dict(row) for row in rows]

    def get_item_by_id(self, item_id: int, user_id: int = None) -> Optional[Dict]:
        conn = self._get_conn()
        if user_id:
            row = conn.execute("""
                SELECT f.*, c.name as category_name, c.default_shelf_life_days
                FROM food_items f
                JOIN categories c ON f.category_id = c.id
                WHERE f.id = ? AND f.user_id = ?
            """, (item_id, user_id)).fetchone()
        else:
            row = conn.execute("""
                SELECT f.*, c.name as category_name, c.default_shelf_life_days
                FROM food_items f
                JOIN categories c ON f.category_id = c.id
                WHERE f.id = ?
            """, (item_id,)).fetchone()
        return dict(row) if row else None

    def get_expiring_items(self, days: int = 3, user_id: int = None) -> List[Dict]:
        conn = self._get_conn()
        future_date = (datetime.now().date() + timedelta(days=days)).isoformat()
        if user_id:
            rows = conn.execute("""
                SELECT f.*, c.name as category_name, c.default_shelf_life_days
                FROM food_items f
                JOIN categories c ON f.category_id = c.id
                WHERE f.user_id = ? AND f.is_consumed = 0 AND f.is_wasted = 0
                AND f.expiry_date <= ?
                ORDER BY f.expiry_date ASC
            """, (user_id, future_date)).fetchall()
        else:
            rows = conn.execute("""
                SELECT f.*, c.name as category_name, c.default_shelf_life_days
                FROM food_items f
                JOIN categories c ON f.category_id = c.id
                WHERE f.is_consumed = 0 AND f.is_wasted = 0
                AND f.expiry_date <= ?
                ORDER BY f.expiry_date ASC
            """, (future_date,)).fetchall()
        return [dict(row) for row in rows]

    def search_items(self, query: str = "", category: str = "", storage: str = "", 
                     status: str = "", user_id: int = None) -> List[Dict]:
        conn = self._get_conn()
        conditions = ["f.is_consumed = 0", "f.is_wasted = 0"]
        params = []

        if user_id:
            conditions.append("f.user_id = ?")
            params.append(user_id)
        if query:
            conditions.append("(f.name LIKE ? OR f.notes LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])
        if category:
            conditions.append("c.name = ?")
            params.append(category)
        if storage:
            conditions.append("f.storage_location = ?")
            params.append(storage)

        where_clause = " AND ".join(conditions)
        rows = conn.execute(f"""
            SELECT f.*, c.name as category_name, c.default_shelf_life_days
            FROM food_items f
            JOIN categories c ON f.category_id = c.id
            WHERE {where_clause}
            ORDER BY f.expiry_date ASC
        """, params).fetchall()
        items = [dict(row) for row in rows]

        if status:
            today = datetime.now().date()
            filtered = []
            for item in items:
                days_left = (datetime.strptime(item["expiry_date"], "%Y-%m-%d").date() - today).days
                if status == "expired" and days_left < 0:
                    filtered.append(item)
                elif status == "expiring" and 0 <= days_left <= 3:
                    filtered.append(item)
                elif status == "fresh" and days_left > 5:
                    filtered.append(item)
            return filtered

        return items

    def update_item(self, item_id: int, name: str, category: str, purchase_date: str,
                    expiry_date: str, quantity: float, unit: str, storage_location: str, 
                    notes: str, user_id: int = None) -> bool:
        cat = self.get_category_by_name(category)
        cat_id = cat["id"] if cat else self._get_or_create_category(category)
        conn = self._get_conn()
        if user_id:
            cursor = conn.execute("""
                UPDATE food_items
                SET name = ?, category_id = ?, purchase_date = ?, expiry_date = ?,
                    quantity = ?, unit = ?, storage_location = ?, notes = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
            """, (name, cat_id, purchase_date, expiry_date, quantity, unit, storage_location, notes, item_id, user_id))
        else:
            cursor = conn.execute("""
                UPDATE food_items
                SET name = ?, category_id = ?, purchase_date = ?, expiry_date = ?,
                    quantity = ?, unit = ?, storage_location = ?, notes = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (name, cat_id, purchase_date, expiry_date, quantity, unit, storage_location, notes, item_id))
        conn.commit()
        return cursor.rowcount > 0

    def mark_consumed(self, item_id: int, user_id: int = None) -> bool:
        conn = self._get_conn()
        if user_id:
            cursor = conn.execute("UPDATE food_items SET is_consumed = 1 WHERE id = ? AND user_id = ?", (item_id, user_id))
        else:
            cursor = conn.execute("UPDATE food_items SET is_consumed = 1 WHERE id = ?", (item_id,))
        conn.commit()
        return cursor.rowcount > 0

    def mark_wasted(self, item_id: int, reason: str = "expired", estimated_cost: float = 0, user_id: int = None) -> bool:
        conn = self._get_conn()
        if user_id:
            conn.execute("UPDATE food_items SET is_wasted = 1 WHERE id = ? AND user_id = ?", (item_id, user_id))
        else:
            conn.execute("UPDATE food_items SET is_wasted = 1 WHERE id = ?", (item_id,))
        conn.execute("""
            INSERT INTO waste_log (user_id, food_item_id, waste_date, reason, estimated_cost)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, item_id, datetime.now().date().isoformat(), reason, estimated_cost))
        conn.commit()
        return True

    def delete_item(self, item_id: int, user_id: int = None) -> bool:
        conn = self._get_conn()
        if user_id:
            cursor = conn.execute("DELETE FROM food_items WHERE id = ? AND user_id = ?", (item_id, user_id))
        else:
            cursor = conn.execute("DELETE FROM food_items WHERE id = ?", (item_id,))
        conn.commit()
        return cursor.rowcount > 0

    def get_waste_stats(self, days: int = 30, user_id: int = None) -> Dict:
        conn = self._get_conn()
        start_date = (datetime.now().date() - timedelta(days=days)).isoformat()
        
        if user_id:
            row = conn.execute("""
                SELECT COUNT(*) as total_wasted, COALESCE(SUM(estimated_cost), 0) as total_cost
                FROM waste_log WHERE user_id = ? AND waste_date >= ?
            """, (user_id, start_date)).fetchone()
            
            reasons = conn.execute("""
                SELECT reason, COUNT(*) as count, COALESCE(SUM(estimated_cost), 0) as cost
                FROM waste_log WHERE user_id = ? AND waste_date >= ?
                GROUP BY reason ORDER BY count DESC
            """, (user_id, start_date)).fetchall()
        else:
            row = conn.execute("""
                SELECT COUNT(*) as total_wasted, COALESCE(SUM(estimated_cost), 0) as total_cost
                FROM waste_log WHERE waste_date >= ?
            """, (start_date,)).fetchone()
            
            reasons = conn.execute("""
                SELECT reason, COUNT(*) as count, COALESCE(SUM(estimated_cost), 0) as cost
                FROM waste_log WHERE waste_date >= ?
                GROUP BY reason ORDER BY count DESC
            """, (start_date,)).fetchall()
        
        return {
            "period_days": days,
            "total_items_wasted": row["total_wasted"],
            "total_cost_lost": round(row["total_cost"], 2),
            "waste_by_reason": [dict(r) for r in reasons]
        }

    def get_daily_waste(self, days: int = 7, user_id: int = None) -> List[Dict]:
        conn = self._get_conn()
        result = []
        for i in range(days - 1, -1, -1):
            date = (datetime.now().date() - timedelta(days=i)).isoformat()
            if user_id:
                row = conn.execute("""
                    SELECT COUNT(*) as count, COALESCE(SUM(estimated_cost), 0) as cost
                    FROM waste_log WHERE user_id = ? AND waste_date = ?
                """, (user_id, date)).fetchone()
            else:
                row = conn.execute("""
                    SELECT COUNT(*) as count, COALESCE(SUM(estimated_cost), 0) as cost
                    FROM waste_log WHERE waste_date = ?
                """, (date,)).fetchone()
            result.append({
                "date": date,
                "count": row["count"],
                "cost": round(row["cost"], 2)
            })
        return result

    def get_shopping_items(self, user_id: int = None) -> List[Dict]:
        conn = self._get_conn()
        if user_id:
            rows = conn.execute("SELECT * FROM shopping_list WHERE user_id = ? AND is_purchased = 0 ORDER BY created_at DESC", (user_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM shopping_list WHERE is_purchased = 0 ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def add_shopping_item(self, name: str, category: str = "", quantity: float = 1, 
                          unit: str = "pcs", user_id: int = None) -> int:
        conn = self._get_conn()
        cursor = conn.execute("""
            INSERT INTO shopping_list (user_id, item_name, category, quantity, unit)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, name, category, quantity, unit))
        conn.commit()
        return cursor.lastrowid

    def mark_shopping_purchased(self, item_id: int, user_id: int = None) -> bool:
        conn = self._get_conn()
        if user_id:
            cursor = conn.execute("UPDATE shopping_list SET is_purchased = 1 WHERE id = ? AND user_id = ?", (item_id, user_id))
        else:
            cursor = conn.execute("UPDATE shopping_list SET is_purchased = 1 WHERE id = ?", (item_id,))
        conn.commit()
        return cursor.rowcount > 0

    def delete_shopping_item(self, item_id: int, user_id: int = None) -> bool:
        conn = self._get_conn()
        if user_id:
            cursor = conn.execute("DELETE FROM shopping_list WHERE id = ? AND user_id = ?", (item_id, user_id))
        else:
            cursor = conn.execute("DELETE FROM shopping_list WHERE id = ?", (item_id,))
        conn.commit()
        return cursor.rowcount > 0

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ==================== USER AUTHENTICATION ====================
    
    def _hash_password(self, password: str, salt: str = None) -> tuple:
        if salt is None:
            salt = secrets.token_hex(16)
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return password_hash.hex(), salt
    
    def create_user(self, username: str, email: str, password: str, full_name: str = "") -> Dict:
        conn = self._get_conn()
        
        existing = conn.execute("SELECT id FROM users WHERE username = ? OR email = ?", 
                               (username, email)).fetchone()
        if existing:
            return {"success": False, "message": "Username or email already exists"}
        
        password_hash, salt = self._hash_password(password)
        colors = ['#6366f1', '#8b5cf6', '#ec4899', '#06b6d4', '#10b981', '#f59e0b', '#ef4444']
        avatar_color = colors[hash(username) % len(colors)]
        
        cursor = conn.execute("""
            INSERT INTO users (username, email, password_hash, salt, full_name, avatar_color)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, email, password_hash, salt, full_name, avatar_color))
        conn.commit()
        
        return {"success": True, "user_id": cursor.lastrowid, "message": "Account created successfully"}
    
    def get_or_create_oauth_user(self, provider: str, provider_user_id: str, 
                                   email: str, name: str = "", avatar_url: str = "") -> Dict:
        conn = self._get_conn()
        
        user = conn.execute(
            "SELECT * FROM users WHERE provider = ? AND provider_id = ?",
            (provider, provider_user_id)
        ).fetchone()
        
        if user:
            conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
            conn.commit()
            return {
                "success": True,
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "full_name": user["full_name"],
                    "avatar_color": user["avatar_color"]
                }
            }
        
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET provider = ?, provider_id = ? WHERE id = ?",
                (provider, provider_user_id, existing["id"])
            )
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE id = ?", (existing["id"],)).fetchone()
            return {
                "success": True,
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "full_name": user["full_name"],
                    "avatar_color": user["avatar_color"]
                }
            }
        
        username = email.split("@")[0]
        base_username = username
        counter = 1
        while conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            username = f"{base_username}{counter}"
            counter += 1
        
        colors = ['#6366f1', '#8b5cf6', '#ec4899', '#06b6d4', '#10b981', '#f59e0b', '#ef4444']
        avatar_color = colors[hash(username) % len(colors)]
        
        cursor = conn.execute("""
            INSERT INTO users (username, email, password_hash, salt, full_name, avatar_color, provider, provider_id)
            VALUES (?, ?, '', '', ?, ?, ?, ?)
        """, (username, email, name, avatar_color, provider, provider_user_id))
        conn.commit()
        
        return {
            "success": True,
            "user": {
                "id": cursor.lastrowid,
                "username": username,
                "email": email,
                "full_name": name,
                "avatar_color": avatar_color
            }
        }
    
    def authenticate_user(self, username: str, password: str) -> Dict:
        conn = self._get_conn()
        user = conn.execute("SELECT * FROM users WHERE username = ? OR email = ?", 
                           (username, username)).fetchone()
        
        if not user:
            return {"success": False, "message": "User not found"}
        
        password_hash, _ = self._hash_password(password, user["salt"])
        
        if password_hash != user["password_hash"]:
            return {"success": False, "message": "Invalid password"}
        
        conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
        conn.commit()
        
        return {
            "success": True,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "full_name": user["full_name"],
                "avatar_color": user["avatar_color"]
            }
        }
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if user:
            return {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "full_name": user["full_name"],
                "avatar_color": user["avatar_color"],
                "created_at": user["created_at"],
                "last_login": user["last_login"]
            }
        return None
    
    def update_user_profile(self, user_id: int, full_name: str, email: str) -> bool:
        conn = self._get_conn()
        try:
            conn.execute("UPDATE users SET full_name = ?, email = ? WHERE id = ?",
                        (full_name, email, user_id))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def change_password(self, user_id: int, old_password: str, new_password: str) -> Dict:
        conn = self._get_conn()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        
        if not user:
            return {"success": False, "message": "User not found"}
        
        old_hash, _ = self._hash_password(old_password, user["salt"])
        if old_hash != user["password_hash"]:
            return {"success": False, "message": "Current password is incorrect"}
        
        new_hash, new_salt = self._hash_password(new_password)
        conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
                    (new_hash, new_salt, user_id))
        conn.commit()
        
        return {"success": True, "message": "Password changed successfully"}
    
    def get_user_stats(self, user_id: int) -> Dict:
        conn = self._get_conn()
        
        items = conn.execute("""
            SELECT COUNT(*) as total FROM food_items 
            WHERE user_id = ? AND is_consumed = 0 AND is_wasted = 0
        """, (user_id,)).fetchone()
        
        consumed = conn.execute("""
            SELECT COUNT(*) as total FROM food_items 
            WHERE user_id = ? AND is_consumed = 1
        """, (user_id,)).fetchone()
        
        wasted = conn.execute("""
            SELECT COUNT(*) as total FROM food_items 
            WHERE user_id = ? AND is_wasted = 1
        """, (user_id,)).fetchone()
        
        return {
            "total_items": items["total"],
            "consumed": consumed["total"],
            "wasted": wasted["total"]
        }

    # ==================== PUSH NOTIFICATIONS ====================
    
    def save_push_subscription(self, subscription: Dict, user_id: int = None):
        conn = self._get_conn()
        endpoint = subscription.get("endpoint", "")
        keys = subscription.get("keys", {})
        p256dh = keys.get("p256dh", "")
        auth = keys.get("auth", "")
        
        existing = conn.execute(
            "SELECT id FROM push_subscriptions WHERE endpoint = ? AND user_id = ?",
            (endpoint, user_id)
        ).fetchone()
        
        if not existing:
            conn.execute(
                "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (?, ?, ?, ?)",
                (user_id, endpoint, p256dh, auth)
            )
            conn.commit()
    
    def remove_push_subscription(self, subscription: Dict, user_id: int = None):
        conn = self._get_conn()
        endpoint = subscription.get("endpoint", "")
        conn.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = ? AND user_id = ?",
            (endpoint, user_id)
        )
        conn.commit()
    
    def get_push_subscriptions(self, user_id: int = None) -> List[Dict]:
        conn = self._get_conn()
        if user_id:
            rows = conn.execute(
                "SELECT * FROM push_subscriptions WHERE user_id = ?",
                (user_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM push_subscriptions").fetchall()
        return [dict(row) for row in rows]
