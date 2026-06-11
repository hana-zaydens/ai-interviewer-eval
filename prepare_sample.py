"""
Selects a stratified random sample of transcripts, parses them into
individual turns, pre-labels auto-detectable fields, and outputs
sample_turns.csv and sample_turns.json for manual coding.

Usage:
    python prepare_sample.py

Sample size and strategy are configured in schema.json under the "sample" key.
Auto-labeling rules (opening, closing patterns) are also read from schema.json.
"""

import csv
import json
import random
import re
import sqlite3
from collections import Counter

DB_PATH = "interviews.db"
SCHEMA_PATH = "schema.json"
OUTPUT_JSON = "sample_turns.json"
OUTPUT_CSV = "sample_turns.csv"


def load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def detect_bias(text, patterns):
    for pattern in patterns:
        if re.match(pattern, text.strip()):
            return True
    return False


def parse_turns(text, transcript_id, split, schema):
    biasing_patterns = schema.get("biasing_response_patterns", [])
    auto_rules = schema.get("auto_label_rules", {})
    opening_patterns = [r["match_pattern"] for r in auto_rules.get("opening", []) if "match_pattern" in r]
    closing_patterns = [r["match_pattern"] for r in auto_rules.get("closing", []) if "match_pattern" in r]

    parts = re.split(r"(?m)^(AI|User)\s*:\s*", text)
    turns = []
    turn_number = 0
    i = 1
    while i < len(parts) - 1:
        speaker = parts[i].strip()
        content = parts[i + 1].strip()
        i += 2
        if not content:
            continue
        turn_number += 1
        turns.append({
            "transcript_id": transcript_id,
            "split": split,
            "turn_number": turn_number,
            "speaker": speaker,
            "text": content,
            "word_count": len(content.split()),
            "char_count": len(content),
            "biasing_response": False,
            "missed_opportunity": False,
            "turn_type": "response" if speaker == "User" else "",
            "notes": "",
        })

    ai_turns = [t for t in turns if t["speaker"] == "AI"]
    if not ai_turns:
        return turns

    # Position-based: first and last AI turns
    ai_turns[0]["turn_type"] = "opening"
    ai_turns[-1]["turn_type"] = "closing"

    # Pattern-based opening rules from schema.json
    for turn in ai_turns:
        if turn["turn_type"]:
            continue
        for pattern in opening_patterns:
            if re.search(pattern, turn["text"], re.IGNORECASE):
                turn["turn_type"] = "opening"
                break

    # Pattern-based closing rules from schema.json (reversed to catch second closing turn)
    for turn in reversed(ai_turns):
        if turn["turn_type"] == "closing":
            continue
        for pattern in closing_patterns:
            if re.search(pattern, turn["text"], re.IGNORECASE):
                turn["turn_type"] = "closing"
                break

    # Biasing response detection on all AI turns except opening
    for turn in ai_turns:
        if turn["turn_type"] == "opening":
            continue
        turn["biasing_response"] = detect_bias(turn["text"], biasing_patterns)

    return turns


def select_sample(schema):
    conn = sqlite3.connect(DB_PATH)
    cfg = schema["sample"]
    seed = cfg.get("seed", 42)
    lower_ratio = cfg.get("lower_half_ratio", 0.5)
    rng = random.Random(seed)
    splits_cfg = cfg.get("splits")

    selected = []

    if splits_cfg:
        # Sample a fixed number of transcripts per named split/group
        for split_name, n in splits_cfg.items():
            rows = conn.execute(
                "SELECT transcript_id FROM transcripts WHERE split=? ORDER BY word_count",
                (split_name,),
            ).fetchall()
            ids = [r[0] for r in rows]
            if not ids:
                print(f"  Warning: no transcripts found for split '{split_name}', skipping")
                continue
            if len(ids) < n:
                print(f"  Warning: only {len(ids)} transcripts in split '{split_name}', requested {n}")
                n = len(ids)
            mid = len(ids) // 2
            n_lower = round(n * lower_ratio)
            n_upper = n - n_lower
            sampled = rng.sample(ids[:mid], min(n_lower, mid)) + rng.sample(ids[mid:], min(n_upper, len(ids) - mid))
            for tid in sampled:
                selected.append((tid, split_name))
    else:
        # Sample n transcripts from the full dataset
        n = cfg.get("n", 40)
        rows = conn.execute(
            "SELECT transcript_id, split FROM transcripts ORDER BY word_count"
        ).fetchall()
        if not rows:
            print("  Error: no transcripts found in database. Run load.py first.")
            conn.close()
            return []
        if len(rows) < n:
            print(f"  Warning: only {len(rows)} transcripts available, requested {n}")
            n = len(rows)
        mid = len(rows) // 2
        n_lower = round(n * lower_ratio)
        n_upper = n - n_lower
        sampled = rng.sample(rows[:mid], min(n_lower, mid)) + rng.sample(rows[mid:], min(n_upper, len(rows) - mid))
        for tid, split in sampled:
            selected.append((tid, split or ""))

    conn.close()
    return selected


def main():
    schema = load_schema()

    selected = select_sample(schema)
    if not selected:
        return

    print(f"Selected {len(selected)} transcripts:")
    for split, count in sorted(Counter(s for _, s in selected).items()):
        print(f"  {split or '(no split)'}: {count}")

    conn = sqlite3.connect(DB_PATH)
    all_turns = []
    for tid, split in selected:
        row = conn.execute("SELECT text FROM transcripts WHERE transcript_id=?", (tid,)).fetchone()
        if not row:
            print(f"  Warning: transcript {tid} not found, skipping")
            continue
        all_turns.extend(parse_turns(row[0], tid, split, schema))
    conn.close()

    with open(OUTPUT_JSON, "w") as f:
        json.dump(all_turns, f, indent=2)

    if all_turns:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_turns[0].keys()))
            writer.writeheader()
            writer.writerows(all_turns)

    ai_turns = [t for t in all_turns if t["speaker"] == "AI"]
    auto_labeled = [t for t in all_turns if t["turn_type"]]
    needs_coding = [t for t in all_turns if not t["turn_type"]]
    praise_turns = [t for t in ai_turns if t["biasing_response"]]

    print(f"\nTurn summary:")
    print(f"  Total turns:               {len(all_turns)}")
    print(f"  AI turns:                  {len(ai_turns)}")
    print(f"  User turns:                {len(all_turns) - len(ai_turns)}")
    print(f"  Auto-labeled:              {len(auto_labeled)}")
    print(f"  Needs manual coding:       {len(needs_coding)}")
    print(f"  AI turns with bias flag:   {len(praise_turns)} ({100 * len(praise_turns) // max(len(ai_turns), 1)}%)")
    print(f"\nSaved to {OUTPUT_CSV} and {OUTPUT_JSON}")
    print(f"\nNext step: open {OUTPUT_CSV} in a spreadsheet to manually code the turns,")
    print(f"then run: python load_coded.py --from-csv {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
