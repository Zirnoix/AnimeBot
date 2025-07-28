import sqlite3
import os

DB_PATH = "data/user_links.db"

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS links (
            discord_id TEXT PRIMARY KEY,
            anilist_id INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def save_link(discord_id, anilist_id):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("REPLACE INTO links (discord_id, anilist_id) VALUES (?, ?)", (str(discord_id), anilist_id))
    conn.commit()
    conn.close()

def get_link(discord_id):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT anilist_id FROM links WHERE discord_id = ?", (str(discord_id),))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def remove_link(discord_id):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM links WHERE discord_id = ?", (str(discord_id),))
    conn.commit()
    conn.close()
