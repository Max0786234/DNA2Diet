"""
MESH Processing Module
Wrapper for mesh.py functionality
"""

import requests
import json
import os
import time
from pathlib import Path

BASE_URL = "http://192.168.1.92:8002/api/disease/"  # Update if your API is different
PARAMS = {
    "limit": 10,
    "page": 1,
    "lastPMID": ""
}
HEADERS = {}

def safe_filename(name):
    """Generate safe filename for each disease."""
    return "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name).strip().replace(" ", "_")

def load_diseases(path):
    """Load selected diseases list from JSON."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    traits = [d["trait"] for d in data if d.get("trait")]
    return traits

def fetch_disease_details(name):
    """Fetch disease details via API call."""
    url = f"{BASE_URL}{name}"
    try:
        response = requests.get(url, params=PARAMS, headers=HEADERS, timeout=10)  # Reduced timeout
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            print(f"⚠️  Not found: {name}")
        else:
            print(f"❌ Failed {name}: {response.status_code}")
    except requests.exceptions.Timeout:
        print(f"⚠️  Timeout fetching {name} - skipping")
        return None
    except Exception as e:
        print(f"⚠️  Error fetching {name}: {e}")
    return None

def process_mesh(selected_diseases_path, user_folder, analysis_id):
    """Process MESH data for diseases"""
    
    input_file = Path(selected_diseases_path)
    output_dir = user_folder / f"disease_details_{analysis_id}"
    output_dir.mkdir(exist_ok=True)
    combined_output = user_folder / f"disease_{analysis_id}.json"
    
    diseases = load_diseases(input_file)
    all_results = []
    
    # Limit to top 10 diseases for faster processing
    diseases_limited = diseases[:10] if len(diseases) > 10 else diseases
    
    for i, disease in enumerate(diseases_limited, start=1):
        print(f"[{i}/{len(diseases_limited)}] Fetching: {disease}")
        data = fetch_disease_details(disease)
        if data:
            fname = safe_filename(disease) + ".json"
            fpath = output_dir / fname
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            all_results.append({
                "trait": disease,
                "result": data
            })
        time.sleep(0.05)  # Reduced delay for faster processing
    
    # Save combined output
    with open(combined_output, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=4, ensure_ascii=False)
    
    return combined_output

