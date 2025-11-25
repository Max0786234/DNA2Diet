#base file with no nlp


import pandas as pd
import re
import requests
from thefuzz import fuzz, process
import aiohttp
import asyncio
import json
from pathlib import Path
from tqdm import tqdm
import time

# -----------------
# 1. Load Genome File
# -----------------
genome_file = "genome_George_Church_Full_20091107080045.txt"

genome = pd.read_csv(
    genome_file,
    sep="\t",
    comment="#",
    names=["rsid", "chromosome", "position", "genotype"],
    dtype=str,
    engine="python",
    on_bad_lines="skip"
)

print(f"Genome loaded: {len(genome)} SNPs")

# -----------------
# 2. Load GWAS Catalog
# -----------------
gwas_file = "gwas_catalog_v1.0.2-associations_e114_r2025-07-21.tsv"
gwas = pd.read_csv(gwas_file, sep="\t", dtype=str)
print(f"GWAS loaded: {len(gwas)} associations")

# -----------------
# 3. Nutrition-related Keywords
# -----------------
keywords = [
    "nutrition", "nutrient", "diet", "metabolism", "obesity", "BMI",
    "lipid", "cholesterol", "glucose", "insulin", "diabetes",
    "vitamin", "iron", "calcium", "magnesium", "zinc", "selenium",
    "caffeine", "alcohol", "lactose", "dairy", "protein",
    "fatty acid", "omega-3", "omega-6", "PUFA", "fiber",
    "gut microbiome", "hypertension", "blood pressure"
]

pattern = "|".join(re.escape(k) for k in keywords)

# Direct keyword filter on MAPPED_TRAIT
nutri_gwas = gwas[gwas["MAPPED_TRAIT"].str.contains(pattern, case=False, na=False, regex=True)]

# -----------------
# 4. Fuzzy Matching to expand results
# -----------------
all_traits = gwas["MAPPED_TRAIT"].dropna().unique()
matched_traits = set(nutri_gwas["MAPPED_TRAIT"].unique())

for kw in keywords:
    close_matches = process.extract(kw, all_traits, scorer=fuzz.partial_ratio, limit=20)
    for trait, score in close_matches:
        if score >= 85:
            matched_traits.add(trait)

nutri_gwas = gwas[gwas["MAPPED_TRAIT"].isin(matched_traits)]
print(f"Nutritionally relevant traits found: {len(nutri_gwas)}")

# -----------------
# 5. Match Genome with Nutritional GWAS
# -----------------
merged = genome.merge(nutri_gwas, left_on="rsid", right_on="SNPS", how="inner")
print(f"Matched SNPs: {len(merged)}")

# -----------------
# 6. Keep only useful columns
# -----------------
final_cols = [
    "rsid", "chromosome", "position", "genotype",
    "MAPPED_TRAIT", "MAPPED_TRAIT_URI",
    "REPORTED GENE(S)", "MAPPED_GENE",
    "STRONGEST SNP-RISK ALLELE", "SNPS",
    "RISK ALLELE FREQUENCY", "P-VALUE", "OR or BETA"
]
merged = merged[final_cols]

# -----------------
# 7. MeSH Mapping (async + cache)
# -----------------
API_URL = "https://id.nlm.nih.gov/mesh/lookup/descriptor"
CACHE_FILE = Path("mesh_cache.json")

# Load cache
if CACHE_FILE.exists():
    with open(CACHE_FILE, "r") as f:
        cache = json.load(f)
else:
    cache = {}

traits_to_map = list(merged["MAPPED_TRAIT"].dropna().unique())
print(f"🔎 Mapping {len(traits_to_map)} traits to MeSH IDs (with cache)...")

async def fetch_mesh(session, trait, retries=2):
    if trait in cache:
        return trait, cache[trait]["MESH_ID"], cache[trait]["MESH_TERM"]

    for attempt in range(retries):
        try:
            # Exact match
            async with session.get(API_URL, params={"label": trait, "match": "exact"}) as r:
                if r.status == 200:
                    data = await r.json()
                    if data:
                        mesh_id = data[0]["resource"].split("/")[-1]
                        mesh_term = trait
                        cache[trait] = {"MESH_ID": mesh_id, "MESH_TERM": mesh_term}
                        return trait, mesh_id, mesh_term

            # Contains match
            async with session.get(API_URL, params={"label": trait, "match": "contains"}) as r:
                if r.status == 200:
                    data = await r.json()
                    if data:
                        mesh_id = data[0]["resource"].split("/")[-1]
                        mesh_term = data[0]["label"]
                        cache[trait] = {"MESH_ID": mesh_id, "MESH_TERM": mesh_term}
                        return trait, mesh_id, mesh_term

        except Exception:
            if attempt < retries - 1:
                await asyncio.sleep(1.5)
            else:
                return trait, None, None

    return trait, None, None

async def run_mapping(traits):
    results = []
    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_mesh(session, t) for t in traits]
        for future in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
            results.append(await future)
            await asyncio.sleep(0.2)  # gentle rate limit (~5 req/s)
    return results

results = asyncio.run(run_mapping(traits_to_map))

# Save cache
with open(CACHE_FILE, "w") as f:
    json.dump(cache, f)

mesh_map = pd.DataFrame(results, columns=["MAPPED_TRAIT", "MESH_ID", "MESH_TERM"])

# -----------------
# 8. Merge MeSH IDs back
# -----------------
merged = merged.merge(mesh_map, on="MAPPED_TRAIT", how="left")

# -----------------
# 9. Save Results
# -----------------
out_file = "nutritional_snps_with_mesh.csv"
merged.to_csv(out_file, index=False)
print(f"💾 Results saved to {out_file}")
print(merged.head())