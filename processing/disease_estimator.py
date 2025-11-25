"""
Disease Estimation Module
Wrapper for diseaseEstimation.py functionality
"""

import os
import re
import json
import math
import numpy as np
import pandas as pd
from pathlib import Path
from tqdm import tqdm

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

PREV_JSON = Path(__file__).parent.parent / "prevalences.json"

# Simulation settings - Reduced for faster processing
N_SIM = 2000  # Reduced from 8000 for faster results
RNG_SEED = 42

# Disease keywords
DISEASE_KEYWORDS = [
    "disease", "disorder", "syndrome", "cancer", "carcinoma", "tumor", "tumour",
    "diabetes", "hypertension", "stroke", "cardio", "heart", "myocardial",
    "coronary", "gout", "nephropathy", "kidney", "renal", "arthrit", "alzheim",
    "dementia", "asthma", "copd", "chronic kidney", "non-alcoholic", "nafld",
    "liver", "hepatitis", "migraine", "schizophrenia", "depress", "bipolar",
    "psych", "epilep", "autism", "parkinson", "glaucoma", "retinopathy",
    "obesity", "cancer", "pulmonary", "hypertensi", "ischemic", "ischaemic"
]
DISEASE_KEYWORDS = [k.lower() for k in DISEASE_KEYWORDS]

PERCENTILE_HIGH = 90
PERCENTILE_MODERATE = 75
ABS_PROB_HIGH = 0.20
ABS_PROB_MODERATE = 0.05

def normalize_trait(t):
    if pd.isna(t):
        return ""
    return re.sub(r'[^a-z0-9 ]+', ' ', str(t).lower()).strip()

def trait_is_disease(trait):
    tn = normalize_trait(trait)
    for kw in DISEASE_KEYWORDS:
        if kw in tn:
            return True
    return False

def parse_risk_allele_field(s):
    if pd.isna(s):
        return None
    s = str(s)
    if '-' in s:
        token = s.split('-')[-1]
    else:
        token = s
    m = re.search(r'([ACGT])', token.upper())
    if m:
        return m.group(1)
    token = token.strip().upper()
    return token[0] if token else None

def dosage_from_genotype(geno, allele):
    if pd.isna(geno) or allele is None:
        return np.nan
    g = str(geno).upper().replace("|", "/").replace(" ", "")
    if "/" in g:
        parts = g.split("/")
        return sum(1 for p in parts if p == allele)
    if len(g) == 2:
        return sum(1 for ch in g if ch == allele)
    return g.count(allele)

def to_log_or_safe(x):
    try:
        v = float(x)
        if v <= 0:
            return np.nan
        return math.log(v)
    except:
        return np.nan

def estimate_diseases(nutritional_snp_path, user_folder, analysis_id):
    """Estimate diseases from nutritional SNP data"""
    
    input_csv = Path(nutritional_snp_path)
    output_path = user_folder / f"disease_candidates_{analysis_id}.csv"
    
    # Load CSV
    df = pd.read_csv(input_csv, dtype=str)
    
    # Detect columns
    genotype_col = None
    for c in df.columns:
        if c.lower() == "genotype":
            genotype_col = c
            break
    
    risk_allele_col = None
    for c in df.columns:
        if 'strongest' in c.lower() and 'allele' in c.lower():
            risk_allele_col = c
            break
    
    effect_col = None
    for choice in ["OR or BETA", "OR", "BETA", "OR_OR_BETA"]:
        if choice in df.columns:
            effect_col = choice
            break
    
    raf_col = None
    for c in df.columns:
        if 'risk' in c.lower() and 'freq' in c.lower():
            raf_col = c
            break
    
    trait_col = None
    if "MESH_TERM" in df.columns and df["MESH_TERM"].notna().any():
        trait_col = "MESH_TERM"
    elif "MAPPED_TRAIT" in df.columns:
        trait_col = "MAPPED_TRAIT"
    
    # Process data
    df_proc = df.copy()
    df_proc['risk_allele_parsed'] = df_proc[risk_allele_col].apply(parse_risk_allele_field)
    df_proc['dosage'] = df_proc.apply(
        lambda r: dosage_from_genotype(r[genotype_col], r['risk_allele_parsed']), axis=1
    )
    df_proc['effect_raw'] = pd.to_numeric(df_proc[effect_col], errors='coerce')
    
    effect_type = 'or'
    if (df_proc['effect_raw'].dropna() < 0).any():
        effect_type = 'beta'
    
    if effect_type == 'or':
        df_proc['effect'] = df_proc['effect_raw'].apply(to_log_or_safe)
    else:
        df_proc['effect'] = df_proc['effect_raw']
    
    if raf_col:
        df_proc['raf'] = pd.to_numeric(df_proc[raf_col], errors='coerce')
    else:
        df_proc['raf'] = np.nan
    
    # Load prevalences
    prevalences = {}
    if PREV_JSON.exists():
        with open(PREV_JSON, 'r') as f:
            prevalences = json.load(f)
    
    # Process traits
    traits = sorted(df_proc[trait_col].dropna().unique().tolist())
    results = []
    
    rng = np.random.default_rng(seed=RNG_SEED)
    
    for trait in tqdm(traits, desc="Processing traits"):
        sub = df_proc[df_proc[trait_col] == trait].copy()
        sub['dosage'] = pd.to_numeric(sub['dosage'], errors='coerce')
        sub = sub.dropna(subset=['effect'])
        
        if sub.shape[0] == 0:
            continue
        
        prs_indiv = float((sub['dosage'].fillna(0).astype(float) * sub['effect'].astype(float)).sum())
        n_snps = int(sub.shape[0])
        n_with_geno = int(sub['dosage'].notna().sum())
        
        # Simulation
        sim_sub = sub.dropna(subset=['raf', 'effect']).copy()
        sim_mean = np.nan
        sim_sd = np.nan
        percentile = np.nan
        zscore = np.nan
        sim_used = 0
        
        if sim_sub.shape[0] > 0:
            effects = sim_sub['effect'].astype(float).values
            rafts = sim_sub['raf'].astype(float).values
            n_sim = int(N_SIM)
            sim_prs = np.zeros(n_sim, dtype=float)
            for ef, p in zip(effects, rafts):
                if np.isnan(ef) or np.isnan(p):
                    continue
                p0 = (1-p)**2
                p1 = 2*p*(1-p)
                p2 = p**2
                draws = rng.choice([0, 1, 2], size=n_sim, p=[p0, p1, p2])
                sim_prs += draws * ef
            sim_mean = float(sim_prs.mean())
            sim_sd = float(sim_prs.std(ddof=1))
            percentile = float(100.0 * np.mean(sim_prs < prs_indiv))
            zscore = float((prs_indiv - sim_mean) / sim_sd) if sim_sd > 0 else np.nan
            sim_used = int(sim_sub.shape[0])
        
        # Absolute probability
        prev_val = None
        if trait in prevalences and prevalences[trait] is not None:
            val = prevalences[trait]
            if isinstance(val, dict):
                found = None
                for loc_k, years_v in val.items():
                    if isinstance(years_v, dict):
                        for y_k, y_v in years_v.items():
                            if y_v is not None:
                                try:
                                    found = float(y_v)
                                    break
                                except:
                                    continue
                        if found is not None:
                            break
                    else:
                        try:
                            found = float(years_v)
                            break
                        except:
                            continue
                prev_val = found
            else:
                try:
                    prev_val = float(val)
                except:
                    prev_val = None
        
        absolute_prob = np.nan
        if prev_val is not None and not math.isnan(prev_val) and 0 < prev_val < 1:
            baseline_odds = prev_val / (1 - prev_val)
            rel_odds = math.exp(prs_indiv)
            post_odds = baseline_odds * rel_odds
            absolute_prob = float(post_odds / (1 + post_odds))
        
        # Confidence
        confidence = "high"
        reasons = []
        if n_snps < 5:
            reasons.append("few_snps")
            confidence = "low"
        if sim_used < max(3, int(0.5 * n_snps)):
            reasons.append("few_sim_snps")
            if confidence != "low":
                confidence = "medium"
        if prev_val is None:
            reasons.append("no_prevalence")
            if confidence == "high":
                confidence = "medium"
        
        # Interpretation
        interpretation = "unknown"
        if not math.isnan(absolute_prob):
            if absolute_prob >= ABS_PROB_HIGH:
                interpretation = "high_absolute_risk"
            elif absolute_prob >= ABS_PROB_MODERATE:
                interpretation = "moderate_absolute_risk"
            else:
                interpretation = "low_absolute_risk"
        else:
            if not math.isnan(percentile):
                if percentile >= PERCENTILE_HIGH:
                    interpretation = "high_percentile_risk"
                elif percentile >= PERCENTILE_MODERATE:
                    interpretation = "moderate_percentile_risk"
                else:
                    interpretation = "low_percentile_risk"
        
        results.append({
            "trait": trait,
            "n_SNPs": n_snps,
            "n_with_genotype": n_with_geno,
            "n_sim_used": sim_used,
            "PRS_indiv": prs_indiv,
            "sim_mean": sim_mean,
            "sim_sd": sim_sd,
            "percentile": percentile,
            "zscore": zscore,
            "prevalence_used": prev_val,
            "absolute_probability": absolute_prob,
            "interpretation": interpretation,
            "confidence": confidence,
            "confidence_reasons": ";".join(reasons)
        })
    
    res_df = pd.DataFrame(results)
    
    # Filter to disease-like traits
    res_df['is_disease_like'] = res_df['trait'].apply(lambda x: trait_is_disease(x))
    disease_df = res_df[res_df['is_disease_like']].copy().sort_values(
        by='absolute_probability', ascending=False, na_position='last'
    )
    
    disease_df.to_csv(output_path, index=False)
    return output_path

