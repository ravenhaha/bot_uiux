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
                    timezone TEXT DEFAULT '+03:00',
                    gender TEXT,
                    breed TEXT,
                    birth_date TEXT,
                    weight REAL,
                    vaccinations TEXT,
                    photo_id TEXT,
                    owner_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id)
                )
            """)
         
            # Миграции: добавляем недостающие колонки
            cursor.execute("PRAGMA table_info(pets)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'timezone' not in columns:
                cursor.execute("ALTER TABLE pets ADD COLUMN timezone TEXT DEFAULT '+03:00'")
            if 'gender' not in columns:
                cursor.execute("ALTER TABLE pets ADD COLUMN gender TEXT")
            if 'breed' not in columns:
                cursor.execute("ALTER TABLE pets ADD COLUMN breed TEXT")
            if 'birth_date' not in columns:
                cursor.execute("ALTER TABLE pets ADD COLUMN birth_date TEXT")
            if 'weight' not in columns:
                cursor.execute("ALTER TABLE pets ADD COLUMN weight REAL")
            if 'vaccinations' not in columns:
                cursor.execute("ALTER TABLE pets ADD COLUMN vaccinations TEXT")
            if 'photo_id' not in columns:
                cursor.execute("ALTER TABLE pets ADD COLUMN photo_id TEXT")
            if 'owner_name' not in columns:
                cursor.execute("ALTER TABLE pets ADD COLUMN owner_name TEXT")
            
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
                    day_of_week INTEGER,
                    time_of_day TEXT,
                    is_recurring INTEGER DEFAULT 0,
                    is_daily INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'pending',
                    sent INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (pet_id) REFERENCES pets(id)
                )
            """)

            # Миграция: добавляем новые поля если их нет
            cursor.execute("PRAGMA table_info(reminders)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'day_of_week' not in columns:
                cursor.execute("ALTER TABLE reminders ADD COLUMN day_of_week INTEGER")
            if 'time_of_day' not in columns:
                cursor.execute("ALTER TABLE reminders ADD COLUMN time_of_day TEXT")
            if 'is_recurring' not in columns:
                cursor.execute("ALTER TABLE reminders ADD COLUMN is_recurring INTEGER DEFAULT 0")
            if 'is_daily' not in columns:
                cursor.execute("ALTER TABLE reminders ADD COLUMN is_daily INTEGER DEFAULT 0")
            if 'is_active' not in columns:
                cursor.execute("ALTER TABLE reminders ADD COLUMN is_active INTEGER DEFAULT 1")
            
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
    
    def create_pet(self, user_id: int, name: str, pet_type: str, timezone: str = '+03:00') -> int:
        """Создать питомца (базовые поля, остальное дополняется позже)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO pets (user_id, name, type, timezone) VALUES (?, ?, ?, ?)",
                (user_id, name, pet_type, timezone)
            )
            return cursor.lastrowid

    def update_pet_timezone(self, user_id: int, timezone: str):
        """Обновить часовой пояс питомца"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pets SET timezone = ? WHERE user_id = ?",
                (timezone, user_id)
            )

    def update_pet_name(self, user_id: int, name: str):
        """Обновить имя питомца"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pets SET name = ? WHERE user_id = ?",
                (name, user_id)
            )

    def update_pet_type(self, user_id: int, pet_type: str):
        """Обновить тип питомца"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pets SET type = ? WHERE user_id = ?",
                (pet_type, user_id)
            )

    def update_pet_details(
        self,
        user_id: int,
        gender: Optional[str] = None,
        breed: Optional[str] = None,
        birth_date: Optional[str] = None,
        weight: Optional[float] = None,
        vaccinations: Optional[str] = None,
        photo_id: Optional[str] = None,
        owner_name: Optional[str] = None,
    ):
        """Обновить дополнительные сведения о питомце"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            params = []

            if gender is not None:
                updates.append("gender = ?")
                params.append(gender)
            if breed is not None:
                updates.append("breed = ?")
                params.append(breed)
            if birth_date is not None:
                updates.append("birth_date = ?")
                params.append(birth_date)
            if weight is not None:
                updates.append("weight = ?")
                params.append(weight)
            if vaccinations is not None:
                updates.append("vaccinations = ?")
                params.append(vaccinations)
            if photo_id is not None:
                updates.append("photo_id = ?")
                params.append(photo_id)
            if owner_name is not None:
                updates.append("owner_name = ?")
                params.append(owner_name)

            if updates:
                params.append(user_id)
                cursor.execute(
                    f"UPDATE pets SET {', '.join(updates)} WHERE user_id = ?",
                    params
                )

    def delete_pet(self, user_id: int):
        """Удалить питомца и все связанные данные"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Получаем pet_id
            cursor.execute("SELECT id FROM pets WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                pet_id = row[0]
                # Удаляем связанные записи
                cursor.execute("DELETE FROM records WHERE pet_id = ?", (pet_id,))
                cursor.execute("DELETE FROM reminders WHERE pet_id = ?", (pet_id,))
                cursor.execute("DELETE FROM transcription_requests WHERE pet_id = ?", (pet_id,))
            # Удаляем питомца
            cursor.execute("DELETE FROM pets WHERE user_id = ?", (user_id,))
    
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
    
    def get_all_records(self, pet_id: int) -> List[Dict]:
        """Получить все записи питомца (полная история)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM records 
                   WHERE pet_id = ? 
                   ORDER BY created_at DESC""",
                (pet_id,)
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
    
    def create_reminder(
        self,
        user_id: int,
        pet_id: int,
        text: str,
        remind_at: datetime,
        day_of_week: int = None,
        time_of_day: str = None,
        is_recurring: bool = False,
        is_daily: bool = False
    ) -> int:
        """Создать напоминание"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO reminders
                   (user_id, pet_id, text, remind_at, day_of_week, time_of_day, is_recurring, is_daily, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (user_id, pet_id, text, remind_at.isoformat(), day_of_week, time_of_day, int(is_recurring), int(is_daily))
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
                   WHERE pet_id = ? AND status = 'pending' AND is_active = 1
                   ORDER BY remind_at ASC""",
                (pet_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_user_reminders(self, user_id: int) -> List[Dict]:
        """Получить все напоминания пользователя (активные и приостановленные)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM reminders
                   WHERE user_id = ? AND status = 'pending'
                   ORDER BY remind_at ASC""",
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_reminder_by_id(self, reminder_id: int) -> Optional[Dict]:
        """Получить напоминание по ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_reminder(
        self,
        reminder_id: int,
        text: str = None,
        remind_at: datetime = None,
        day_of_week: int = None,
        time_of_day: str = None,
        is_recurring: bool = None,
        is_active: bool = None
    ):
        """Обновить напоминание"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            params = []

            if text is not None:
                updates.append("text = ?")
                params.append(text)
            if remind_at is not None:
                updates.append("remind_at = ?")
                params.append(remind_at.isoformat())
            if day_of_week is not None:
                updates.append("day_of_week = ?")
                params.append(day_of_week)
            if time_of_day is not None:
                updates.append("time_of_day = ?")
                params.append(time_of_day)
            if is_recurring is not None:
                updates.append("is_recurring = ?")
                params.append(int(is_recurring))
            if is_active is not None:
                updates.append("is_active = ?")
                params.append(int(is_active))

            if updates:
                params.append(reminder_id)
                cursor.execute(
                    f"UPDATE reminders SET {', '.join(updates)} WHERE id = ?",
                    params
                )

    def delete_reminder(self, reminder_id: int):
        """Удалить напоминание"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))

    def toggle_reminder_active(self, reminder_id: int, is_active: bool):
        """Включить/выключить напоминание"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET is_active = ? WHERE id = ?",
                (int(is_active), reminder_id)
            )

    def disable_reminder_recurring(self, reminder_id: int):
        """Отключить повторение напоминания"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET is_recurring = 0 WHERE id = ?",
                (reminder_id,)
            )

    def reset_reminder_for_next_week(self, reminder_id: int, next_remind_at: datetime):
        """Сбросить напоминание для следующей недели"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET remind_at = ?, sent = 0, status = 'pending' WHERE id = ?",
                (next_remind_at.isoformat(), reminder_id)
            )

    def get_recurring_reminders_to_confirm(self) -> List[Dict]:
        """Получить повторяющиеся напоминания для подтверждения (в конце недели)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM reminders
                   WHERE is_recurring = 1 AND is_active = 1 AND sent = 1 AND status != 'pending'
                   ORDER BY remind_at ASC"""
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
