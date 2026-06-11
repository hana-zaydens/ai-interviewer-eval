"""
Loads manually coded turns from a CSV file into the coded_turns table
in interviews.db.

The expected input is a CSV produced by prepare_sample.py and manually
coded in a spreadsheet. The turn_type, biasing_response, missed_opportunity,
and notes columns should be filled in by the coder.

Usage:
    python load_coded.py --from-csv sample_turns.csv
    python load_coded.py --from-csv sample_turns.csv --force

Options:
    --from-csv   Path to the coded CSV file (required)
    --db         Path to SQLite database (default: interviews.db)
    --force      Drop and recreate the coded_turns table from scratch
"""

import argparse
import csv
import json
import sqlite3
import sys

DB_PATH = "interviews.db"
SCHEMA_PATH = "schema.json"

VALID_TURN_TYPES = {"opening", "new_question", "follow_up", "closing", "response", "ambiguous", "other"}


def parse_bool(val):
    s = str(val).strip().lower()
    if s in ("true", "yes", "1"):
        return 1
    if s in ("false", "no", "0", ""):
        return 0
    return None


def setup_table(conn, force):
    if force:
        conn.execute("DROP TABLE IF EXISTS coded_turns")
        print("Dropped existing coded_turns table.")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS coded_turns (
            transcript_id      TEXT,
            split              TEXT,
            turn_number        INTEGER,
            speaker            TEXT,
            text               TEXT,
            word_count         INTEGER,
            char_count         INTEGER,
            turn_type          TEXT,
            biasing_response   INTEGER,
            missed_opportunity INTEGER,
            notes              TEXT,
            coded_by           TEXT DEFAULT 'human',
            PRIMARY KEY (transcript_id, turn_number)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ct_transcript ON coded_turns(transcript_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ct_split ON coded_turns(split)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ct_turn_type ON coded_turns(turn_type)")


def main():
    parser = argparse.ArgumentParser(
        description="Load manually coded turns from CSV into interviews.db"
    )
    parser.add_argument("--from-csv", required=True, metavar="FILE",
                        help="Path to the coded CSV file")
    parser.add_argument("--db", default=DB_PATH, metavar="PATH",
                        help=f"Path to SQLite database (default: {DB_PATH})")
    parser.add_argument("--force", action="store_true",
                        help="Drop and recreate the coded_turns table from scratch")
    args = parser.parse_args()

    rows = []
    warnings = []

    with open(args.from_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, record in enumerate(reader, start=1):
            turn_type = record.get("turn_type", "").strip()
            biasing_raw = record.get("biasing_response", "")
            missed_raw = record.get("missed_opportunity", "")

            if not turn_type:
                warnings.append(f"  Row {i} ({record.get('transcript_id', '?')}, turn {record.get('turn_number', '?')}): no turn_type — included but will be skipped in validation")

            if turn_type and turn_type not in VALID_TURN_TYPES:
                warnings.append(f"  Row {i}: unrecognised turn_type '{turn_type}' — included as-is")

            biasing = parse_bool(biasing_raw)
            missed = parse_bool(missed_raw)

            if biasing is None:
                warnings.append(f"  Row {i}: could not parse biasing_response '{biasing_raw}', defaulting to 0")
                biasing = 0
            if missed is None:
                warnings.append(f"  Row {i}: could not parse missed_opportunity '{missed_raw}', defaulting to 0")
                missed = 0

            rows.append((
                record.get("transcript_id", ""),
                record.get("split", ""),
                int(record.get("turn_number", 0) or 0),
                record.get("speaker", ""),
                record.get("text", ""),
                int(record.get("word_count", 0) or 0),
                int(record.get("char_count", 0) or 0),
                turn_type,
                biasing,
                missed,
                record.get("notes", ""),
                "human",
            ))

    if not rows:
        print("No rows found in CSV. Check the file path and format.")
        sys.exit(1)

    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for w in warnings:
            print(w)
        print()

    conn = sqlite3.connect(args.db)
    setup_table(conn, args.force)

    existing = {
        (r[0], r[1])
        for r in conn.execute("SELECT transcript_id, turn_number FROM coded_turns").fetchall()
    }
    new_rows = [r for r in rows if (r[0], r[2]) not in existing]
    skipped = len(rows) - len(new_rows)

    if new_rows:
        conn.executemany("INSERT OR REPLACE INTO coded_turns VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", new_rows)
        conn.commit()

    conn.close()

    coded = sum(1 for r in rows if r[7])
    uncoded = len(rows) - coded

    print(f"Loaded {len(new_rows)} turns into coded_turns ({args.db})")
    if skipped:
        print(f"Skipped {skipped} already-present turns (use --force to overwrite)")
    print(f"  Coded turns:   {coded}")
    if uncoded:
        print(f"  Uncoded turns: {uncoded}  (turn_type empty — will be skipped in validation)")
    print(f"\nNext step: python llm_classifier.py --preview")


if __name__ == "__main__":
    main()
