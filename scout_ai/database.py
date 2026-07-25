import sqlite3
import json
from datetime import datetime, timedelta

DB_NAME = "scout_ai.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Volles Schema für Mastermind Signale
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_key TEXT,
            bet_key TEXT,
            consensus_reached TEXT,
            sources TEXT,
            timestamp DATETIME
        )
    ''')
    conn.commit()
    conn.close()

def process_consensus(match, bet, source_name, full_json):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    match_key = match.lower().strip()
    bet_key = bet.lower().strip()

    # Prüfen, ob bereits gesendet (letzte 36h)
    cursor.execute('''
        SELECT id FROM signals
        WHERE match_key = ? AND bet_key = ?
        AND timestamp > datetime('now', '-36 hours')
    ''', (match_key, bet_key))

    if cursor.fetchone():
        conn.close()
        return 0, False
    else:
        con_val = full_json.get("consensus_reached", "DIRECT")
        cursor.execute('''
            INSERT INTO signals (match_key, bet_key, consensus_reached, sources, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (match_key, bet_key, str(con_val), source_name, datetime.now()))
        conn.commit()
        conn.close()
        return 1, True
