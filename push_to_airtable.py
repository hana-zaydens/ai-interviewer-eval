"""
Pushes the prepared sample turns to an Airtable base for manual coding.

Setup:
  1. Create a Personal Access Token at https://airtable.com/create/tokens
     Scopes needed: data.records:write, schema.bases:write
  2. Create a new base in Airtable (any name, e.g. "Interviewer Analysis")
  3. Copy the base ID from the URL: airtable.com/{BASE_ID}/...
  4. Set environment variables (or create a .env file — see .env.example):
       AIRTABLE_PAT=your_token_here
       AIRTABLE_BASE_ID=appXXXXXXXXXXXXXX

Run:
  python3 push_to_airtable.py
"""

import json
import os
import sys
import time
import requests

INPUT_JSON = "sample_turns.json"
TABLE_NAME = "Turns"

FIELD_DEFS = [
    {"name": "transcript_id",   "type": "singleLineText"},
    {"name": "split",           "type": "singleLineText"},
    {"name": "turn_number",     "type": "number",       "options": {"precision": 0}},
    {"name": "speaker",         "type": "singleSelect", "options": {"choices": [
        {"name": "AI"}, {"name": "User"}
    ]}},
    {"name": "text",            "type": "multilineText"},
    {"name": "word_count",      "type": "number",       "options": {"precision": 0}},
    {"name": "char_count",      "type": "number",       "options": {"precision": 0}},
    {"name": "biasing_response",    "type": "checkbox", "options": {"icon": "check", "color": "yellowBright"}},
    {"name": "missed_opportunity", "type": "checkbox", "options": {"icon": "check", "color": "blueBright"}},
    {"name": "turn_type",          "type": "singleSelect", "options": {"choices": [
        {"name": "opening"},
        {"name": "new_question"},
        {"name": "follow_up"},
        {"name": "closing"},
        {"name": "response"},
        {"name": "ambiguous"},
        {"name": "other"},
    ]}},
    {"name": "notes",           "type": "multilineText"},
]


def get_env():
    pat = os.environ.get("AIRTABLE_PAT")
    base_id = os.environ.get("AIRTABLE_BASE_ID")

    # Try loading from .env file if env vars not set
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
        print("ERROR: AIRTABLE_PAT and AIRTABLE_BASE_ID must be set.")
        print("Create a .env file (see .env.example) or set them as environment variables.")
        sys.exit(1)

    return pat, base_id


def create_table(pat, base_id):
    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    headers = {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}
    payload = {"name": TABLE_NAME, "fields": FIELD_DEFS}
    r = requests.post(url, headers=headers, json=payload)

    if r.status_code == 422 and "already exists" in r.text.lower():
        print(f"  Table '{TABLE_NAME}' already exists — will append records.")
        return None
    r.raise_for_status()
    print(f"  Created table '{TABLE_NAME}'")
    return r.json()["id"]


def push_records(pat, base_id, turns):
    url = f"https://api.airtable.com/v0/{base_id}/{TABLE_NAME}"
    headers = {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}

    # Airtable allows max 10 records per request
    batch_size = 10
    total = len(turns)
    pushed = 0

    for i in range(0, total, batch_size):
        batch = turns[i: i + batch_size]
        records = []
        for t in batch:
            fields = {
                "transcript_id":   t["transcript_id"],
                "split":           t["split"],
                "turn_number":     t["turn_number"],
                "speaker":         t["speaker"],
                "text":            t["text"][:99000],  # stay under Airtable's 100k char limit
                "word_count":      t["word_count"],
                "char_count":      t["char_count"],
                "biasing_response":    bool(t["biasing_response"]),
                "missed_opportunity": bool(t.get("missed_opportunity", False)),
                "notes":              t["notes"],
            }
            if t["turn_type"]:
                fields["turn_type"] = t["turn_type"]
            records.append({"fields": fields})

        r = requests.post(url, headers=headers, json={"records": records})
        r.raise_for_status()
        pushed += len(batch)
        print(f"  Pushed {pushed}/{total} turns...", end="\r")

        # Airtable rate limit: 5 requests/second
        time.sleep(0.25)

    print(f"\n  Done. {pushed} turns pushed to '{TABLE_NAME}'.")


def main():
    pat, base_id = get_env()

    with open(INPUT_JSON) as f:
        turns = json.load(f)
    print(f"Loaded {len(turns)} turns from {INPUT_JSON}")

    print("Creating table in Airtable...")
    create_table(pat, base_id)

    print("Pushing records...")
    push_records(pat, base_id, turns)

    print(f"\nOpen your base at: https://airtable.com/{base_id}")


if __name__ == "__main__":
    main()
