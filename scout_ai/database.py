import sqlite3
from datetime import datetime

DB_NAME = "scout_ai.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match TEXT,
            expert_source TEXT,
            predicted_pick TEXT,
            timestamp DATETIME
        )
    ''')
    conn.commit()
    conn.close()

def is_duplicate(match, expert_source, predicted_pick):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM picks
        WHERE match = ? AND expert_source = ? AND predicted_pick = ?
    ''', (match, expert_source, predicted_pick))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def save_pick(match, expert_source, predicted_pick):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO picks (match, expert_source, predicted_pick, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (match, expert_source, predicted_pick, datetime.now()))
    conn.commit()
    conn.close()
