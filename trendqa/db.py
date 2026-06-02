import os
import time
import socket
import logging
import queue
import threading
from functools import wraps

import pymysql
from pymysql.cursors import DictCursor
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

POOL_SIZE = 5
MAX_RETRIES = 5
RETRY_DELAY = 1


def with_conn_retry(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                return fn(self, *args, **kwargs)
            except (pymysql.err.OperationalError, pymysql.err.InterfaceError) as e:
                last_exc = e
                logger.warning(f"DB error on {fn.__name__} (attempt {attempt+1}/{MAX_RETRIES}): {e}")
                self._recycle_all()
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
        raise last_exc
    return wrapper


class Database:
    _tables_initialized = False
    _init_lock = threading.Lock()

    def __init__(self, host=None, port=None, user=None, password=None, database=None):
        self.host = host or os.getenv("DB_HOST", "localhost")
        self.port = port or int(os.getenv("DB_PORT", 3306))
        self.user = user or os.getenv("DB_USER", "root")
        self.password = password or os.getenv("DB_PASSWORD", "")
        self.database = database or os.getenv("DB_NAME", "trendqa")
        self._pool = queue.Queue(maxsize=POOL_SIZE)
        self._pool_size = 0
        self._pool_lock = threading.Lock()
        self._ensure_tunnel()
        self._init_tables_once()

    def _ensure_tunnel(self):
        from trendqa.tunnel import tunnel_manager
        tunnel_manager.ensure_alive()

    def _init_tables_once(self):
        if Database._tables_initialized:
            return
        with Database._init_lock:
            if Database._tables_initialized:
                return
            self._init_tables()
            Database._tables_initialized = True

    def _get_conn(self):
        try:
            conn = self._pool.get_nowait()
            if self._ping(conn):
                return conn
        except queue.Empty:
            pass
        return self._create_conn()

    def _create_conn(self):
        conn = pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            cursorclass=DictCursor,
            charset="utf8mb4",
            connect_timeout=30,
            autocommit=True,
        )
        self._set_tcp_keepalive(conn)
        return conn

    def _set_tcp_keepalive(self, conn):
        try:
            sock = conn._sock
            if sock is None:
                return
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        except Exception:
            pass

    def _ping(self, conn):
        try:
            conn.ping(reconnect=False)
            return True
        except Exception:
            return False

    def _recycle_all(self):
        from trendqa.tunnel import tunnel_manager
        tunnel_manager.ensure_alive()
        while True:
            try:
                conn = self._pool.get_nowait()
                try:
                    conn.close()
                except Exception:
                    pass
            except queue.Empty:
                break
        with self._pool_lock:
            self._pool_size = 0

    def _return_conn(self, conn):
        if conn is None:
            return
        try:
            if self._ping(conn):
                try:
                    self._pool.put_nowait(conn)
                    return
                except queue.Full:
                    pass
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    def _execute(self, conn, sql, params=None):
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur

    @with_conn_retry
    def _init_tables(self):
        conn = self._get_conn()
        try:
            self._execute(conn, """
                CREATE TABLE IF NOT EXISTS sources (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) UNIQUE,
                    source_type VARCHAR(100),
                    base_url TEXT,
                    active INT DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self._execute(conn, """
                CREATE TABLE IF NOT EXISTS items (
                    id VARCHAR(255),
                    source_id INT,
                    title TEXT,
                    content TEXT,
                    url TEXT,
                    author TEXT,
                    created_utc DOUBLE,
                    created_at TEXT,
                    raw_json TEXT,
                    item_type TEXT,
                    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processed_at DATETIME,
                    topic TEXT,
                    pais TEXT,
                    PRIMARY KEY (id(255), source_id)
                )
            """)
            self._execute(conn, """
                CREATE TABLE IF NOT EXISTS questions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    item_id TEXT,
                    question TEXT,
                    category TEXT,
                    confidence DOUBLE,
                    model_used TEXT,
                    analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    topic TEXT
                )
            """)
            self._execute(conn, """
                CREATE TABLE IF NOT EXISTS reports (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    topic TEXT,
                    period_label TEXT,
                    summary_json TEXT,
                    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self._execute(conn, """
                CREATE TABLE IF NOT EXISTS trend_terms (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    keyword TEXT,
                    related_top TEXT,
                    related_rising TEXT,
                    autocomplete TEXT,
                    interest_over_time TEXT,
                    geo TEXT,
                    captured_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self._execute(conn, """
                CREATE TABLE IF NOT EXISTS contacts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nombre_completo VARCHAR(255),
                    email_corporativo VARCHAR(255),
                    telefono VARCHAR(50),
                    industria VARCHAR(255),
                    mensaje TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self._execute(conn, """
                CREATE TABLE IF NOT EXISTS processing_log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    step TEXT,
                    status TEXT,
                    message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def ensure_source(self, name, source_type, base_url=None):
        conn = self._get_conn()
        try:
            cur = self._execute(conn, "SELECT id FROM sources WHERE name = %s", (name,))
            row = cur.fetchone()
            if row:
                return row["id"]
            cur = self._execute(conn,
                "INSERT IGNORE INTO sources (name, source_type, base_url) VALUES (%s, %s, %s)",
                (name, source_type, base_url),
            )
            if cur.lastrowid:
                conn.commit()
                return cur.lastrowid
            cur = self._execute(conn, "SELECT id FROM sources WHERE name = %s", (name,))
            row = cur.fetchone()
            return row["id"] if row else None
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def save_item(self, item):
        conn = self._get_conn()
        try:
            self._execute(conn, """
                REPLACE INTO items
                    (id, source_id, title, content, url, author, created_utc,
                     created_at, raw_json, item_type, topic, pais)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                item.get("id"), item.get("source_id"), item.get("title"),
                item.get("content"), item.get("url"), item.get("author"),
                item.get("created_utc"), item.get("created_at"),
                item.get("raw_json"), item.get("item_type", "post"),
                item.get("topic", ""), item.get("pais", "paraguay"),
            ))
            conn.commit()
            return item.get("id")
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def mark_item_processed(self, item_id):
        conn = self._get_conn()
        try:
            self._execute(conn,
                "UPDATE items SET processed_at = CURRENT_TIMESTAMP WHERE id = %s",
                (item_id,),
            )
            conn.commit()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def save_question(self, item_id, question, category, confidence=None, model_used=None, topic=""):
        conn = self._get_conn()
        try:
            self._execute(conn, """
                INSERT INTO questions (item_id, question, category, confidence, model_used, topic)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (item_id, question, category, confidence, model_used, topic))
            conn.commit()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def save_trend_term(self, keyword, related_top=None, related_rising=None, autocomplete=None, interest_over_time=None, geo="PY"):
        conn = self._get_conn()
        try:
            self._execute(conn, """
                INSERT INTO trend_terms (keyword, related_top, related_rising, autocomplete, interest_over_time, geo)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (keyword, related_top, related_rising, autocomplete, interest_over_time, geo))
            conn.commit()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def save_report(self, topic, period_label, summary_json):
        conn = self._get_conn()
        try:
            self._execute(conn, """
                INSERT INTO reports (topic, period_label, summary_json)
                VALUES (%s, %s, %s)
            """, (topic, period_label, summary_json))
            conn.commit()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def log_step(self, step, status, message=None):
        conn = self._get_conn()
        try:
            self._execute(conn,
                "INSERT INTO processing_log (step, status, message) VALUES (%s, %s, %s)",
                (step, status, message),
            )
            conn.commit()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def get_unprocessed_items(self):
        conn = self._get_conn()
        try:
            cur = self._execute(conn,
                "SELECT * FROM items WHERE processed_at IS NULL ORDER BY scraped_at DESC"
            )
            return cur.fetchall()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def get_all_questions_with_items(self):
        conn = self._get_conn()
        try:
            cur = self._execute(conn, """
                SELECT q.*, i.title, i.content, i.url, i.author, s.source_type, s.name as source_name
                FROM questions q
                LEFT JOIN items i ON q.item_id = i.id
                LEFT JOIN sources s ON i.source_id = s.id
                ORDER BY q.analyzed_at DESC
            """)
            return cur.fetchall()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def get_items_by_topic(self, topic, pais=None, limit=50):
        conn = self._get_conn()
        try:
            if pais:
                cur = self._execute(conn, """
                    SELECT i.*, s.name as source_name, s.source_type
                    FROM items i
                    LEFT JOIN sources s ON i.source_id = s.id
                    WHERE i.topic = %s AND i.pais = %s
                    ORDER BY i.scraped_at DESC
                    LIMIT %s
                """, (topic, pais, limit))
            else:
                cur = self._execute(conn, """
                    SELECT i.*, s.name as source_name, s.source_type
                    FROM items i
                    LEFT JOIN sources s ON i.source_id = s.id
                    WHERE i.topic = %s
                    ORDER BY i.scraped_at DESC
                    LIMIT %s
                """, (topic, limit))
            return cur.fetchall()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def get_questions_by_topic(self, topic, limit=100):
        conn = self._get_conn()
        try:
            cur = self._execute(conn, """
                SELECT q.*, i.title, i.content, i.url, s.name as source_name, s.source_type
                FROM questions q
                LEFT JOIN items i ON q.item_id = i.id
                LEFT JOIN sources s ON i.source_id = s.id
                WHERE q.topic = %s
                ORDER BY q.confidence DESC
                LIMIT %s
            """, (topic, limit))
            return cur.fetchall()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def get_latest_report(self, topic=None):
        conn = self._get_conn()
        try:
            if topic:
                cur = self._execute(conn,
                    "SELECT summary_json, generated_at FROM reports WHERE topic = %s ORDER BY generated_at DESC LIMIT 1",
                    (topic,),
                )
            else:
                cur = self._execute(conn,
                    "SELECT summary_json, generated_at FROM reports ORDER BY generated_at DESC LIMIT 1"
                )
            row = cur.fetchone()
            if row:
                return (row["summary_json"], row["generated_at"])
            return None
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def get_question_trends(self, topic="", recent_days=30):
        recent = {}
        older = {}
        cutoff = (datetime.now() - timedelta(days=recent_days)).isoformat()
        conn = self._get_conn()
        try:
            cur = self._execute(conn,
                "SELECT question, COUNT(*) as cnt FROM questions WHERE topic = %s AND analyzed_at >= %s GROUP BY question",
                (topic, cutoff),
            )
            for row in cur.fetchall():
                recent[row["question"]] = row["cnt"]
            cur = self._execute(conn,
                "SELECT question, COUNT(*) as cnt FROM questions WHERE topic = %s AND analyzed_at < %s GROUP BY question",
                (topic, cutoff),
            )
            for row in cur.fetchall():
                older[row["question"]] = row["cnt"]
        finally:
            self._return_conn(conn)
        return recent, older

    @with_conn_retry
    def get_trend_terms(self, limit=50):
        conn = self._get_conn()
        try:
            cur = self._execute(conn,
                "SELECT * FROM trend_terms ORDER BY captured_at DESC LIMIT %s",
                (limit,),
            )
            return cur.fetchall()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def get_category_counts(self, topic):
        conn = self._get_conn()
        try:
            cur = self._execute(conn,
                "SELECT category, COUNT(*) as cnt FROM questions WHERE topic = %s GROUP BY category",
                (topic,),
            )
            return {row["category"]: row["cnt"] for row in cur.fetchall()}
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def save_contact(self, nombre_completo, email_corporativo, telefono=None, industria=None, mensaje=None):
        conn = self._get_conn()
        try:
            self._execute(conn, """
                INSERT INTO contacts (nombre_completo, email_corporativo, telefono, industria, mensaje)
                VALUES (%s, %s, %s, %s, %s)
            """, (nombre_completo, email_corporativo, telefono, industria, mensaje))
            conn.commit()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def get_contacts(self, limit=50):
        conn = self._get_conn()
        try:
            cur = self._execute(conn,
                "SELECT * FROM contacts ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
            return cur.fetchall()
        finally:
            self._return_conn(conn)

    @with_conn_retry
    def prune_old_data(self, days=90):
        conn = self._get_conn()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            self._execute(conn, "DELETE FROM items WHERE scraped_at < %s", (cutoff,))
            self._execute(conn, "DELETE FROM questions WHERE analyzed_at < %s", (cutoff,))
            self._execute(conn, "DELETE FROM reports WHERE generated_at < %s", (cutoff,))
            self._execute(conn, "DELETE FROM trend_terms WHERE captured_at < %s", (cutoff,))
            self._execute(conn, "DELETE FROM processing_log WHERE created_at < %s", (cutoff,))
            conn.commit()
        finally:
            self._return_conn(conn)
