# ai-interviewer-eval

A toolkit for evaluating the methodological quality of AI interviewer transcripts. It analyses turn-level dynamics including:

- **Probe depth** — how often the AI follows up vs. moves on (miss rate)
- **Response bias** — language that could steer participant responses (praise, leading interpretations, vocabulary substitution, agency shifts)
- **Interview structure** — turn type distribution (opening, new question, follow-up, closing)

Classification can be done manually (via spreadsheet or Airtable) or automatically using an LLM (Claude via the Anthropic API). Results are stored in a local SQLite database and browsable via Datasette.

<img width="10332" height="5007" alt="img_eval_workflow" src="https://github.com/user-attachments/assets/116d4433-4b50-4147-8513-5bb35107dc68" />


---

## Requirements

- Python 3.9+
- An Anthropic API key (for LLM classification)

```bash
pip install anthropic datasette python-dotenv requests
```

Create a `.env` file in the project root by copying `.env.example` and filling in your credentials:

```bash
cp .env.example .env
```

---

## Two workflows

### Run-As-Is
Use the default coding schema out of the box. Best for: getting a quick read on a dataset, or when the default turn-type and bias definitions fit your study.

```
load.py → llm_classifier.py --preview → llm_classifier.py --run → ./start.sh
```

### Customized
Adapt the coding schema and/or manually code a sample before running the full classifier. Best for: studies where the default definitions need adjusting, or where you want human-coded ground truth to validate the classifier.

```
load.py → [edit schema.json] → [prepare_sample.py → code CSV → load_coded.py]
        → llm_classifier.py --preview → llm_classifier.py --run → ./start.sh
```

---

## Run-As-Is workflow

### Step 1 — Load your transcripts

```bash
python load.py transcripts.csv
```

Supported formats: CSV, JSON, or a directory of `.txt` files (one file per transcript).

If your CSV uses different column names or speaker labels, configure them:

```bash
python load.py data.csv \
  --id-col interview_id \
  --text-col transcript \
  --split-col group \
  --ai-label Interviewer \
  --user-label Participant
```

Speaker labels in the transcript text (e.g. `Interviewer:`, `Bot:`) are normalised to `AI:` / `User:` on load so the rest of the toolkit works without further configuration.

If you have transcript groups (e.g. conditions, rounds), include them in a `split` column — this enables per-group analysis and stratified sampling later.

### Step 2 — Run a mini preview

```bash
python llm_classifier.py --preview
```

Classifies a small sample of transcripts (~5 by default) and prints the results for you to review. If you have manually coded data in the database, agreement statistics are shown automatically.

Review the outputs and decide: do the classifications look right? If yes, proceed. If not, see the [Customized workflow](#customized-workflow) to adjust the coding schema.

### Step 3 — Run the full classifier

```bash
python llm_classifier.py --run
```

Classifies all transcripts and saves results to the `llm_coded_turns` table. Transcripts already classified are skipped, so it's safe to re-run if interrupted.

### Step 4 — Explore results

```bash
./start.sh
```

Opens Datasette in your browser for browsing and filtering the results.

---

## Customized workflow

Use this when you want to adjust the coding schema, or when you need to manually code a sample to understand your data before writing a coding prompt.

### Option A — You already know what you want to change

Edit `schema.json` directly (see [Customizing schema.json](#customizing-schemajson)), then go straight to the preview step:

```bash
python llm_classifier.py --preview
```

If the preview looks good, run the full classifier:

```bash
python llm_classifier.py --run
```

If you updated the coding schema and want to re-run transcripts that were already classified:

```bash
python llm_classifier.py --run --force
```

`--force` drops and recreates the `llm_coded_turns` table from scratch. Use this any time you change the coding schema and want clean results.

### Option B — You need to manually code a sample first

This is the right path when you're not yet sure how the coding categories apply to your data.

**1. Pull a sample**

```bash
python prepare_sample.py
```

Selects a stratified random sample of transcripts, parses them into individual turns, pre-labels what can be detected automatically (first/last AI turn, User turns, explicit praise patterns), and saves the result to `sample_turns.csv`.

Sample size and strategy are configured in `schema.json` under the `"sample"` key.

**2. Code the sample**

Open `sample_turns.csv` in a spreadsheet (Excel, Google Sheets, Numbers). Fill in the `turn_type`, `biasing_response`, `missed_opportunity`, and `notes` columns for each AI turn.

Refer to [CODEBOOK.md](CODEBOOK.md) for coding definitions and decision rules.

The `turn_type` column accepts: `opening`, `new_question`, `follow_up`, `closing`, `response`, `ambiguous`, `other`.

The `biasing_response` and `missed_opportunity` columns accept: `TRUE` / `FALSE` (or `1` / `0`).

**3. Load codes back into the database**

```bash
python load_coded.py --from-csv sample_turns.csv
```

Writes the manually coded turns into the `coded_turns` table in `interviews.db`.

**4. Update the coding schema**

Use what you learned from coding to refine the definitions and patterns in `schema.json`. See [Customizing schema.json](#customizing-schemajson).

**5. Preview and validate**

```bash
python llm_classifier.py --preview
```

Because you now have manually coded data in the database, the preview will also show agreement statistics (% agreement and Cohen's kappa) between your codes and the classifier's output.

If the agreement is good enough for your purposes, proceed. If not, refine `schema.json` and preview again.

**6. Run the full classifier**

```bash
python llm_classifier.py --run
```

Or, if you updated the coding schema since a previous run:

```bash
python llm_classifier.py --run --force
```

---

## Script reference

| Script | Purpose |
|--------|---------|
| `load.py` | Load transcripts into `interviews.db` |
| `prepare_sample.py` | Pull a stratified sample for manual coding |
| `load_coded.py` | Load a manually coded CSV back into the database |
| `llm_classifier.py` | Run LLM classification (preview, full run) |
| `start.sh` | Launch Datasette to browse results |
| `push_to_airtable.py` | *(Optional)* Push sample to Airtable for manual coding |
| `pull_from_airtable.py` | *(Optional)* Pull codes from Airtable back into the database |

### load.py

```
python load.py <source> [options]

Arguments:
  source             CSV file, JSON file, or directory of .txt files

Options:
  --id-col COL       Column name for transcript ID     (default: transcript_id)
  --text-col COL     Column name for transcript text   (default: text)
  --split-col COL    Column name for split/group       (default: split; omitted if absent)
  --ai-label LABEL   Speaker label for AI/interviewer  (default: AI)
  --user-label LABEL Speaker label for participant     (default: User)
  --db PATH          Database path                     (default: interviews.db)
  --force            Drop and recreate the transcripts table
```

### llm_classifier.py

```
python llm_classifier.py --preview                   Mini run (5 transcripts by default)
python llm_classifier.py --preview --sample-size 20  Preview a larger sample
python llm_classifier.py --run                       Classify all transcripts
python llm_classifier.py --run --force               Drop llm_coded_turns and re-classify everything from scratch
```

`--preview` prints each turn with its classification and any `[bias]` or `[missed]` flags so you can eyeball the results. If manually coded data exists in `coded_turns`, agreement statistics (% agreement and Cohen's kappa) are shown automatically.

Use `--run --force` any time you update the coding schema and want the classifier to re-run cleanly on the full dataset.

### prepare_sample.py

```
python prepare_sample.py
```

Reads sample configuration from `schema.json`. Outputs `sample_turns.csv` and `sample_turns.json`.

### load_coded.py

```
python load_coded.py --from-csv FILE [options]

Options:
  --from-csv FILE    Path to the coded CSV file (required)
  --db PATH          Database path (default: interviews.db)
  --force            Drop and recreate the coded_turns table
```

---

## Customizing the toolkit

### CODEBOOK.md — the coding rules

`CODEBOOK.md` is the single source of truth for coding rules. It is used by:
- **Human coders** — as a reference guide when manually coding turns in a spreadsheet
- **The LLM classifier** — read at runtime as the system prompt

When you edit `CODEBOOK.md`, both the human and LLM coding instructions update together, keeping them in sync. If your `--preview` agreement scores are poor, refining the definitions, decision rules, or examples in `CODEBOOK.md` is the first thing to try.

### schema.json — technical configuration

`schema.json` holds the technical config that is not prose. Edit it to adapt the toolkit to your dataset.

### Model selection (`model`)

Controls which Claude model is used for classification:

```json
"model": "claude-sonnet-4-6"
```

- `claude-sonnet-4-6` — default; fast and cost-effective
- `claude-opus-4-8` — more capable; better for nuanced judgment calls like `biasing_response` and `missed_opportunity` if kappa scores are poor

### Coding prompt (`turn_types`)

Defines what each turn type means. The classifier uses these definitions to decide how to label each turn. Edit the descriptions to match your study's interview structure.

### Bias detection patterns (`biasing_response_patterns`)

A list of regex patterns used to auto-detect explicit praise in the AI's turns. These are pre-populated with common patterns but are only a starting point — they catch explicit praise phrases, not interpretive reframes, which always require manual judgment.

To add a pattern:

```json
"biasing_response_patterns": [
  "(?i)^that'?s\\s+really\\s+interesting",
  "(?i)^your own pattern here"
]
```

### Auto-labeling rules (`auto_label_rules`)

Rules applied by `prepare_sample.py` to pre-label turns before manual coding, reducing the amount of manual work needed.

By default, only position-based rules are active (first AI turn → `opening`, last AI turn → `closing`). You can add pattern-based rules for recurring phrases in your transcripts:

```json
"auto_label_rules": {
  "opening": [
    {"match": "first AI turn in transcript", "note": "Auto-labeled by position"},
    {"match_pattern": "(?i)tell me about your typical day", "note": "Standard opening question"}
  ],
  "closing": [
    {"match": "last AI turn in transcript", "note": "Auto-labeled by position"},
    {"match_pattern": "(?i)those are all the questions", "note": "Standard closing phrase"}
  ]
}
```

### Sample configuration (`sample`)

Controls how `prepare_sample.py` selects transcripts:

```json
"sample": {
  "n": 40,
  "seed": 42,
  "lower_half_ratio": 0.5
}
```

- `n` — total number of transcripts to sample
- `seed` — random seed for reproducibility; set to `null` for a random draw each time
- `lower_half_ratio` — fraction of the sample drawn from shorter transcripts (by word count); 0.5 means half short, half long

To sample a fixed number per group instead of a flat total, add a `splits` object:

```json
"sample": {
  "seed": 42,
  "lower_half_ratio": 0.5,
  "splits": {
    "condition_a": 20,
    "condition_b": 20
  }
}
```

The split names must match values in the `split` column of your transcripts table.

---

## Manual coding with Airtable (optional)

If you prefer to code in Airtable rather than a spreadsheet, use the Airtable scripts instead of `load_coded.py`:

**Setup:** Add your Airtable credentials to `.env` (see `.env.example`).

```bash
python prepare_sample.py          # Pull sample → sample_turns.csv
python push_to_airtable.py        # Push sample to Airtable
# ... code in Airtable ...
python pull_from_airtable.py      # Pull codes back into interviews.db
```

Then continue with `llm_classifier.py --preview` as normal.

---

## Database tables

Results are stored in `interviews.db` (SQLite). Launch Datasette with `./start.sh` to browse them.

| Table | Contents |
|-------|----------|
| `transcripts` | All loaded transcripts with metadata |
| `coded_turns` | Manually coded turns (from CSV or Airtable) |
| `llm_coded_turns` | LLM-classified turns |
