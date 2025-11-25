"""
generate_prevalences_fixed.py

Variant of the OWID/GBD mapping script that runs directly on one hard-coded SNP-result CSV.
No command-line args required.

How to use in VS Code:
 - Edit INPUT_FILE below to point to your single SNP-result CSV (e.g. "C:\\Users\\vishal\\Desktop\\test\\nutritional_snps_final.csv")
 - Open this file in VS Code and press Run (or use the Python extension Run button).
 - The script will attempt to download OWID endpoints, match traits -> causes, and write:
     - prevalences.json
     - prevalences_report.csv
"""

import json
import os
import re
from glob import glob
import requests
import pandas as pd
from thefuzz import process, fuzz
from tqdm import tqdm

# -------------------------
# USER CONFIG (edit these)
# -------------------------
INPUT_FILE = r"C:\Users\vishal\Desktop\test\nutritional_snps_final.csv"  # <-- set your file path here
LOCATION = "World"   # hard-coded location
YEAR = "2021"        # hard-coded year
OUT_JSON = "prevalences.json"
OUT_REPORT = "prevalences_report.csv"
FUZZY_THRESHOLD = 80

# -------------------------
# End user config
# -------------------------

OWID_ENDPOINTS = [
    ("depressive_disorders", "https://ourworldindata.org/grapher/depressive-disorders-prevalence-ihme.csv"),
    ("migraine_disorders", "https://ourworldindata.org/grapher/migraine_disorders_prevalence-ihme.csv"),
    ("cardio_prevalence", "https://ourworldindata.org/grapher/prevalence-rate-of-cardiovascular-disease.csv"),
    ("diabetes_prevalence", "https://ourworldindata.org/grapher/diabetes-prevalence.csv"),
]

DEFAULT_PREVALENCES = {
    "hypertension": 0.32,
    "diabetes mellitus": 0.10,
    "type 2 diabetes": 0.10,
    "obesity": 0.16,
    "gout": 0.0066,
    "non-alcoholic fatty liver disease": 0.25,
    "migraine disorder": 0.07,
    "schizophrenia": 0.004,
    "attention deficit hyperactivity disorder": 0.05,
    "coronary artery disease": 0.06,
    "ischaemic heart disease": 0.06,
    "stroke": 0.02,
    "chronic kidney disease": 0.09,
    "alcohol use disorder": 0.04,
    "hypercholesterolemia": 0.15,
    "type 1 diabetes": 0.0004
}

def normalize_text(s):
    if s is None:
        return ""
    s = str(s).lower().strip()
    s = re.sub(r'[_\-\(\)\[\]:,;]+', ' ', s)
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'[^a-z0-9 ]+', '', s)
    return s.strip()

def download_csv(url, timeout=30):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        from io import StringIO
        return pd.read_csv(StringIO(r.text), dtype=str)
    except Exception as e:
        print(f"Warning: could not download {url}: {e}")
        return None

def collect_traits_from_file(path):
    df = pd.read_csv(path, dtype=str)
    if "MESH_TERM" in df.columns and df["MESH_TERM"].notna().any():
        traits = df["MESH_TERM"].dropna().unique().tolist()
    elif "MAPPED_TRAIT" in df.columns:
        traits = df["MAPPED_TRAIT"].dropna().unique().tolist()
    else:
        candidates = [c for c in df.columns if 'trait' in c.lower() or 'disease' in c.lower()]
        if candidates:
            traits = df[candidates[0]].dropna().unique().tolist()
        else:
            traits = []
    return [t for t in traits if isinstance(t, str) and t.strip()]

def build_cause_index_from_owid(dfs, location, year):
    cause_to_prev = {}
    cause_names = set()
    for df in dfs:
        cols = [c.lower() for c in df.columns]
        possible_location_cols = [c for c in df.columns if 'location' in c.lower() or 'entity' in c.lower() or 'country' in c.lower()]
        possible_year_cols = [c for c in df.columns if 'year' in c.lower() or 'time' in c.lower() or 'date' in c.lower()]
        possible_value_cols = [c for c in df.columns if any(k in c.lower() for k in ['preval','val','mean','estimate','value','rate'])]
        loc_col = possible_location_cols[0] if possible_location_cols else None
        year_col = possible_year_cols[0] if possible_year_cols else None
        val_col = possible_value_cols[0] if possible_value_cols else None
        if val_col is None:
            continue
        subset = df.copy()
        if loc_col:
            subset = subset[subset[loc_col].astype(str).str.lower() == location.lower()]
        if year_col:
            subset = subset[subset[year_col].astype(str) == str(year)]
        name_col = None
        for c in ['variable','indicator','cause','cause_name','name','label','entity']:
            if c in [x.lower() for x in df.columns]:
                name_col = next(x for x in df.columns if x.lower()==c)
                break
        if name_col is None:
            for idx, row in subset.iterrows():
                parts = []
                for c in subset.columns:
                    cl = c.lower()
                    if cl in [loc_col.lower() if loc_col else None, year_col.lower() if year_col else None, val_col.lower()]:
                        continue
                    parts.append(str(row[c]))
                cause_name = " ".join([p for p in parts if p and p != 'nan']).strip()
                if not cause_name:
                    continue
                try:
                    val = float(row[val_col])
                except:
                    continue
                cause_to_prev[cause_name] = val
                cause_names.add(cause_name)
        else:
            for idx, row in subset.iterrows():
                cname = str(row[name_col])
                try:
                    val = float(row[val_col])
                except:
                    continue
                cause_to_prev[cname] = val
                cause_names.add(cname)
    return cause_to_prev, list(cause_names)

# -------------------------
# Run (hard-coded behavior)
# -------------------------
if not os.path.isfile(INPUT_FILE):
    raise SystemExit(f"Input file not found: {INPUT_FILE}")

print("Reading traits from:", INPUT_FILE)
traits = collect_traits_from_file(INPUT_FILE)
print("Found", len(traits), "unique traits in the file.")

print("Attempting to download public OWID/GBD-derived CSVs...")
dfs = []
for name, url in OWID_ENDPOINTS:
    df = download_csv(url)
    if df is not None:
        print("  downloaded:", name)
        dfs.append(df)
if not dfs:
    print("No datasets downloaded. Will use defaults for matches where possible.")

cause_to_prev = {}
cause_names = []
if dfs:
    cause_to_prev, cause_names = build_cause_index_from_owid(dfs, LOCATION, YEAR)
    print("Built cause index with", len(cause_to_prev), "entries from downloaded datasets.")

prevalences = {}
report_rows = []

for t in tqdm(traits, desc="Mapping traits"):
    matched = None
    score = 0
    prev = None
    source = None
    tn = normalize_text(t)
    if cause_names:
        best = process.extractOne(t, cause_names, scorer=fuzz.token_sort_ratio)
        if best:
            matched, score = best[0], int(best[1])
            if matched in cause_to_prev and cause_to_prev[matched] is not None:
                prev = float(cause_to_prev[matched])
                source = f"OWID_GBD:{YEAR}"
    if prev is None:
        for dk, dv in DEFAULT_PREVALENCES.items():
            if dk in tn or tn in dk:
                prev = dv
                source = "DEFAULT"
                if matched is None:
                    matched = dk
                    score = 100
                break
    prevalences[t] = {LOCATION: {str(YEAR): prev}}
    report_rows.append({
        "trait": t,
        "matched_cause": matched,
        "score": score,
        "prevalence": prev,
        "source": source
    })

with open(OUT_JSON, "w") as f:
    json.dump(prevalences, f, indent=2)
pd.DataFrame(report_rows).to_csv(OUT_REPORT, index=False)

print("Wrote", OUT_JSON, "and", OUT_REPORT)
print("Finished. Please inspect", OUT_REPORT, "and edit", OUT_JSON, "if necessary.")
