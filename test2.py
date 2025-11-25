# nlp implemented and getting 3 files
# one is all snp with and without meshID
# one is all traits for which nlp was used (for testing)
# one is the final file with the traits with meshID

import pandas as pd
import re
import requests
from thefuzz import fuzz, process
import aiohttp
import asyncio
import json
from pathlib import Path
from tqdm import tqdm
import spacy
from concurrent.futures import ThreadPoolExecutor, as_completed

# -----------------
# Configuration
# -----------------
GENOME_FILE = "genome_George_Church_Full_20091107080045.txt"
GWAS_FILE = "gwas_catalog_v1.0.2-associations_e114_r2025-07-21.tsv"
CACHE_FILE = Path("mesh_cache.json")
NLP_CACHE_FILE = Path("nlp_cache.json")
OUTPUT_ALL = "nutritional_snps_with_mesh_all.csv"
OUTPUT_FOUND = "nutritional_snps_final.csv"
OUTPUT_NLP_TRAITS = "traits_nlp_fallback.csv"

API_URL = "https://id.nlm.nih.gov/mesh/lookup/descriptor"

# -----------------
# Load MeSH Cache
# -----------------
if CACHE_FILE.exists():
    with open(CACHE_FILE, "r") as f:
        mesh_cache = json.load(f)
else:
    mesh_cache = {}

# -----------------
# Load NLP Cache
# -----------------
if NLP_CACHE_FILE.exists():
    with open(NLP_CACHE_FILE, "r") as f:
        nlp_cache = json.load(f)
else:
    nlp_cache = {}

# -----------------
# Load NLP Model
# -----------------
nlp = spacy.load("en_core_sci_sm")

# -----------------
# Nutrition Keywords
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

# -----------------
# Async MeSH mapping
# -----------------
async def fetch_mesh(session, trait, retries=2):
    if trait in mesh_cache:
        return trait, mesh_cache[trait]["MESH_ID"], mesh_cache[trait]["MESH_TERM"]

    for attempt in range(retries):
        try:
            async with session.get(API_URL, params={"label": trait, "match": "exact"}) as r:
                if r.status == 200:
                    data = await r.json()
                    if data:
                        mesh_id = data[0]["resource"].split("/")[-1]
                        mesh_cache[trait] = {"MESH_ID": mesh_id, "MESH_TERM": trait}
                        return trait, mesh_id, trait
            async with session.get(API_URL, params={"label": trait, "match": "contains"}) as r:
                if r.status == 200:
                    data = await r.json()
                    if data:
                        mesh_id = data[0]["resource"].split("/")[-1]
                        mesh_cache[trait] = {"MESH_ID": mesh_id, "MESH_TERM": data[0]["label"]}
                        return trait, mesh_id, data[0]["label"]
        except:
            if attempt < retries - 1:
                await asyncio.sleep(1)
            else:
                return trait, None, None
    return trait, None, None

async def run_mesh_mapping(traits):
    results = []
    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_mesh(session, t) for t in traits]
        for future in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="MeSH Mapping"):
            results.append(await future)
            await asyncio.sleep(0.1)
    return results

# -----------------
# NLP Fallback
# -----------------
def process_trait_thread(trait):
    if trait in nlp_cache:
        return trait, nlp_cache[trait][0], nlp_cache[trait][1]

    doc = nlp(trait)
    extracted_term = doc.ents[0].text if doc.ents else (list(doc.noun_chunks)[0].text if list(doc.noun_chunks) else trait)

    mesh_id = None
    try:
        r = requests.get(API_URL, params={"label": extracted_term, "match": "exact"})
        if r.status_code == 200:
            data = r.json()
            if data:
                mesh_id = data[0]["resource"].split("/")[-1]
            else:
                r2 = requests.get(API_URL, params={"label": extracted_term, "match": "contains"})
                if r2.status_code == 200:
                    data2 = r2.json()
                    if data2:
                        mesh_id = data2[0]["resource"].split("/")[-1]
    except:
        pass

    nlp_cache[trait] = [extracted_term, mesh_id]
    return trait, extracted_term, mesh_id

def main():
    # -----------------
    # Load Genome + GWAS
    # -----------------
    genome = pd.read_csv(
        GENOME_FILE,
        sep="\t",
        comment="#",
        names=["rsid", "chromosome", "position", "genotype"],
        dtype=str,
        engine="python",
        on_bad_lines="skip"
    )
    print(f"Genome loaded: {len(genome)} SNPs")

    gwas = pd.read_csv(GWAS_FILE, sep="\t", dtype=str)
    print(f"GWAS loaded: {len(gwas)} associations")

    # -----------------
    # Filter nutritional traits
    # -----------------
    nutri_gwas = gwas[gwas["MAPPED_TRAIT"].str.contains(pattern, case=False, na=False, regex=True)]

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
    # Merge with genome
    # -----------------
    merged = genome.merge(nutri_gwas, left_on="rsid", right_on="SNPS", how="inner")
    final_cols = [
        "rsid", "chromosome", "position", "genotype",
        "MAPPED_TRAIT", "MAPPED_TRAIT_URI",
        "REPORTED GENE(S)", "MAPPED_GENE",
        "STRONGEST SNP-RISK ALLELE", "SNPS",
        "RISK ALLELE FREQUENCY", "P-VALUE", "OR or BETA"
    ]
    merged = merged[final_cols]
    print(f"Matched SNPs: {len(merged)}")

    # -----------------
    # Map MeSH IDs
    # -----------------
    traits_to_map = list(merged["MAPPED_TRAIT"].dropna().unique())
    results_mesh = asyncio.run(run_mesh_mapping(traits_to_map))

    # Save cache
    with open(CACHE_FILE, "w") as f:
        json.dump(mesh_cache, f)

    mesh_map = pd.DataFrame(results_mesh, columns=["MAPPED_TRAIT", "MESH_ID", "MESH_TERM"])
    merged = merged.merge(mesh_map, on="MAPPED_TRAIT", how="left")

    # -----------------
    # NLP fallback for missing MeSH
    # -----------------
    traits_to_process = merged.loc[merged["MESH_ID"].isna(), "MAPPED_TRAIT"].dropna().unique()
    print(f"➡ Traits needing NLP fallback: {len(traits_to_process)}")

    results_nlp = []
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(process_trait_thread, t) for t in traits_to_process]
        for f in tqdm(as_completed(futures), total=len(futures), desc="NLP Fallback"):
            results_nlp.append(f.result())

    # Update merged table with NLP results
    nlp_df = pd.DataFrame(results_nlp, columns=["MAPPED_TRAIT", "NLP_TERM", "NLP_MESH_ID"])
    merged = merged.merge(nlp_df, on="MAPPED_TRAIT", how="left")

    # Remove traits still not found in MeSH after NLP
    merged_found = merged[merged["NLP_MESH_ID"].notna() | merged["MESH_ID"].notna()]
    merged_all = merged.copy()

    # -----------------
    # Save results
    # -----------------
    merged_all.to_csv(OUTPUT_ALL, index=False)
    merged_found.to_csv(OUTPUT_FOUND, index=False)
    nlp_df.to_csv(OUTPUT_NLP_TRAITS, index=False)

    # Save NLP cache
    with open(NLP_CACHE_FILE, "w") as f:
        json.dump(nlp_cache, f)

    print(f"All SNPs saved to {OUTPUT_ALL}")
    print(f"SNPs with MeSH/NLP found saved to {OUTPUT_FOUND}")
    print(f"Traits processed via NLP saved to {OUTPUT_NLP_TRAITS}")

if __name__ == "__main__":
    main()