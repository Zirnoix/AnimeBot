# modules/database.py

import sqlite3
import os

DB_PATH = "data/bot_data.db"


def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS linked_accounts (
            user_id TEXT PRIMARY KEY,
            anilist_username TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS challenges (
            user_id TEXT,
            challenge_name TEXT,
            completed INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, challenge_name)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            user_id TEXT PRIMARY KEY,
            notify_enabled INTEGER DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()


def get_connection():
    return sqlite3.connect(DB_PATH)


def link_account(user_id: str, anilist_username: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("REPLACE INTO linked_accounts (user_id, anilist_username) VALUES (?, ?)", (user_id, anilist_username))
    conn.commit()
    conn.close()


def unlink_account(user_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM linked_accounts WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_linked_username(user_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT anilist_username FROM linked_accounts WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None
