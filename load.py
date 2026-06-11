"""
Loads interview transcripts into interviews.db for analysis.

Supported formats:
    CSV  — one row per transcript
    JSON — array of objects
    TXT  — directory of .txt files, one transcript per file

Usage:
    python load.py transcripts.csv
    python load.py transcripts.json
    python load.py transcripts/

    python load.py data.csv --id-col interview_id --text-col transcript --split-col group
    python load.py data.csv --ai-label Interviewer --user-label Participant

Run python load.py --help for all options.

Speaker labels: whatever labels appear in your transcript text (e.g. "Interviewer",
"Bot", "AI") are normalized to "AI:" and "User:" on load so the rest of the toolkit
works without any extra configuration.
"""

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

DB_PATH = "interviews.db"


def normalize_labels(text, ai_label, user_label):
    if ai_label != "AI":
        text = re.sub(rf"(?m)^{re.escape(ai_label)}\s*:", "AI:", text)
    if user_label != "User":
        text = re.sub(rf"(?m)^{re.escape(user_label)}\s*:", "User:", text)
    return text


def transcript_stats(text):
    ai_turns = len(re.findall(r"(?m)^AI\s*:", text))
    user_turns = len(re.findall(r"(?m)^User\s*:", text))
    return len(text.split()), ai_turns + user_turns, ai_turns, user_turns, len(text)


def make_row(transcript_id, split, text):
    word_count, total_turns, ai_turns, participant_turns, char_count = transcript_stats(text)
    return (transcript_id, split, text, word_count, total_turns, ai_turns, participant_turns, char_count)


def load_csv(path, id_col, text_col, split_col, ai_label, user_label):
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, record in enumerate(reader):
            tid = record.get(id_col, "").strip() or f"transcript_{i+1:04d}"
            text = record.get(text_col, "").strip()
            split = record.get(split_col, "").strip() if split_col in (record or {}) else ""
            if not text:
                print(f"  Warning: row {i+1} has no text in column '{text_col}', skipping")
                continue
            rows.append(make_row(tid, split, normalize_labels(text, ai_label, user_label)))
    return rows


def load_json(path, id_col, text_col, split_col, ai_label, user_label):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print("ERROR: JSON file must be an array of objects")
        sys.exit(1)
    rows = []
    for i, record in enumerate(data):
        tid = str(record.get(id_col, "")).strip() or f"transcript_{i+1:04d}"
        text = str(record.get(text_col, "")).strip()
        split = str(record.get(split_col, "")).strip() if split_col in record else ""
        if not text:
            print(f"  Warning: item {i+1} has no text in field '{text_col}', skipping")
            continue
        rows.append(make_row(tid, split, normalize_labels(text, ai_label, user_label)))
    return rows


def load_txt_dir(path, ai_label, user_label):
    txt_files = sorted(Path(path).glob("*.txt"))
    if not txt_files:
        print(f"ERROR: No .txt files found in {path}")
        sys.exit(1)
    rows = []
    for filepath in txt_files:
        text = filepath.read_text(encoding="utf-8").strip()
        if not text:
            print(f"  Warning: {filepath.name} is empty, skipping")
            continue
        rows.append(make_row(filepath.stem, "", normalize_labels(text, ai_label, user_label)))
    return rows


def setup_db(conn, force):
    if force:
        conn.execute("DROP TABLE IF EXISTS transcripts")
        conn.execute("DROP TABLE IF EXISTS transcripts_fts")
        print("Dropped existing transcripts table.")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            transcript_id     TEXT PRIMARY KEY,
            split             TEXT,
            text              TEXT,
            word_count        INTEGER,
            total_turns       INTEGER,
            ai_turns          INTEGER,
            participant_turns INTEGER,
            char_count        INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_split ON transcripts(split)")
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts
        USING fts5(transcript_id, text, content=transcripts, content_rowid=rowid)
    """)


def main():
    parser = argparse.ArgumentParser(
        description="Load interview transcripts into interviews.db",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python load.py transcripts.csv
  python load.py transcripts.json
  python load.py transcripts/
  python load.py data.csv --id-col interview_id --text-col transcript --split-col group
  python load.py data.csv --ai-label Interviewer --user-label Participant
        """
    )
    parser.add_argument("source", help="CSV file, JSON file, or directory of .txt files")
    parser.add_argument("--id-col",    default="transcript_id", metavar="COL",
                        help="Column/field name for transcript ID (default: transcript_id)")
    parser.add_argument("--text-col",  default="text",          metavar="COL",
                        help="Column/field name for transcript text (default: text)")
    parser.add_argument("--split-col", default="split",         metavar="COL",
                        help="Column/field name for split/group label (default: split; omitted if column absent)")
    parser.add_argument("--ai-label",   default="AI",   metavar="LABEL",
                        help="Speaker label for the AI/interviewer in the text (default: AI)")
    parser.add_argument("--user-label", default="User", metavar="LABEL",
                        help="Speaker label for the participant in the text (default: User)")
    parser.add_argument("--db",    default=DB_PATH, metavar="PATH",
                        help=f"Path to SQLite database (default: {DB_PATH})")
    parser.add_argument("--force", action="store_true",
                        help="Drop and recreate the transcripts table from scratch")
    args = parser.parse_args()

    source = args.source
    if os.path.isdir(source):
        print(f"Loading .txt files from {source}/...")
        rows = load_txt_dir(source, args.ai_label, args.user_label)
    elif source.lower().endswith(".csv"):
        print(f"Loading {source}...")
        rows = load_csv(source, args.id_col, args.text_col, args.split_col, args.ai_label, args.user_label)
    elif source.lower().endswith(".json"):
        print(f"Loading {source}...")
        rows = load_json(source, args.id_col, args.text_col, args.split_col, args.ai_label, args.user_label)
    else:
        print("ERROR: source must be a .csv file, .json file, or a directory of .txt files")
        sys.exit(1)

    if not rows:
        print("No transcripts loaded. Check your input file and column/field names.")
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    setup_db(conn, args.force)

    existing = {r[0] for r in conn.execute("SELECT transcript_id FROM transcripts").fetchall()}
    new_rows = [r for r in rows if r[0] not in existing]
    skipped = len(rows) - len(new_rows)

    if new_rows:
        conn.executemany("INSERT OR REPLACE INTO transcripts VALUES (?,?,?,?,?,?,?,?)", new_rows)
        conn.execute("INSERT INTO transcripts_fts(transcripts_fts) VALUES('rebuild')")
        conn.commit()

    conn.close()

    print(f"\nLoaded {len(new_rows)} new transcripts into {args.db}")
    if skipped:
        print(f"Skipped {skipped} already-present (use --force to overwrite)")

    splits = {}
    for r in rows:
        key = r[1] or "(no split)"
        splits[key] = splits.get(key, 0) + 1
    if not (len(splits) == 1 and "(no split)" in splits):
        for split, count in sorted(splits.items()):
            print(f"  {split}: {count}")

    total_turns = sum(r[4] for r in rows)
    print(f"  {total_turns} total turns across {len(rows)} transcripts")
    print(f"\nNext step: python llm_classifier.py --preview")


if __name__ == "__main__":
    main()
