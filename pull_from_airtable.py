"""
Pulls coded turn data from Airtable and loads it into the local SQLite
database as a new table: coded_turns.
"""

import sqlite3
import json
import os
import sys
import time
import requests

DB_PATH = "interviews.db"
TABLE_NAME = "Turns"


def get_env():
    pat = os.environ.get("AIRTABLE_PAT")
    base_id = os.environ.get("AIRTABLE_BASE_ID")

    if not pat or not base_id:
        try:
            with open(".env") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("AIRTABLE_PAT="):
                        pat = line.split("=", 1)[1].strip()
                    elif line.startswith("AIRTABLE_BASE_ID="):
                        base_id = line.split("=", 1)[1].strip()
        except FileNotFoundError:
            pass

    if not pat or not base_id:
        print("ERROR: AIRTABLE_PAT and AIRTABLE_BASE_ID must be set in .env")
        sys.exit(1)

    return pat, base_id


def fetch_all_records(pat, base_id):
    url = f"https://api.airtable.com/v0/{base_id}/{TABLE_NAME}"
    headers = {"Authorization": f"Bearer {pat}"}
    records = []
    params = {"pageSize": 100}

    while True:
        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        records.extend(data["records"])
        print(f"  Fetched {len(records)} records...", end="\r")

        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset
        time.sleep(0.25)

    print(f"\n  Done. {len(records)} records fetched.")
    return records


def load_to_sqlite(records):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DROP TABLE IF EXISTS coded_turns")
    conn.execute("""
        CREATE TABLE coded_turns (
            airtable_id     TEXT PRIMARY KEY,
            transcript_id   TEXT,
            split           TEXT,
            turn_number     INTEGER,
            speaker         TEXT,
            text            TEXT,
            word_count      INTEGER,
            char_count      INTEGER,
            turn_type       TEXT,
            biasing_response INTEGER,
            missed_opportunity INTEGER,
            notes           TEXT,
            coded_by        TEXT DEFAULT 'human'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ct_transcript ON coded_turns(transcript_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ct_split ON coded_turns(split)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ct_turn_type ON coded_turns(turn_type)")

    rows = []
    skipped = 0
    for rec in records:
        f = rec.get("fields", {})
        if not f.get("transcript_id"):
            skipped += 1
            continue
        rows.append((
            rec["id"],
            f.get("transcript_id", ""),
            f.get("split", ""),
            f.get("turn_number", 0),
            f.get("speaker", ""),
            f.get("text", ""),
            f.get("word_count", 0),
            f.get("char_count", 0),
            f.get("turn_type", ""),
            1 if f.get("biasing_response") else 0,
            1 if f.get("missed_opportunity") else 0,
            f.get("notes", ""),
            "human",
        ))

    conn.executemany("INSERT INTO coded_turns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()

    if skipped:
        print(f"  Skipped {skipped} records with missing transcript_id")

    return conn, len(rows)


def print_summary(conn):
    print("\n" + "="*50)
    print("CODING SUMMARY")
    print("="*50)

    total = conn.execute("SELECT COUNT(*) FROM coded_turns").fetchone()[0]
    print(f"\nTotal coded turns: {total}")

    print("\nTurn type breakdown:")
    rows = conn.execute("""
        SELECT turn_type, COUNT(*) as n,
               ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM coded_turns), 1) as pct
        FROM coded_turns
        GROUP BY turn_type
        ORDER BY n DESC
    """).fetchall()
    for row in rows:
        label = row[0] if row[0] else "(uncoded)"
        print(f"  {label:<22} {row[1]:>4}  ({row[2]}%)")

    print("\nAI turns only:")
    ai_total = conn.execute("SELECT COUNT(*) FROM coded_turns WHERE speaker='AI'").fetchone()[0]
    biasing = conn.execute("SELECT COUNT(*) FROM coded_turns WHERE speaker='AI' AND biasing_response=1").fetchone()[0]
    missed = conn.execute("SELECT COUNT(*) FROM coded_turns WHERE speaker='AI' AND missed_opportunity=1").fetchone()[0]
    print(f"  Total AI turns:          {ai_total}")
    print(f"  Biasing response:        {biasing} ({round(100*biasing/ai_total, 1)}%)")
    print(f"  Missed opportunity:      {missed} ({round(100*missed/ai_total, 1)}%)")

    print("\nBy split:")
    rows = conn.execute("""
        SELECT split,
               COUNT(*) as total,
               SUM(CASE WHEN speaker='AI' AND biasing_response=1 THEN 1 ELSE 0 END) as biasing,
               SUM(CASE WHEN speaker='AI' AND missed_opportunity=1 THEN 1 ELSE 0 END) as missed,
               SUM(CASE WHEN speaker='AI' THEN 1 ELSE 0 END) as ai_turns
        FROM coded_turns
        GROUP BY split
    """).fetchall()
    print(f"  {'Split':<14} {'Turns':>6} {'AI turns':>9} {'Biasing':>8} {'Missed':>7}")
    print(f"  {'-'*48}")
    for row in rows:
        split, total, biasing, missed, ai = row
        print(f"  {split:<14} {total:>6} {ai:>9} {biasing:>8} {missed:>7}")

    print("\nUncoded turns (review needed):")
    uncoded = conn.execute(
        "SELECT COUNT(*) FROM coded_turns WHERE (turn_type IS NULL OR turn_type = '') AND speaker='AI'"
    ).fetchone()[0]
    print(f"  {uncoded} AI turns still uncoded")

    conn.close()


def main():
    pat, base_id = get_env()

    print("Fetching records from Airtable...")
    records = fetch_all_records(pat, base_id)

    print("Loading into SQLite...")
    conn, loaded = load_to_sqlite(records)
    print(f"  {loaded} turns loaded into coded_turns table")

    print_summary(conn)
    print(f"\nData saved to {DB_PATH} → table: coded_turns")
    print("Launch Datasette to explore: ./start.sh")


if __name__ == "__main__":
    main()
