"""
Disease Finalization Module
Wrapper for disease_final.py functionality
"""

import os
import json
import pandas as pd
import numpy as np
from pathlib import Path

INTERPRET_KEEP = {
    "high_absolute_risk", "high_percentile_risk",
    "moderate_absolute_risk", "moderate_percentile_risk"
}
PERCENTILE_MIN = 75.0
ABS_PROB_MIN = 0.05
TOP_SNPS = 5

def to_float(x):
    try:
        return float(x)
    except:
        return np.nan

def load_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return pd.read_csv(path, dtype=str)

def finalize_diseases(disease_candidates_path, nutritional_snp_path, user_folder, analysis_id):
    """Finalize and rank diseases"""
    
    input_diseases = Path(disease_candidates_path)
    input_orig = Path(nutritional_snp_path)
    output_csv = user_folder / f"selected_diseases_ranked_{analysis_id}.csv"
    output_json = user_folder / f"selected_diseases_ranked_{analysis_id}.json"
    
    # Load disease candidates
    df = load_csv(input_diseases)
    
    for col in ["percentile", "absolute_probability"]:
        df[col] = df[col].apply(to_float)
    
    df['interpretation'] = df['interpretation'].astype(str)
    
    # Filter
    mask = (
        df['interpretation'].str.lower().isin({s.lower() for s in INTERPRET_KEEP})
        | (df['percentile'].fillna(-1) >= PERCENTILE_MIN)
        | (df['absolute_probability'].fillna(0) >= ABS_PROB_MIN)
    )
    selected = df[mask].copy().reset_index(drop=True)
    
    # Load original SNP data
    orig = load_csv(input_orig)
    
    trait_col = "MESH_TERM" if "MESH_TERM" in orig.columns else "MAPPED_TRAIT"
    mesh_col = "MESH_ID" if "MESH_ID" in orig.columns else None
    
    out = []
    for _, r in selected.iterrows():
        trait = r["trait"]
        
        sub = orig[(orig.get(trait_col, "") == trait) | (orig.get("MAPPED_TRAIT", "") == trait)]
        sub = sub.drop_duplicates(subset=["rsid"]) if "rsid" in sub.columns else sub
        
        top_snps = []
        if not sub.empty:
            effcol = next((c for c in ["OR or BETA", "OR", "BETA"] if c in sub.columns), None)
            
            if effcol:
                sub["effabs"] = pd.to_numeric(sub[effcol], errors="coerce").abs()
                sub = sub.sort_values("effabs", ascending=False).head(TOP_SNPS)
            
            for _, s in sub.iterrows():
                top_snps.append({
                    "rsid": s.get("rsid"),
                    "genotype": s.get("genotype"),
                    "risk_allele": s.get("STRONGEST SNP-RISK ALLELE"),
                    "effect_raw": s.get(effcol),
                    "mapped_gene": s.get("MAPPED_GENE") or s.get("REPORTED GENE(S)")
                })
        
        mesh = sub[mesh_col].dropna().unique()[0] if mesh_col and not sub.empty else None
        
        out.append({
            "trait": trait,
            "mesh_id": mesh,
            "percentile": r["percentile"],
            "absolute_probability": r["absolute_probability"],
            "interpretation": r["interpretation"],
            "confidence": r.get("confidence"),
            "prevalence_used": r.get("prevalence_used"),
            "top_snps": top_snps
        })
    
    df_out = pd.DataFrame(out)
    
    # Score and rank
    def score_row(r):
        p = r.get("percentile")
        ap = r.get("absolute_probability")
        if pd.isna(p):
            p = 50
        if pd.isna(ap):
            ap = 0
        return (p - 50) / 10 + 10 * ap
    
    df_out["risk_score"] = df_out.apply(score_row, axis=1)
    df_out = df_out.sort_values("risk_score", ascending=False).reset_index(drop=True)
    df_out["rank"] = np.arange(1, len(df_out) + 1)
    
    # SNP summary
    def snp_summary(lst):
        if not lst:
            return ""
        return "; ".join([
            f"{x['rsid']}({x['genotype']},{x['risk_allele']},e={x['effect_raw']})"
            for x in lst
        ])
    
    df_out["top_snps_summary"] = df_out["top_snps"].apply(snp_summary)
    
    # Save
    df_out.to_csv(output_csv, index=False)
    
    # Convert top_snps to JSON-serializable format
    records = df_out.to_dict(orient="records")
    with open(output_json, "w") as f:
        json.dump(records, f, indent=2)
    
    return output_json
