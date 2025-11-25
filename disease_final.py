"""
select_and_rank_diseases.py

Goal:
- Pick diseases with high/moderate genetic risk from disease_candidates.csv
- Merge with SNP details from nutritional_snps_final.csv
- Compute a combined risk score and rank them
- Save outputs to CSV and JSON
"""

import os, json
import pandas as pd
import numpy as np

# ---------- USER CONFIG ----------
INPUT_DISEASES = "./disease_candidates.csv"   # input file: disease-level risk data
INPUT_ORIG = "./nutritional_snps_final.csv"   # input file: SNP-level data (effects, traits)
OUT_CSV = "./selected_diseases_ranked.csv"    # output ranked list as CSV
OUT_JSON = "./selected_diseases_ranked.json"  # output ranked list as JSON

# Only keep diseases with these "interpretation" labels (case-insensitive)
INTERPRET_KEEP = {
    "high_absolute_risk", "high_percentile_risk",
    "moderate_absolute_risk", "moderate_percentile_risk"
}
PERCENTILE_MIN = 75.0   # keep if risk percentile >= 75 (e.g. top 25%)
ABS_PROB_MIN = 0.05     # keep if absolute probability >= 0.05 (≥5%)
TOP_SNPS = 5            # keep top 5 SNPs contributing to risk
# ---------------------------------

def to_float(x):
    """Safely convert value to float; return NaN if fails (e.g. 'NA' or blank)."""
    try:
        return float(x)
    except:
        return np.nan

def load_csv(path):
    """Load a CSV file (error if missing). Keeps all columns as strings for safety."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return pd.read_csv(path, dtype=str)

def main():
    # ---------- Load and clean disease candidates ----------
    df = load_csv(INPUT_DISEASES)
    print(f"Loaded {len(df)} disease candidate rows")

    # convert numeric columns (percentile and abs prob) to floats
    # e.g. "80.5" → 80.5
    for col in ["percentile", "absolute_probability"]:
        df[col] = df[col].apply(to_float)

    # ensure interpretation is string for comparison
    df['interpretation'] = df['interpretation'].astype(str)

    # ---------- Filter: keep only high/moderate risk diseases ----------
    # Condition examples:
    #   interpretation = "high_absolute_risk" keep
    #   percentile = 78 (>=75) keep
    #   absolute_probability = 0.06 (>=0.05) keep
    mask = (
        df['interpretation'].str.lower().isin({s.lower() for s in INTERPRET_KEEP})
        | (df['percentile'].fillna(-1) >= PERCENTILE_MIN)
        | (df['absolute_probability'].fillna(0) >= ABS_PROB_MIN)
    )
    selected = df[mask].copy().reset_index(drop=True)
    print(f"Selected {len(selected)} high/moderate-risk diseases")

    # ---------- Merge each disease with SNP data ----------
    orig = load_csv(INPUT_ORIG)

    # choose which column in SNP file represents trait name (depends on file)
    trait_col = "MESH_TERM" if "MESH_TERM" in orig.columns else "MAPPED_TRAIT"
    # choose MeSH ID column if present
    mesh_col = "MESH_ID" if "MESH_ID" in orig.columns else None

    out = []
    for _, r in selected.iterrows():   # loop through each selected disease
        trait = r["trait"]             # e.g. "Type 2 diabetes"

        # find SNP rows matching this disease trait in SNP dataset
        sub = orig[(orig.get(trait_col, "") == trait) | (orig.get("MAPPED_TRAIT", "") == trait)]

        # remove duplicate SNPs if same rsid appears multiple times
        sub = sub.drop_duplicates(subset=["rsid"]) if "rsid" in sub.columns else sub

        top_snps = []
        if not sub.empty:
            # choose correct effect column (OR or BETA values)
            # e.g. OR = 1.3 → effect size showing risk strength
            effcol = next((c for c in ["OR or BETA", "OR", "BETA"] if c in sub.columns), None)

            if effcol:
                # compute absolute value of effect for ranking
                # e.g. OR = -1.5 → abs(OR) = 1.5
                sub["effabs"] = pd.to_numeric(sub[effcol], errors="coerce").abs()

                # take top 5 SNPs with largest absolute effect
                sub = sub.sort_values("effabs", ascending=False).head(TOP_SNPS)

            # build small dictionary of each top SNP's info
            for _, s in sub.iterrows():
                top_snps.append({
                    "rsid": s.get("rsid"),                              # e.g. rs12345
                    "genotype": s.get("genotype"),                      # e.g. "AA"
                    "risk_allele": s.get("STRONGEST SNP-RISK ALLELE"),  # e.g. "A"
                    "effect_raw": s.get(effcol),                        # raw OR/BETA value
                    "mapped_gene": s.get("MAPPED_GENE") or s.get("REPORTED GENE(S)")  # e.g. "TCF7L2"
                })

        # get MeSH ID (disease ontology code) if available
        mesh = sub[mesh_col].dropna().unique()[0] if mesh_col and not sub.empty else None

        # collect one summary record per disease
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

    # convert all disease summaries into a DataFrame
    df_out = pd.DataFrame(out)

    # ---------- Compute and rank risk score ----------
    def score_row(r):
        # Default missing percentile to 50 (average), missing abs prob to 0
        p = r.get("percentile")
        ap = r.get("absolute_probability")
        if pd.isna(p): p = 50
        if pd.isna(ap): ap = 0
        # risk_score formula mixes percentile + absolute risk
        # Example:
        #   percentile = 80, abs_prob = 0.10
        #   => score = (80-50)/10 + 10*0.10 = 3 + 1 = 4
        return (p - 50)/10 + 10 * ap

    # compute score per disease and sort descending (higher = riskier)
    df_out["risk_score"] = df_out.apply(score_row, axis=1)
    df_out = df_out.sort_values("risk_score", ascending=False).reset_index(drop=True)
    df_out["rank"] = np.arange(1, len(df_out) + 1)   # assign 1,2,3,...

    # ---------- Add short SNP summary string ----------
    def snp_summary(lst):
        if not lst: return ""
        # example output: "rs123(A/A,A,e=1.2); rs456(G/T,T,e=0.8)"
        return "; ".join([f"{x['rsid']}({x['genotype']},{x['risk_allele']},e={x['effect_raw']})" for x in lst])

    df_out["top_snps_summary"] = df_out["top_snps"].apply(snp_summary)

    # ---------- Save results ----------
    df_out.to_csv(OUT_CSV, index=False)     # save ranked diseases as CSV
    with open(OUT_JSON, "w") as f:
        json.dump(df_out.to_dict(orient="records"), f, indent=2)   # save as JSON list

    print(f"\n✅ Wrote {len(df_out)} ranked diseases to {OUT_CSV}")
    print("\nTop ranked preview:")
    print(df_out[["rank", "trait", "percentile", "absolute_probability", "risk_score"]].to_string(index=False))

# Run the main function when the script is executed directly
if _name_ == "_main_":
    main()