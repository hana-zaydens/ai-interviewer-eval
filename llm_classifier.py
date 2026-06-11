"""
LLM classifier for turn-level coding of interview transcripts.

Usage:
    python llm_classifier.py --preview              Mini run on a sample; shows agreement stats if coded data exists
    python llm_classifier.py --preview --sample-size 10
    python llm_classifier.py --run                  Classify all transcripts
    python llm_classifier.py --run --force          Drop llm_coded_turns and re-classify everything from scratch

Requires:
    pip install anthropic
    ANTHROPIC_API_KEY in environment or .env file
"""

import argparse
import json
import os
import random
import re
import sqlite3
import sys
import time
from collections import Counter

import anthropic

DB_PATH = "interviews.db"
SCHEMA_PATH = "schema.json"
CODEBOOK_PATH = "CODEBOOK.md"
DEFAULT_MODEL = "claude-sonnet-4-6"
LLM_TABLE = "llm_coded_turns"
SLEEP_BETWEEN = 0.5  # seconds between API calls to avoid rate limits

SYSTEM_PROMPT = None  # loaded from CODEBOOK.md at startup


# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------

def get_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        try:
            with open(".env") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ANTHROPIC_API_KEY="):
                        key = line.split("=", 1)[1].strip()
        except FileNotFoundError:
            pass
    if not key:
        print("ERROR: ANTHROPIC_API_KEY must be set in environment or .env file")
        sys.exit(1)
    return key


# ---------------------------------------------------------------------------
# System prompt — loaded from CODEBOOK.md at startup
# ---------------------------------------------------------------------------

def load_system_prompt():
    try:
        with open(CODEBOOK_PATH, encoding="utf-8") as f:
            codebook = f.read()
    except FileNotFoundError:
        print(f"ERROR: {CODEBOOK_PATH} not found. The codebook is required for classification.")
        sys.exit(1)

    return (
        "You are a qualitative research assistant classifying turns in AI-conducted interview transcripts.\n\n"
        "You will receive a full interview transcript and must classify every turn. "
        "Submit all classifications using the submit_classifications tool — one entry per turn, in order.\n\n"
        "The following codebook defines the coding scheme:\n\n"
        "---\n\n"
        + codebook
    )


TOOL_DEF = {
    "name": "submit_classifications",
    "description": "Submit turn-level classifications for all turns in the transcript",
    "input_schema": {
        "type": "object",
        "properties": {
            "turns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "turn_number": {"type": "integer"},
                        "turn_type": {
                            "type": "string",
                            "enum": [
                                "opening", "new_question", "follow_up", "closing",
                                "response", "ambiguous", "other"
                            ]
                        },
                        "biasing_response": {"type": "boolean"},
                        "missed_opportunity": {"type": "boolean"},
                        "notes": {"type": "string"}
                    },
                    "required": ["turn_number", "turn_type", "biasing_response", "missed_opportunity"]
                }
            }
        },
        "required": ["turns"]
    }
}


# ---------------------------------------------------------------------------
# Turn parsing
# ---------------------------------------------------------------------------

def parse_turns_basic(text):
    """Parse transcript text into turns without any auto-labeling."""
    parts = re.split(r"(?m)^(AI|User|Assistant)\s*:\s*", text)
    turns = []
    turn_number = 0
    i = 1
    while i < len(parts) - 1:
        speaker_raw = parts[i].strip()
        content = parts[i + 1].strip()
        i += 2
        if not content:
            continue
        turn_number += 1
        speaker = "AI" if speaker_raw in ("AI", "Assistant") else "User"
        turns.append({
            "turn_number": turn_number,
            "speaker": speaker,
            "text": content,
        })
    return turns


def format_transcript_for_prompt(turns):
    return "\n\n".join(
        f"Turn {t['turn_number']} ({t['speaker']}): {t['text']}"
        for t in turns
    )


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def classify_transcript(client, transcript_id, text, max_retries=3):
    """Call the LLM to classify all turns in a transcript. Returns list of result dicts."""
    turns = parse_turns_basic(text)
    if not turns:
        return []

    formatted = format_transcript_for_prompt(turns)
    n = len(turns)
    user_message = (
        f"Classify all {n} turns in the following interview transcript. "
        f"Submit your classifications using the submit_classifications tool.\n\n"
        f"---\n{formatted}\n---"
    )

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=DEFAULT_MODEL,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                tools=[TOOL_DEF],
                tool_choice={"type": "tool", "name": "submit_classifications"},
                messages=[{"role": "user", "content": user_message}]
            )
            break
        except anthropic.RateLimitError:
            if attempt < max_retries - 1:
                wait = 30 * (attempt + 1)
                print(f"(rate limit, waiting {wait}s...)", end=" ", flush=True)
                time.sleep(wait)
            else:
                raise
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt < max_retries - 1:
                print(f"(API overloaded, waiting 60s...)", end=" ", flush=True)
                time.sleep(60)
            else:
                raise

    turn_map = {t["turn_number"]: t for t in turns}
    results = []
    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_classifications":
            for ct in block.input.get("turns", []):
                tn = ct["turn_number"]
                orig = turn_map.get(tn, {})
                results.append({
                    "transcript_id": transcript_id,
                    "split": "",
                    "turn_number": tn,
                    "speaker": orig.get("speaker", ""),
                    "text": orig.get("text", ""),
                    "word_count": len(orig.get("text", "").split()),
                    "char_count": len(orig.get("text", "")),
                    "turn_type": ct.get("turn_type", ""),
                    "biasing_response": 1 if ct.get("biasing_response") else 0,
                    "missed_opportunity": 1 if ct.get("missed_opportunity") else 0,
                    "notes": ct.get("notes", ""),
                    "coded_by": "llm",
                })

    if len(results) != n:
        print(f"(warning: expected {n} turns, got {len(results)})", end=" ", flush=True)

    return results


# ---------------------------------------------------------------------------
# Agreement metrics
# ---------------------------------------------------------------------------

def cohens_kappa(y1, y2):
    n = len(y1)
    if n == 0:
        return float("nan")
    po = sum(a == b for a, b in zip(y1, y2)) / n
    c1, c2 = Counter(y1), Counter(y2)
    labels = set(y1) | set(y2)
    pe = sum((c1[lbl] / n) * (c2[lbl] / n) for lbl in labels)
    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def binary_report(label, pairs):
    if not pairs:
        return
    pct = sum(a == b for a, b in pairs) / len(pairs)
    kappa = cohens_kappa([p[0] for p in pairs], [p[1] for p in pairs])
    h_pos = sum(p[0] for p in pairs)
    h_neg = len(pairs) - h_pos
    tp = sum(1 for h, l in pairs if h == 1 and l == 1)
    tn = sum(1 for h, l in pairs if h == 0 and l == 0)
    sens = tp / h_pos if h_pos else float("nan")
    spec = tn / h_neg if h_neg else float("nan")
    print(f"\n{label}  (AI turns only, n={len(pairs)})")
    print(f"  % agreement:   {100*pct:.1f}%")
    print(f"  Cohen's kappa: {kappa:.3f}")
    print(f"  Sensitivity:   {100*sens:.1f}%  (caught {tp} of {h_pos} human-flagged)")
    print(f"  Specificity:   {100*spec:.1f}%  ({tn} of {h_neg} negatives correctly not flagged)")


# ---------------------------------------------------------------------------
# Preview mode
# ---------------------------------------------------------------------------

def preview(client, sample_size=5):
    """Mini run: classify a sample, print readable output, show agreement stats if coded data exists."""
    conn = sqlite3.connect(DB_PATH)

    coded_ids = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT transcript_id FROM coded_turns"
        ).fetchall()
    ]
    has_coded = len(coded_ids) > 0

    if has_coded:
        sample_ids = random.sample(coded_ids, min(sample_size, len(coded_ids)))
        print(f"Found {len(coded_ids)} manually coded transcripts.")
        print(f"Previewing {len(sample_ids)} — agreement stats will be shown.\n")
    else:
        rows = conn.execute(
            "SELECT transcript_id FROM transcripts ORDER BY RANDOM() LIMIT ?", (sample_size,)
        ).fetchall()
        sample_ids = [r[0] for r in rows]
        print(f"No manually coded data found. Previewing {len(sample_ids)} transcripts.\n")

    if not sample_ids:
        print("No transcripts found. Run load.py first.")
        conn.close()
        return

    human_turns = {}
    if has_coded:
        placeholders = ",".join("?" * len(sample_ids))
        for row in conn.execute(
            f"SELECT transcript_id, turn_number, turn_type, biasing_response, missed_opportunity "
            f"FROM coded_turns WHERE transcript_id IN ({placeholders})",
            sample_ids
        ).fetchall():
            human_turns[(row[0], row[1])] = {
                "turn_type": row[2],
                "biasing_response": row[3],
                "missed_opportunity": row[4],
            }

    all_results = []
    for i, tid in enumerate(sample_ids):
        row = conn.execute(
            "SELECT text, split FROM transcripts WHERE transcript_id=?", (tid,)
        ).fetchone()
        if not row:
            print(f"  Warning: {tid} not found in transcripts table, skipping")
            continue
        text, split = row

        print(f"[{i+1}/{len(sample_ids)}] {tid}  ({split or 'no split'})")
        try:
            results = classify_transcript(client, tid, text)
            for r in results:
                r["split"] = split
        except Exception as e:
            print(f"  FAILED: {e}\n")
            continue

        for r in results:
            flags = ""
            if r["biasing_response"]:
                flags += " [bias]"
            if r["missed_opportunity"]:
                flags += " [missed]"
            snippet = r["text"][:70].replace("\n", " ")
            if len(r["text"]) > 70:
                snippet += "…"
            print(f"  {r['turn_number']:>3}  {r['speaker']:<5}  {r['turn_type']:<15}{flags:<12}  \"{snippet}\"")

        all_results.extend(results)
        print()
        time.sleep(SLEEP_BETWEEN)

    conn.close()

    if has_coded and human_turns:
        turn_type_pairs, bias_pairs, missed_pairs = [], [], []
        for r in all_results:
            key = (r["transcript_id"], r["turn_number"])
            human = human_turns.get(key)
            if not human:
                continue
            if human["turn_type"] and r["turn_type"]:
                turn_type_pairs.append((human["turn_type"], r["turn_type"]))
            if r["speaker"] == "AI":
                bias_pairs.append((human["biasing_response"], r["biasing_response"]))
                missed_pairs.append((human["missed_opportunity"], r["missed_opportunity"]))

        print("=" * 60)
        print("AGREEMENT STATS")
        print("=" * 60)

        if turn_type_pairs:
            h = [p[0] for p in turn_type_pairs]
            l = [p[1] for p in turn_type_pairs]
            pct = sum(a == b for a, b in turn_type_pairs) / len(turn_type_pairs)
            kappa = cohens_kappa(h, l)
            print(f"\nturn_type  (n={len(turn_type_pairs)} turns)")
            print(f"  % agreement:   {100*pct:.1f}%")
            print(f"  Cohen's kappa: {kappa:.3f}")
            print(f"  Per-code breakdown:")
            for code in sorted(set(h)):
                subset = [(a, b) for a, b in turn_type_pairs if a == code]
                match = sum(1 for a, b in subset if a == b)
                print(f"    {code:<20} {match}/{len(subset)}  ({100*match/len(subset):.0f}%)")

        binary_report("biasing_response", bias_pairs)
        binary_report("missed_opportunity", missed_pairs)
        print()

    print("─" * 60)
    print("Looks good?  python llm_classifier.py --run")
    print("Need to adjust the schema?  edit schema.json, then re-run --preview")
    print("Re-classify after schema changes?  python llm_classifier.py --run --force")


# ---------------------------------------------------------------------------
# Run mode
# ---------------------------------------------------------------------------

def ensure_llm_table(conn):
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {LLM_TABLE} (
            transcript_id    TEXT,
            split            TEXT,
            turn_number      INTEGER,
            speaker          TEXT,
            text             TEXT,
            word_count       INTEGER,
            char_count       INTEGER,
            turn_type        TEXT,
            biasing_response INTEGER,
            missed_opportunity INTEGER,
            notes            TEXT,
            coded_by         TEXT DEFAULT 'llm',
            PRIMARY KEY (transcript_id, turn_number)
        )
    """)
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_llm_transcript ON {LLM_TABLE}(transcript_id)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_llm_split ON {LLM_TABLE}(split)")
    conn.commit()


def run(client, force=False):
    """Classify remaining un-coded transcripts into llm_coded_turns."""
    conn = sqlite3.connect(DB_PATH)

    if force:
        conn.execute(f"DROP TABLE IF EXISTS {LLM_TABLE}")
        conn.commit()
        print("Dropped existing llm_coded_turns table.")

    ensure_llm_table(conn)

    human_ids = set(
        r[0] for r in conn.execute("SELECT DISTINCT transcript_id FROM coded_turns").fetchall()
    )
    done_ids = set(
        r[0] for r in conn.execute(f"SELECT DISTINCT transcript_id FROM {LLM_TABLE}").fetchall()
    )

    all_rows = conn.execute(
        "SELECT transcript_id, split, text FROM transcripts ORDER BY split, transcript_id"
    ).fetchall()
    to_do = [
        (tid, split, text) for tid, split, text in all_rows
        if tid not in human_ids and tid not in done_ids
    ]

    total_target = len(all_rows) - len(human_ids)
    print(f"Target: {total_target} transcripts  |  Already done: {len(done_ids)}  |  Remaining: {len(to_do)}")

    if not to_do:
        print("Nothing to do.")
        conn.close()
        return

    start = time.time()
    for i, (tid, split, text) in enumerate(to_do):
        elapsed = time.time() - start
        done_so_far = i + 1
        if i > 0:
            rate = elapsed / i  # seconds per transcript
            eta = rate * (len(to_do) - i)
            eta_min = int(eta // 60)
            eta_str = f", ~{eta_min}m remaining"
        else:
            eta_str = ""

        pct = 100 * (len(done_ids) + done_so_far) / total_target
        print(f"  [{done_so_far}/{len(to_do)}, {pct:.0f}%{eta_str}] {tid} ({split})...", end=" ", flush=True)

        try:
            results = classify_transcript(client, tid, text)
            for r in results:
                r["split"] = split

            conn.executemany(
                f"INSERT OR REPLACE INTO {LLM_TABLE} VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [(r["transcript_id"], r["split"], r["turn_number"],
                  r["speaker"], r["text"], r["word_count"], r["char_count"],
                  r["turn_type"], r["biasing_response"], r["missed_opportunity"],
                  r["notes"], "llm") for r in results]
            )
            conn.commit()
            print(f"{len(results)} turns")
        except Exception as e:
            print(f"FAILED: {e}")

        time.sleep(SLEEP_BETWEEN)

    total_done = conn.execute(f"SELECT COUNT(DISTINCT transcript_id) FROM {LLM_TABLE}").fetchone()[0]
    total_turns = conn.execute(f"SELECT COUNT(*) FROM {LLM_TABLE}").fetchone()[0]
    conn.close()

    print(f"\nDone. {total_done} transcripts, {total_turns} turns saved to {LLM_TABLE}.")
    print("Launch Datasette to explore: ./start.sh")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LLM turn-level classifier for interview transcripts")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preview", action="store_true",
                       help="Classify a small sample and print results for review; shows agreement stats if coded data exists")
    group.add_argument("--run", action="store_true",
                       help="Classify all transcripts into llm_coded_turns")
    parser.add_argument("--force", action="store_true",
                        help="(with --run) Drop and recreate llm_coded_turns from scratch")
    parser.add_argument("--sample-size", type=int, default=5, metavar="N",
                        help="(with --preview) Number of transcripts to preview (default: 5)")
    args = parser.parse_args()

    global DEFAULT_MODEL, SYSTEM_PROMPT
    try:
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        DEFAULT_MODEL = schema.get("model", DEFAULT_MODEL)
    except FileNotFoundError:
        print(f"schema.json not found — using default model: {DEFAULT_MODEL}")

    SYSTEM_PROMPT = load_system_prompt()
    print(f"Using model: {DEFAULT_MODEL}  |  Codebook: {CODEBOOK_PATH}")

    client = anthropic.Anthropic(api_key=get_api_key())

    if args.preview:
        preview(client, sample_size=args.sample_size)
    else:
        run(client, force=args.force)


if __name__ == "__main__":
    main()
