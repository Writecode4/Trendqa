import sqlite3
import os
from datetime import datetime


class Database:
    def __init__(self, db_name="trendqa.db"):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = os.path.join(base_dir, db_name)
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def column_exists(self, conn, table_name, column_name):
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        return column_name in [row[1] for row in cursor.fetchall()]

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    source_type TEXT NOT NULL,
                    base_url TEXT,
                    active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY,
                    source_id INTEGER,
                    title TEXT, content TEXT, url TEXT UNIQUE, author TEXT,
                    created_utc REAL, created_at TEXT, raw_json TEXT, item_type TEXT,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (source_id) REFERENCES sources (id) ON DELETE SET NULL
                )
            """)

            # Agrega columnas de forma segura (ignora si ya existen)
            try: cursor.execute("ALTER TABLE items ADD COLUMN topic TEXT DEFAULT ''")
            except: pass
            try: cursor.execute("ALTER TABLE items ADD COLUMN pais TEXT DEFAULT 'paraguay'")
            except: pass

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL, question TEXT NOT NULL, category TEXT,
                    confidence REAL, model_used TEXT, topic TEXT DEFAULT '',
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trend_terms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL, related_top TEXT, related_rising TEXT,
                    autocomplete TEXT, interest_over_time TEXT, geo TEXT DEFAULT 'PY',
                    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL, period_label TEXT, summary_json TEXT NOT NULL,
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processing_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    step TEXT NOT NULL, status TEXT NOT NULL, message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

    def ensure_source(self, name, source_type, base_url=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO sources (name, source_type, base_url)
                VALUES (?, ?, ?)
            """, (name, source_type, base_url))
            conn.commit()

            cursor.execute("SELECT id FROM sources WHERE name = ?", (name,))
            row = cursor.fetchone()
            return row[0] if row else None

    def save_item(self, item):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            item_id = item.get("id")
            url = item.get("url") or None
            source_id = item.get("source_id")
            title = item.get("title")
            content = item.get("content")
            topic = item.get("topic", "")
            pais = item.get("pais", "paraguay")

            if url:
                cursor.execute("SELECT id FROM items WHERE url = ?", (url,))
                existing = cursor.fetchone()
                if existing:
                    cursor.execute("""
                        UPDATE items SET source_id=?, title=?, content=?, topic=?, pais=?, scraped_at=CURRENT_TIMESTAMP
                        WHERE id=?
                    """, (source_id, title, content, topic, pais, existing[0]))
                    conn.commit()
                    return existing[0]

            if item_id:
                cursor.execute("SELECT id FROM items WHERE id = ?", (item_id,))
                if cursor.fetchone():
                    cursor.execute("""
                        UPDATE items SET source_id=?, title=?, content=?, url=?, topic=?, pais=?, scraped_at=CURRENT_TIMESTAMP
                        WHERE id=?
                    """, (source_id, title, content, url, topic, pais, item_id))
                    conn.commit()
                    return item_id

            cursor.execute("""
                INSERT INTO items
                (id, source_id, title, content, url, author, created_utc, created_at, raw_json, item_type, topic, pais)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_id, source_id, title, content, url, item.get("author"),
                item.get("created_utc"), item.get("created_at"), item.get("raw_json"),
                item.get("item_type", "post"), topic, pais
            ))
            conn.commit()
            return item_id

    def mark_item_processed(self, item_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE items
                SET processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (item_id,))
            conn.commit()

    def save_question(self, item_id, question, category, confidence=None, model_used=None, topic=""):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM items WHERE id = ?", (item_id,))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT OR IGNORE INTO items (id, title, content, item_type)
                    VALUES (?, ?, ?, 'placeholder')
                """, (item_id, question[:200], question))
            cursor.execute("""
                INSERT INTO questions (item_id, question, category, confidence, model_used, topic)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (item_id, question, category, confidence, model_used, topic))
            conn.commit()

    def save_trend_term(self, keyword, related_top=None, related_rising=None, autocomplete=None, interest_over_time=None, geo="PY"):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trend_terms
                (keyword, related_top, related_rising, autocomplete, interest_over_time, geo)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                keyword,
                related_top,
                related_rising,
                autocomplete,
                interest_over_time,
                geo
            ))
            conn.commit()

    def save_report(self, topic, period_label, summary_json):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reports (topic, period_label, summary_json)
                VALUES (?, ?, ?)
            """, (topic, period_label, summary_json))
            conn.commit()

    def log_step(self, step, status, message=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO processing_log (step, status, message)
                VALUES (?, ?, ?)
            """, (step, status, message))
            conn.commit()

    def get_unprocessed_items(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, content
                FROM items
                WHERE processed_at IS NULL
            """)
            return cursor.fetchall()

    def get_all_questions_with_items(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT q.question, q.category, q.confidence, q.model_used,
                       i.title, i.url, i.item_type, i.scraped_at, s.name, s.source_type
                FROM questions q
                JOIN items i ON q.item_id = i.id
                LEFT JOIN sources s ON i.source_id = s.id
                ORDER BY q.analyzed_at DESC
            """)
            return cursor.fetchall()

    def get_latest_report(self, topic=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if topic:
                cursor.execute("""
                    SELECT summary_json, generated_at
                    FROM reports
                    WHERE topic = ?
                    ORDER BY generated_at DESC
                    LIMIT 1
                """, (topic,))
            else:
                cursor.execute("""
                    SELECT summary_json, generated_at
                    FROM reports
                    ORDER BY generated_at DESC
                    LIMIT 1
                """)
            return cursor.fetchone()

    def get_question_trends(self, topic="", recent_days=30):
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=recent_days)).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT question, COUNT(*) as freq
                FROM questions
                WHERE topic = ? AND analyzed_at >= ?
                GROUP BY question
                ORDER BY freq DESC
                LIMIT 20
            """, (topic, cutoff))
            recent = dict(cursor.fetchall())
            cursor.execute("""
                SELECT question, COUNT(*) as freq
                FROM questions
                WHERE topic = ? AND analyzed_at < ?
                GROUP BY question
                ORDER BY freq DESC
                LIMIT 20
            """, (topic, cutoff))
            older = dict(cursor.fetchall())
        return recent, older

    def get_trend_terms(self, limit=50):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT keyword, related_top, related_rising, autocomplete, interest_over_time, geo, captured_at
                FROM trend_terms
                ORDER BY captured_at DESC
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()
