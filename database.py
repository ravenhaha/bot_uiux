"""
Модуль работы с базой данных SQLite
"""

import sqlite3
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import contextmanager


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        """Контекстный менеджер для соединения с БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def _init_db(self):
        """Инициализация таблиц"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица питомцев
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id)
                )
            """)
            
            # Таблица записей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pet_id INTEGER NOT NULL,
                    text TEXT,
                    photo_id TEXT,
                    tag TEXT,
                    description TEXT,
                    is_visit INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (pet_id) REFERENCES pets(id)
                )
            """)
            
            # Таблица напоминаний
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    pet_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    remind_at TIMESTAMP NOT NULL,
                    status TEXT DEFAULT 'pending',
                    sent INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (pet_id) REFERENCES pets(id)
                )
            """)
            
            # Таблица супервизоров
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS supervisors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица запросов на расшифровку
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcription_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    pet_id INTEGER NOT NULL,
                    pdf_file_id TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    supervisor_id INTEGER,
                    transcription TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (pet_id) REFERENCES pets(id),
                    FOREIGN KEY (supervisor_id) REFERENCES supervisors(id)
                )
            """)
            
            # Индексы для быстрого поиска
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pets_user ON pets(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_pet ON records(pet_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminders_pet ON reminders(pet_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminders_time ON reminders(remind_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transcription_status ON transcription_requests(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_supervisors_user ON supervisors(user_id)")
    
    # === Питомцы ===
    
    def create_pet(self, user_id: int, name: str, pet_type: str) -> int:
        """Создать питомца"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO pets (user_id, name, type) VALUES (?, ?, ?)",
                (user_id, name, pet_type)
            )
            return cursor.lastrowid
    
    def get_pet(self, user_id: int) -> Optional[Dict]:
        """Получить питомца пользователя"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pets WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_pet_by_id(self, pet_id: int) -> Optional[Dict]:
        """Получить питомца по ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pets WHERE id = ?", (pet_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # === Записи ===
    
    def create_record(
        self, 
        pet_id: int, 
        text: str = None, 
        photo_id: str = None, 
        tag: str = None,
        description: str = None,
        is_visit: bool = False
    ) -> int:
        """Создать запись"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO records (pet_id, text, photo_id, tag, description, is_visit) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (pet_id, text, photo_id, tag, description, int(is_visit))
            )
            return cursor.lastrowid
    
    def get_records(self, pet_id: int, limit: int = 20) -> List[Dict]:
        """Получить записи питомца"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM records 
                   WHERE pet_id = ? 
                   ORDER BY created_at DESC 
                   LIMIT ?""",
                (pet_id, limit)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_visits(self, pet_id: int, limit: int = 20) -> List[Dict]:
        """Получить визиты к врачу"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM records 
                   WHERE pet_id = ? AND is_visit = 1
                   ORDER BY created_at DESC 
                   LIMIT ?""",
                (pet_id, limit)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def update_record(self, record_id: int, tag: str = None, description: str = None, is_visit: bool = None):
        """Обновить запись (для визарда)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if tag is not None:
                updates.append("tag = ?")
                params.append(tag)
            
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            
            if is_visit is not None:
                updates.append("is_visit = ?")
                params.append(int(is_visit))
            
            if updates:
                params.append(record_id)
                cursor.execute(
                    f"UPDATE records SET {', '.join(updates)} WHERE id = ?",
                    params
                )
    
    # === Напоминания ===
    
    def create_reminder(self, user_id: int, pet_id: int, text: str, remind_at: datetime) -> int:
        """Создать напоминание"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO reminders (user_id, pet_id, text, remind_at) 
                   VALUES (?, ?, ?, ?)""",
                (user_id, pet_id, text, remind_at.isoformat())
            )
            return cursor.lastrowid
    
    def get_pending_reminders(self) -> List[Dict]:
        """Получить напоминания, которые пора отправить"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute(
                """SELECT * FROM reminders 
                   WHERE remind_at <= ? AND sent = 0 AND status = 'pending'
                   ORDER BY remind_at ASC""",
                (now,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def mark_reminder_sent(self, reminder_id: int):
        """Отметить напоминание как отправленное"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET sent = 1 WHERE id = ?",
                (reminder_id,)
            )
    
    def update_reminder_status(self, reminder_id: int, status: str):
        """Обновить статус напоминания"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET status = ? WHERE id = ?",
                (status, reminder_id)
            )
    
    def get_reminders_history(self, pet_id: int, limit: int = 20) -> List[Dict]:
        """Получить историю напоминаний"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM reminders 
                   WHERE pet_id = ? 
                   ORDER BY created_at DESC 
                   LIMIT ?""",
                (pet_id, limit)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_active_reminders(self, pet_id: int) -> List[Dict]:
        """Получить активные напоминания"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM reminders 
                   WHERE pet_id = ? AND status = 'pending'
                   ORDER BY remind_at ASC""",
                (pet_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    # === Супервизоры ===
    
    def add_supervisor(self, user_id: int, name: str = None) -> int:
        """Добавить супервизора"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO supervisors (user_id, name) VALUES (?, ?)",
                (user_id, name)
            )
            return cursor.lastrowid
    
    def remove_supervisor(self, user_id: int):
        """Удалить супервизора"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM supervisors WHERE user_id = ?",
                (user_id,)
            )
    
    def is_supervisor(self, user_id: int) -> bool:
        """Проверить, является ли пользователь супервизором"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM supervisors WHERE user_id = ?",
                (user_id,)
            )
            return cursor.fetchone() is not None
    
    def get_supervisor_by_user_id(self, user_id: int) -> Optional[Dict]:
        """Получить супервизора по user_id"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM supervisors WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_supervisors(self) -> List[Dict]:
        """Получить всех супервизоров"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM supervisors")
            return [dict(row) for row in cursor.fetchall()]
    
    # === Запросы на расшифровку ===
    
    def create_transcription_request(self, user_id: int, pet_id: int, pdf_file_id: str) -> int:
        """Создать запрос на расшифровку"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO transcription_requests (user_id, pet_id, pdf_file_id, status) 
                   VALUES (?, ?, ?, 'pending')""",
                (user_id, pet_id, pdf_file_id)
            )
            return cursor.lastrowid
    
    def get_transcription_request(self, request_id: int) -> Optional[Dict]:
        """Получить запрос на расшифровку по ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM transcription_requests WHERE id = ?",
                (request_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_pending_transcription_requests(self) -> List[Dict]:
        """Получить ожидающие запросы на расшифровку"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM transcription_requests 
                   WHERE status = 'pending'
                   ORDER BY created_at ASC"""
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def assign_transcription_to_supervisor(self, request_id: int, supervisor_id: int):
        """Назначить запрос супервизору"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE transcription_requests 
                   SET status = 'in_progress', supervisor_id = ? 
                   WHERE id = ?""",
                (supervisor_id, request_id)
            )
    
    def complete_transcription_request(self, request_id: int, transcription: str):
        """Завершить запрос на расшифровку"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE transcription_requests 
                   SET status = 'completed', 
                       transcription = ?,
                       completed_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (transcription, request_id)
            )
    
    def get_user_transcription_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получить историю расшифровок пользователя"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM transcription_requests 
                   WHERE user_id = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (user_id, limit)
            )
            return [dict(row) for row in cursor.fetchall()]
