import requests
import json
import os
import time

# ---------------- USER CONFIG ----------------
BASE_URL = "http://192.168.1.92:8002/api/disease/"  # your working API
INPUT_FILE = "./selected_diseases_ranked.json"      # file containing diseases from your previous step
OUTPUT_DIR = "./disease_details"                    # folder for per-disease JSONs
COMBINED_OUTPUT = "./disease.json"     # combined output file

# Optional API params / headers
PARAMS = {
    "limit": 10,
    "page": 1,
    "lastPMID": ""
}
HEADERS = {
    # If your API doesn’t need authorization, leave this empty:
    # "Authorization": "Bearer YOUR_API_KEY"
}
# ------------------------------------------------


def safe_filename(name):
    """Generate safe filename for each disease."""
    return "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name).strip().replace(" ", "_")


def load_diseases(path):
    """Load selected diseases list from JSON."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    traits = [d["trait"] for d in data if d.get("trait")]
    print(f"✅ Loaded {len(traits)} diseases from {path}")
    return traits


def fetch_disease_details(name):
    """Fetch disease details via API call."""
    url = f"{BASE_URL}{name}"
    try:
        response = requests.get(url, params=PARAMS, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            print(f"⚠️  Not found: {name}")
        else:
            print(f"❌ Failed {name}: {response.status_code}")
    except Exception as e:
        print(f"⚠️  Error fetching {name}: {e}")
    return None


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_results = []

    diseases = load_diseases(INPUT_FILE)

    for i, disease in enumerate(diseases, start=1):
        print(f"\n[{i}/{len(diseases)}] Fetching: {disease}")
        data = fetch_disease_details(disease)
        if data:
            fname = safe_filename(disease) + ".json"
            fpath = os.path.join(OUTPUT_DIR, fname)
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"   ✅ Saved: {fpath}")
            all_results.append({
                "trait": disease,
                "result": data
            })
        time.sleep(0.5)  # polite delay between requests

    # Save combined output
    with open(COMBINED_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=4, ensure_ascii=False)
    print(f"\n📁 All data combined and saved to {COMBINED_OUTPUT}")


if __name__ == "__main__":
    main()
