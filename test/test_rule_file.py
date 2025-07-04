import pandas as pd
import pytest
import itertools

CSV_PATH = 'csv rule checker/test/ruleFile.csv'

def clean_columns(columns):
    return [col.strip().lower() for col in columns]

def load_csv(path):
    try:
        df = pd.read_csv(path, skip_blank_lines=True, engine='python')
    except Exception:
        df = pd.read_csv(path, skip_blank_lines=True, engine='python', header=1)
    df.columns = clean_columns(df.columns)
    return df

def test_required_columns():
    df = load_csv(CSV_PATH)
    columns = df.columns
    assert any(col == 'name' for col in columns), "Missing 'name' column"
    assert any(col.startswith('condition') or col == 'condition' for col in columns), "No 'condition' columns found"
    assert any(col.startswith('action') or col == 'action' for col in columns), "No 'action' columns found"

def test_non_empty_name():
    df = load_csv(CSV_PATH)
    assert df['name'].notnull().all() and (df['name'] != '').all(), "Some rows have empty 'name' values"

def test_at_least_one_condition_per_row():
    df = load_csv(CSV_PATH)
    condition_cols = [col for col in df.columns if col.startswith('condition') or col == 'condition']
    assert any(condition_cols), "No 'condition' columns found"
    for idx, row in df.iterrows():
        assert any(str(row[col]).strip() for col in condition_cols), f"Row {idx+1} has all empty 'condition' columns"

def test_at_least_one_action_per_row():
    df = load_csv(CSV_PATH)
    action_cols = [col for col in df.columns if col.startswith('action') or col == 'action']
    assert any(action_cols), "No 'action' columns found"
    for idx, row in df.iterrows():
        assert any(str(row[col]).strip() for col in action_cols), f"Row {idx+1} has all empty 'action' columns"
