# database/db_manager.py
import sqlite3
import json
from datetime import datetime
from pathlib import Path
import bcrypt
from typing import List, Optional, Dict


class DatabaseManager:
    def __init__(self, db_path='data/database/defect_system.db'):
        self.db_path = Path(__file__).parent.parent / db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    def get_connection(self):
        return sqlite3.connect(str(self.db_path))

    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'operator',
                real_name TEXT,
                department TEXT,
                email TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detection_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                image_path TEXT,
                result_image_path TEXT,
                source_type TEXT,
                total_detections INTEGER DEFAULT 0,
                detections_json TEXT,
                inference_time REAL,
                confidence_threshold REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                class_counts TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT,
                details TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        cursor.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
        if cursor.fetchone()[0] == 0:
            admin_password = self.hash_password('admin123')
            cursor.execute('''
                INSERT INTO users (username, password_hash, role, real_name, is_active)
                VALUES (?, ?, ?, ?, ?)
            ''', ('admin', admin_password, 'admin', '系统管理员', 1))

        conn.commit()
        conn.close()

    def hash_password(self, password: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, password: str, password_hash: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

    def create_user(self, username: str, password: str, role: str = 'operator',
                    real_name: str = '', department: str = '',
                    email: str = '', phone: str = '') -> bool:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            password_hash = self.hash_password(password)
            cursor.execute('''
                INSERT INTO users (username, password_hash, role, real_name, department, email, phone)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (username, password_hash, role, real_name, department, email, phone))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False

    def authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, password_hash, role, real_name, department, email, phone, is_active
            FROM users WHERE username = ?
        ''', (username,))
        user_data = cursor.fetchone()
        conn.close()

        if user_data and user_data[8] == 1:
            if self.verify_password(password, user_data[2]):
                return {
                    'id': user_data[0],
                    'username': user_data[1],
                    'role': user_data[3],
                    'real_name': user_data[4],
                    'department': user_data[5],
                    'email': user_data[6],
                    'phone': user_data[7]
                }
        return None

    def update_last_login(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()

    def update_user(self, user_id: int, **kwargs) -> bool:
        """
        更新用户信息

        Args:
            user_id: 用户ID
            **kwargs: 要更新的字段 (real_name, department, email, phone, role, is_active)

        Returns:
            bool: 是否更新成功
        """
        allowed_fields = ['real_name', 'department', 'email', 'phone', 'role', 'is_active']
        updates = []
        values = []

        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                values.append(value)

        if not updates:
            return False

        values.append(user_id)

        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", values)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"更新用户失败: {e}")
            return False

    def change_password(self, user_id: int, new_password: str) -> bool:
        """
        修改用户密码

        Args:
            user_id: 用户ID
            new_password: 新密码

        Returns:
            bool: 是否修改成功
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            password_hash = self.hash_password(new_password)
            cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"修改密码失败: {e}")
            return False

    def get_all_users(self) -> List[Dict]:
        """
        获取所有用户列表

        Returns:
            List[Dict]: 用户列表
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, role, real_name, department, email, phone, created_at, last_login, is_active
            FROM users ORDER BY id
        ''')
        users = cursor.fetchall()
        conn.close()

        return [{
            'id': u[0],
            'username': u[1],
            'role': u[2],
            'real_name': u[3],
            'department': u[4],
            'email': u[5],
            'phone': u[6],
            'created_at': u[7],
            'last_login': u[8],
            'is_active': u[9]
        } for u in users]

    def save_detection_record(self, record) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO detection_records 
            (user_id, username, image_path, result_image_path, source_type, 
             total_detections, detections_json, inference_time, confidence_threshold, class_counts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            record.user_id, record.username, record.image_path, record.result_image_path,
            record.source_type, record.total_detections, record.detections_json,
            record.inference_time, record.confidence_threshold, record.class_counts
        ))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return record_id

    def get_detection_history(self, user_id: int = None, limit: int = 100) -> List[Dict]:
        conn = self.get_connection()
        cursor = conn.cursor()

        if user_id:
            cursor.execute('''
                SELECT id, user_id, username, image_path, result_image_path, source_type,
                       total_detections, detections_json, inference_time, confidence_threshold,
                       created_at, class_counts
                FROM detection_records 
                WHERE user_id = ?
                ORDER BY created_at DESC LIMIT ?
            ''', (user_id, limit))
        else:
            cursor.execute('''
                SELECT id, user_id, username, image_path, result_image_path, source_type,
                       total_detections, detections_json, inference_time, confidence_threshold,
                       created_at, class_counts
                FROM detection_records 
                ORDER BY created_at DESC LIMIT ?
            ''', (limit,))

        records = cursor.fetchall()
        conn.close()

        return [{
            'id': r[0],
            'user_id': r[1],
            'username': r[2],
            'image_path': r[3],
            'result_image_path': r[4],
            'source_type': r[5],
            'total_detections': r[6],
            'detections_json': r[7],
            'inference_time': r[8],
            'confidence_threshold': r[9],
            'created_at': r[10],
            'class_counts': json.loads(r[11]) if r[11] else {}
        } for r in records]

    def get_statistics(self) -> Dict:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM detection_records")
        total_detections = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(total_detections) FROM detection_records")
        total_objects = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM detection_records WHERE DATE(created_at) = DATE('now')")
        today_detections = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        total_users = cursor.fetchone()[0]

        conn.close()

        return {
            'total_detections': total_detections,
            'total_objects': total_objects,
            'today_detections': today_detections,
            'total_users': total_users
        }

    def log_system_action(self, user_id: int, username: str, action: str,
                          details: str = '', ip_address: str = ''):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO system_logs (user_id, username, action, details, ip_address)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, action, details, ip_address))
        conn.commit()
        conn.close()