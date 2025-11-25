"""
Ingredient Extraction Module
Wrapper for IngredientExtraction functionality
"""

import json
import os
import csv
from collections import defaultdict, Counter
from pathlib import Path

def norm_food(s):
    if not s:
        return ""
    return str(s).strip().lower()

def interpret_association(assoc_str):
    s = str(assoc_str).strip().lower()
    if s == "positive":
        return "prefer"
    if s == "negative":
        return "avoid"
    return "neutral"

def process_dataset(path):
    with open(path, "r", encoding="utf-8") as f:
        arr = json.load(f)
    
    per_disease = {}
    aggregate = defaultdict(list)
    
    for rec in arr:
        trait = rec.get("trait") or ""
        trait_key = trait.strip().lower()
        result = rec.get("result") or {}
        fd_list = result.get("foodDiseases") or []
        per_map = {}
        
        for fd in fd_list:
            food = fd.get("food-term") or fd.get("food_term") or ""
            food_norm = norm_food(food)
            if not food_norm:
                continue
            assoc = fd.get("association")
            pmid = fd.get("pmid")
            sentence = fd.get("sentence")
            action = interpret_association(assoc)
            
            evidence = {
                "food_term": food,
                "association": assoc,
                "pmid": pmid,
                "sentence": sentence,
                "action": action
            }
            
            per_map.setdefault(food_norm, []).append(evidence)
            aggregate[food_norm].append({
                "disease": trait_key,
                "evidence": evidence
            })
        
        per_disease[trait_key] = per_map
    
    return per_disease, aggregate

def collapse_per_disease(per_disease):
    out = {}
    for disease, fmap in per_disease.items():
        out[disease] = {}
        for food, evs in fmap.items():
            actions = [e["action"] for e in evs]
            if "avoid" in actions:
                act = "avoid"
            elif "prefer" in actions:
                act = "prefer"
            else:
                act = "neutral"
            out[disease][food] = {
                "action": act,
                "evidences": evs
            }
    return out

def aggregate_across_diseases(collapsed_map):
    ing_reasons = defaultdict(list)
    for disease, fmap in collapsed_map.items():
        for food, info in fmap.items():
            ing_reasons[food].append({
                "disease": disease,
                "action": info["action"],
                "evidence_count": len(info["evidences"]),
                "evidences": info["evidences"]
            })
    
    final = {}
    for food, reasons in ing_reasons.items():
        acts = [r["action"] for r in reasons]
        if "avoid" in acts:
            final_action = "avoid"
        elif "prefer" in acts:
            final_action = "prefer"
        else:
            final_action = "neutral"
        final[food] = {
            "final_action": final_action,
            "reasons": reasons,
            "counts": dict(Counter(acts))
        }
    return final

def extract_ingredients(disease_json_path, user_folder, analysis_id):
    """Extract ingredient recommendations from disease JSON"""
    
    input_json = Path(disease_json_path)
    output_json = user_folder / f"ingredient_recommendations_{analysis_id}.json"
    output_csv = user_folder / f"ingredient_recommendations_{analysis_id}.csv"
    
    if not input_json.exists():
        raise FileNotFoundError(f"Input file not found: {input_json}")
    
    per_raw, agg = process_dataset(str(input_json))
    per_coll = collapse_per_disease(per_raw)
    final_map = aggregate_across_diseases(per_coll)
    
    # Combined JSON
    combined = {
        "per_disease": per_coll,
        "ingredient_recommendations": final_map
    }
    
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)
    
    # CSV
    with open(output_csv, "w", newline="", encoding="utf-8") as csvf:
        writer = csv.writer(csvf)
        writer.writerow([
            "ingredient", "final_action", "avoid_count", "prefer_count", "neutral_count",
            "example_disease", "example_action", "example_pmid", "example_sentence"
        ])
        for food, meta in sorted(final_map.items()):
            cnt = meta["counts"]
            reasons = meta["reasons"]
            ex = reasons[0] if reasons else {}
            ex_e = ex.get("evidences", [{}])[0]
            writer.writerow([
                food,
                meta["final_action"],
                cnt.get("avoid", 0),
                cnt.get("prefer", 0),
                cnt.get("neutral", 0),
                ex.get("disease", ""),
                ex.get("action", ""),
                ex_e.get("pmid", ""),
                (ex_e.get("sentence") or "")[:200].replace("\n", " ")
            ])
    
    return output_json

