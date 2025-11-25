"""
Genome Processing Module
Wrapper for test3.py functionality
"""

import sys
import os
from pathlib import Path
import pandas as pd
import re
import requests
from thefuzz import fuzz, process
import aiohttp
import asyncio
import json
from tqdm import tqdm
import spacy
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path to access GWAS file
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configuration
GWAS_FILE = Path(__file__).parent.parent / "gwas.tsv"
API_URL = "https://id.nlm.nih.gov/mesh/lookup/descriptor"

# Load NLP Model
try:
    nlp = spacy.load("en_core_sci_sm")
except:
    print("Info: scispacy model not found. NLP fallback disabled - using direct MeSH API lookups instead.")
    print("     (This is fine - core functionality works without the model)")
    print("     To enable NLP: pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.3/en_core_sci_sm-0.5.3.tar.gz")
    nlp = None

# Nutrition Keywords
keywords = [
    "nutrition", "nutrient", "diet", "metabolism", "obesity", "BMI",
    "lipid", "cholesterol", "glucose", "insulin", "diabetes",
    "vitamin", "iron", "calcium", "magnesium", "zinc", "selenium",
    "caffeine", "alcohol", "lactose", "dairy", "protein",
    "fatty acid", "omega-3", "omega-6", "PUFA", "fiber",
    "gut microbiome", "hypertension", "blood pressure"
]
pattern = "|".join(re.escape(k) for k in keywords)

async def fetch_mesh(session, trait, cache, retries=2):
    if trait in cache:
        return trait, cache[trait]["MESH_ID"], cache[trait]["MESH_TERM"]
    
    for attempt in range(retries):
        try:
            async with session.get(API_URL, params={"label": trait, "match": "exact"}) as r:
                if r.status == 200:
                    data = await r.json()
                    if data:
                        mesh_id = data[0]["resource"].split("/")[-1]
                        cache[trait] = {"MESH_ID": mesh_id, "MESH_TERM": trait}
                        return trait, mesh_id, trait
            
            async with session.get(API_URL, params={"label": trait, "match": "contains"}) as r:
                if r.status == 200:
                    data = await r.json()
                    if data:
                        mesh_id = data[0]["resource"].split("/")[-1]
                        cache[trait] = {"MESH_ID": mesh_id, "MESH_TERM": data[0]["label"]}
                        return trait, mesh_id, data[0]["label"]
        except:
            if attempt < retries - 1:
                await asyncio.sleep(1)
            else:
                return trait, None, None
    return trait, None, None

async def run_mesh_mapping(traits, cache, progress_callback=None):
    results = []
    connector = aiohttp.TCPConnector(limit=30)
    total = max(len(traits), 1)
    processed = 0
    last_reported = 0
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_mesh(session, t, cache) for t in traits]
        for future in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="MeSH Mapping"):
            result = await future
            results.append(result)
            processed += 1
            if progress_callback:
                pct = 10 + int((processed / total) * 10)
                pct = min(25, pct)
                if pct > last_reported:
                    last_reported = pct
                    progress_callback(f"Mapping traits to MeSH ({processed}/{total})", pct)
    return results

def process_trait_thread(trait, nlp_cache):
    if trait in nlp_cache:
        return trait, nlp_cache[trait][0], nlp_cache[trait][1]
    
    if nlp is None:
        return trait, trait, None
    
    doc = nlp(trait)
    extracted_term = doc.ents[0].text if doc.ents else (
        list(doc.noun_chunks)[0].text if list(doc.noun_chunks) else trait
    )
    
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

def process_genome_file(genome_filepath, user_folder, analysis_id, progress_callback=None):
    """Process genome file and return path to nutritional_snp_final.csv"""
    
    # Create cache files for this user
    cache_file = user_folder / f"mesh_cache_{analysis_id}.json"
    nlp_cache_file = user_folder / f"nlp_cache_{analysis_id}.json"
    output_file = user_folder / f"nutritional_snp_final_{analysis_id}.csv"
    
    # Load caches
    if cache_file.exists():
        with open(cache_file, "r") as f:
            mesh_cache = json.load(f)
    else:
        mesh_cache = {}
    
    if nlp_cache_file.exists():
        with open(nlp_cache_file, "r") as f:
            nlp_cache = json.load(f)
    else:
        nlp_cache = {}
    
    # Load genome
    genome = pd.read_csv(
        genome_filepath,
        sep="\t",
        comment="#",
        names=["rsid", "chromosome", "position", "genotype"],
        dtype=str,
        engine="python",
        on_bad_lines="skip"
    )
    if progress_callback:
        progress_callback("Genome file loaded", 12)
    
    # Load GWAS
    gwas = pd.read_csv(GWAS_FILE, sep="\t", dtype=str)
    if progress_callback:
        progress_callback("GWAS data loaded", 14)
    
    # Filter nutritional traits
    nutri_gwas = gwas[gwas["MAPPED_TRAIT"].str.contains(pattern, case=False, na=False, regex=True)]
    
    all_traits = gwas["MAPPED_TRAIT"].dropna().unique()
    matched_traits = set(nutri_gwas["MAPPED_TRAIT"].unique())
    
    for kw in keywords:
        close_matches = process.extract(kw, all_traits, scorer=fuzz.partial_ratio, limit=20)
        for trait, score in close_matches:
            if score >= 85:
                matched_traits.add(trait)
    
    nutri_gwas = gwas[gwas["MAPPED_TRAIT"].isin(matched_traits)]
    if progress_callback:
        progress_callback("Filtered nutritional traits", 16)
    
    # Merge
    merged = genome.merge(nutri_gwas, left_on="rsid", right_on="SNPS", how="inner")
    if progress_callback:
        progress_callback("Merged genome with traits", 18)
    final_cols = [
        "rsid", "chromosome", "position", "genotype",
        "MAPPED_TRAIT", "MAPPED_TRAIT_URI",
        "REPORTED GENE(S)", "MAPPED_GENE",
        "STRONGEST SNP-RISK ALLELE", "SNPS",
        "RISK ALLELE FREQUENCY", "P-VALUE", "OR or BETA"
    ]
    merged = merged[final_cols]
    
    # Map MeSH IDs
    traits_to_map = list(merged["MAPPED_TRAIT"].dropna().unique())
    results_mesh = asyncio.run(run_mesh_mapping(traits_to_map, mesh_cache, progress_callback))
    
    # Save cache
    with open(cache_file, "w") as f:
        json.dump(mesh_cache, f)
    
    mesh_map = pd.DataFrame(results_mesh, columns=["MAPPED_TRAIT", "MESH_ID", "MESH_TERM"])
    merged = merged.merge(mesh_map, on="MAPPED_TRAIT", how="left")
    
    # NLP fallback
    traits_to_process = merged.loc[merged["MESH_ID"].isna(), "MAPPED_TRAIT"].dropna().unique()
    if progress_callback:
        progress_callback("Running NLP fallback for unmapped traits", 23)
    
    if nlp is not None:
        results_nlp = []
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(process_trait_thread, t, nlp_cache) for t in traits_to_process]
            for f in tqdm(as_completed(futures), total=len(futures), desc="NLP Fallback"):
                results_nlp.append(f.result())
        
        nlp_df = pd.DataFrame(results_nlp, columns=["MAPPED_TRAIT", "NLP_TERM", "NLP_MESH_ID"])
        merged = merged.merge(nlp_df, on="MAPPED_TRAIT", how="left")
        
        # Replace missing MeSH ID with NLP results
        merged["MESH_ID"] = merged.apply(
            lambda row: row["MESH_ID"] if pd.notna(row["MESH_ID"]) else row["NLP_MESH_ID"],
            axis=1
        )
        merged["MESH_TERM"] = merged.apply(
            lambda row: row["MESH_TERM"] if pd.notna(row["MESH_TERM"]) else row["NLP_TERM"],
            axis=1
        )
        
        merged.drop(columns=["NLP_TERM", "NLP_MESH_ID"], inplace=True)
        
        # Save NLP cache
        with open(nlp_cache_file, "w") as f:
            json.dump(nlp_cache, f)
    
    # Final output (only SNPs with MeSH ID)
    merged_found = merged[merged["MESH_ID"].notna()]
    merged_found.to_csv(output_file, index=False)
    if progress_callback:
        progress_callback("Genome processing completed", 30)
    
    return output_file

