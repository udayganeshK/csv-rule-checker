import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile
import itertools
import io
import numpy as np
import re

st.title("Rule File Checker")

uploaded_file = st.file_uploader("Upload a CSV file or a .zip file containing CSV rule files", type=["zip", "csv"])

if uploaded_file:
    with tempfile.TemporaryDirectory() as tmpdir:
        if uploaded_file.name.endswith('.zip'):
            zip_path = os.path.join(tmpdir, "uploaded.zip")
            with open(zip_path, "wb") as f:
                f.write(uploaded_file.read())
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdir)
            search_dir = tmpdir
        elif uploaded_file.name.endswith('.csv'):
            csv_path = os.path.join(tmpdir, uploaded_file.name)
            with open(csv_path, "wb") as f:
                f.write(uploaded_file.read())
            search_dir = tmpdir
        else:
            st.error("Unsupported file type.")
            search_dir = None

        if search_dir:
            csv_files = []
            for root, _, files in os.walk(search_dir):
                for file in files:
                    if file.endswith('.csv'):
                        csv_files.append(os.path.join(root, file))
            if not csv_files:
                st.warning("No CSV files found in the uploaded file.")
            else:
                results = []
                for csv_file in csv_files:
                    st.subheader(f"Checking: {os.path.basename(csv_file)}")
                    file_results = []
                    try:
                        meta_df = pd.read_csv(csv_file, nrows=2, header=None, skip_blank_lines=True, engine='python')
                        df = pd.read_csv(csv_file, skiprows=2, skip_blank_lines=True, engine='python', header=None)
                    except Exception as e:
                        msg = f"Error reading file: {e}"
                        st.error(msg)
                        file_results.append(msg)
                        results.append({'file': os.path.basename(csv_file), 'result': msg})
                        continue

                    # Row 1: must be ['name', 'CONDITION', 'ACTION', 'PRIORITY'] (case-insensitive)
                    header_types = [str(x).strip().lower() for x in meta_df.iloc[0]]
                    if header_types[0] != "name" or header_types[-1] != "priority" or "condition" not in header_types or "action" not in header_types:
                        st.error("First row must have columns: name, CONDITION, ACTION, PRIORITY (in any order, case-insensitive)")
                        continue

                    # Row 2: field names
                    field_names = [str(x).strip() for x in meta_df.iloc[1]]
                    df.columns = field_names

                    # Identify columns
                    name_col = field_names[0]
                    priority_col = field_names[-1]
                    # All columns between name and priority
                    mid_cols = field_names[1:-1]
                    # Use header_types to split mid_cols into condition and action columns
                    condition_cols = [col for col, typ in zip(mid_cols, header_types[1:-1]) if typ == "condition"]
                    action_cols = [col for col, typ in zip(mid_cols, header_types[1:-1]) if typ == "action"]

                    # Validation
                    if not name_col or not condition_cols or not action_cols or not priority_col:
                        st.error("Rule file must have name, at least one CONDITION, at least one ACTION, and PRIORITY columns.")
                        continue

                    st.success("File structure is valid.")
                    # Row-level checks
                    if not (df[name_col].notnull().all() and (df[name_col] != '').all()):
                        msg = "Some rows have empty 'name' values."
                        st.error(msg)
                        file_results.append(msg)
                    for idx, row in df.iterrows():
                        if not any(str(row[col]).strip() for col in condition_cols):
                            msg = f"Row {idx+1} has all empty 'condition' columns."
                            st.error(msg)
                            file_results.append(msg)
                        if not any(str(row[col]).strip() for col in action_cols):
                            msg = f"Row {idx+1} has all empty 'action' columns."
                            st.error(msg)
                            file_results.append(msg)
                    # --- Automated test data generation and rule matching ---
                    st.markdown("---")
                    st.header("Automated Rule Test Results (Kruz-style)")
                    # Generate test data: for each unique combination of condition values in the rule file
                    test_data = df[condition_cols].drop_duplicates().reset_index(drop=True)
                    st.write("Generated Test Data:", test_data)
                    def parse_condition(expr, value):
                        expr = str(expr).strip()
                        value = str(value).strip()
                        if expr == '' or pd.isna(expr):
                            return True
                        # Improved regex: allow negative numbers, decimals, and spaces
                        m = re.match(r'([a-zA-Z0-9_ ]+)\s*([><=]=?|=)\s*(-?\d+\.?\d*|[a-zA-Z0-9_.-]+)', expr)
                        if m:
                            field, op, rule_val = m.groups()
                            # Try numeric comparison
                            try:
                                test_val = float(value)
                                rule_val = float(rule_val)
                                if op == '>':
                                    return test_val > rule_val
                                elif op == '<':
                                    return test_val < rule_val
                                elif op == '>=':
                                    return test_val >= rule_val
                                elif op == '<=':
                                    return test_val <= rule_val
                                elif op == '=':
                                    return test_val == rule_val
                            except ValueError:
                                # Fallback to string/boolean comparison
                                if op == '=':
                                    return str(value).lower() == str(rule_val).lower()
                                else:
                                    return False
                        # fallback to equality
                        return expr == value
                    test_results = []
                    for idx, test_row in test_data.iterrows():
                        matched_rule = None
                        for _, rule_row in df.iterrows():
                            match = True
                            for cond_col in condition_cols:
                                rule_val = str(rule_row[cond_col]).strip()
                                test_val = str(test_row[cond_col]).strip()
                                # If rule_val is empty, treat as wildcard
                                if rule_val == '' or pd.isna(rule_val):
                                    continue
                                # Use kruz-style evaluation: rule_val is the condition expression, test_val is the value to check
                                if not parse_condition(rule_val, test_val):
                                    match = False
                                    break
                            if match:
                                matched_rule = rule_row
                                break
                        if matched_rule is not None:
                            actions = {col: matched_rule[col] for col in action_cols}
                            # Use name_col instead of hardcoded 'name'
                            test_results.append({**test_row, **actions, 'matched_rule': matched_rule[name_col], 'rule_status': 'Passed'})
                        else:
                            test_results.append({**test_row, 'matched_rule': 'No match', 'actions': '', 'rule_status': 'Failed'})
                    test_result_df = pd.DataFrame(test_results)
                    st.dataframe(test_result_df)
                    st.download_button("Download Automated Test Results", test_result_df.to_csv(index=False), file_name="automated_test_results.csv")
                    # --- Kruz-style Rule Executor UI ---
                    st.markdown("---")
                    st.header("Kruz-style Rule Executor")
                    st.write("Enter test input values for each condition column:")

                    # Parse operator from column header for each condition column
                    cond_col_ops = {}
                    for cond_col in condition_cols:
                        # Extract operator from column header (e.g., "fico >", "tier =")
                        m = re.match(r'([a-zA-Z0-9_ ]+)\s*([><=]=?|=)?\s*$', cond_col)
                        if m:
                            field, op = m.groups()
                            field = field.strip()
                            op = op.strip() if op else '='  # Default to '=' if no operator
                            cond_col_ops[cond_col] = (field, op)
                        else:
                            cond_col_ops[cond_col] = (cond_col.strip(), '=')

                    user_inputs = {}
                    for cond_col in condition_cols:
                        field, _ = cond_col_ops[cond_col]
                        user_inputs[cond_col] = st.text_input(f"{field}", value="")

                    def parse_and_eval(col_op, rule_val, user_val):
                        # col_op: (field, op) from column header
                        # rule_val: value from rule row cell
                        # user_val: value entered by user
                        _, op = col_op
                        rule_val = str(rule_val).strip()
                        user_val = str(user_val).strip()
                        if rule_val == '' or pd.isna(rule_val):
                            return True
                        # Numeric comparison if possible
                        try:
                            user_val_num = float(user_val)
                            rule_val_num = float(rule_val)
                            if op == '>':
                                return user_val_num > rule_val_num
                            elif op == '<':
                                return user_val_num < rule_val_num
                            elif op == '>=':
                                return user_val_num >= rule_val_num
                            elif op == '<=':
                                return user_val_num <= rule_val_num
                            elif op == '=':
                                return user_val_num == rule_val_num
                        except ValueError:
                            if op == '=':
                                return user_val.lower() == rule_val.lower()
                            else:
                                return False
                        return False

                    if st.button("Evaluate Rule File with Test Inputs"):
                        matched_rules = []
                        failed_reasons = []
                        for rule_idx, rule_row in df.iterrows():
                            match = True
                            mismatch_details = []
                            for cond_col in condition_cols:
                                col_op = cond_col_ops[cond_col]
                                rule_val = rule_row[cond_col]
                                user_val = user_inputs[cond_col]
                                if not parse_and_eval(col_op, rule_val, user_val):
                                    match = False
                                    mismatch_details.append(
                                        f"Rule {rule_idx+1} [{col_op[0]}]: input '{user_val}' did not satisfy '{col_op[0]} {col_op[1]} {rule_val}'"
                                    )
                            if match:
                                matched_rules.append(rule_row)
                            else:
                                failed_reasons.append(
                                    f"Rule {rule_idx+1} ({rule_row[name_col]}): " + "; ".join(mismatch_details)
                                )
                        if matched_rules:
                            # Pick rule with lowest priority (priority as int, lower is higher priority)
                            try:
                                matched_rules = sorted(matched_rules, key=lambda r: int(r[priority_col]))
                            except Exception:
                                matched_rules = sorted(matched_rules, key=lambda r: str(r[priority_col]))
                            best_rule = matched_rules[0]
                            actions = {col: best_rule[col] for col in action_cols}
                            st.success(f"Matched Rule: {best_rule[name_col]} (Priority: {best_rule[priority_col]})")
                            st.write("Actions to perform:", actions)
                        else:
                            st.error("No matching rule found for the given inputs.")
                            if failed_reasons:
                                st.markdown("#### Why no rule matched:")
                                for reason in failed_reasons:
                                    st.write(reason)

                results.append({'file': os.path.basename(csv_file), 'result': '\n'.join(file_results)})
                # Download results
                if results:
                    output = io.StringIO()
                    for r in results:
                        output.write(f"File: {r['file']}\n{r['result']}\n{'-'*40}\n")
                    # Use a truly unique key for each download button (add an incrementing index)
                    st.download_button(
                        "Download Results",
                        output.getvalue(),
                        file_name="rule_check_results.txt",
                        key=f"download_results_{os.path.basename(csv_file)}_{len(results)}"
                    )
                    # st.download_button("Download Results", output.getvalue(), file_name="rule_check_results.txt")
                    # st.download_button("Download Results", output.getvalue(), file_name="rule_check_results.txt")

                results.append({'file': os.path.basename(csv_file), 'result': '\n'.join(file_results)})
                # Download results
                if results:
                    output = io.StringIO()
                    for r in results:
                        output.write(f"File: {r['file']}\n{r['result']}\n{'-'*40}\n")
                    # Use a truly unique key for each download button (add an incrementing index)
                    st.download_button(
                        "Download Results",
                        output.getvalue(),
                        file_name="rule_check_results.txt",
                        key=f"download_results_{os.path.basename(csv_file)}_{len(results)}"
                    )
                    # st.download_button("Download Results", output.getvalue(), file_name="rule_check_results.txt")
                    # st.download_button("Download Results", output.getvalue(), file_name="rule_check_results.txt")
                    # st.download_button("Download Results", output.getvalue(), file_name="rule_check_results.txt")
                    output.write(f"File: {r['file']}\n{r['result']}\n{'-'*40}\n")
                    st.download_button("Download Results", output.getvalue(), file_name="rule_check_results.txt", key="download_results")
                    # st.download_button("Download Results", output.getvalue(), file_name="rule_check_results.txt")
                    # st.download_button("Download Results", output.getvalue(), file_name="rule_check_results.txt")
                    # st.download_button("Download Results", output.getvalue(), file_name="rule_check_results.txt")