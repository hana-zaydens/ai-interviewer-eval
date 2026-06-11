#!/bin/bash
source "$(dirname "$0")/venv/bin/activate"
datasette interviews.db --metadata metadata.json --open
