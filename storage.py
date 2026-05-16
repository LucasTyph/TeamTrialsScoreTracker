"""CSV data persistence."""

import os
from datetime import datetime

import pandas as pd

import config


def _csv_path():
    return os.path.join(config.DATA_DIR, config.CSV_FILENAME)


def load_data():
    path = _csv_path()
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


def append_match(scores):
    path = _csv_path()
    os.makedirs(config.DATA_DIR, exist_ok=True)

    row = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")}
    for name in config.CHARACTER_NAMES:
        row[name] = scores.get(name, None)

    new_df = pd.DataFrame([row])

    if os.path.exists(path):
        existing = pd.read_csv(path)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_csv(path, index=False)
    return row
