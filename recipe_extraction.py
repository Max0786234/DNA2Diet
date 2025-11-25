import requests
import json
import csv
import os
import time
import random


# -------------------------------------------------------------
# 1. LOAD POSITIVE INGREDIENTS
# -------------------------------------------------------------
ING_FILE = "ingredient_recommendations.json"

with open(ING_FILE, "r", encoding="utf-8") as f:
    ing_data = json.load(f)

positive_ings = set()

for ing_name, info in ing_data["ingredient_recommendations"].items():
    if info.get("final_action", "").lower().strip() == "prefer":
        positive_ings.add(ing_name.lower().strip())

print("Loaded positive ingredients:", positive_ings)


# -------------------------------------------------------------
# 2. CSV INITIALIZATION
# -------------------------------------------------------------
CSV_FILE = "recipe_recommendations.csv"

CSV_HEADER = [
    "recipe_id",
    "recipe_title",
    "url",
    "img_url",
    "region",
    "sub_region",
    "continent",
    "source",
    "servings",
    "calories",

    # Nutrition fields
    "energy_kcal",
    "carbohydrate_by_difference_g",
    "protein_g",
    "total_lipid_fat_g",

    # Time fields WITH UNITS
    "cook_time_min",
    "prep_time_min",
    "total_time_min",

    "processes",
    "vegan",
    "pescetarian",
    "ovo_vegetarian",
    "lacto_vegetarian",
    "ovo_lacto_vegetarian",
    "utensils",
    "calorie_partition",

    # Ingredient phrases list
    "ingredient_phrases",

    # JSON dumps
    "ingredients_json",
    "raw_json"
]


def init_csv():
    """Create CSV file with header if not exists."""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADER)
        print("📄 CSV file created with header.")
    else:
        print("📄 CSV file already exists, appending to it.")


# -------------------------------------------------------------
# 3. APPEND ONE FULL RECIPE TO CSV
# -------------------------------------------------------------
def append_to_csv(root):
    if not isinstance(root, dict):
        return

    recipe = root.get("recipe", {}) or {}
    ingredients = root.get("ingredients", []) or []

    # Ingredient phrases extraction
    ingredient_phrases = [ing.get("ingredient_phrase") for ing in ingredients]
    ingredient_phrases_json = json.dumps(ingredient_phrases, ensure_ascii=False)

    # Basic fields
    recipe_id = recipe.get("recipe_id")
    recipe_title = recipe.get("recipe_title")
    url = recipe.get("url")
    img_url = recipe.get("img_url")
    region = recipe.get("region")
    sub_region = recipe.get("sub_region")
    continent = recipe.get("continent")
    source = recipe.get("source")
    servings = recipe.get("servings")
    calories = recipe.get("calories")

    # Nutrition fields
    energy_kcal = recipe.get("energy (kcal)")
    carbs = recipe.get("carbohydrate, by difference (g)")
    protein = recipe.get("protein (g)")
    fat = recipe.get("total lipid (fat) (g)")

    # Time fields (treated as minutes)
    cook_time_min = recipe.get("cook_time")
    prep_time_min = recipe.get("prep_time")
    total_time_min = recipe.get("total_time")

    # Other fields
    processes = recipe.get("processes")
    vegan = recipe.get("vegan")
    pescetarian = recipe.get("pescetarian")
    ovo_vegetarian = recipe.get("ovo_vegetarian")
    lacto_vegetarian = recipe.get("lacto_vegetarian")
    ovo_lacto_vegetarian = recipe.get("ovo_lacto_vegetarian")
    utensils = recipe.get("utensils")
    calorie_partition = recipe.get("calorie_partition")

    # JSON fields
    ingredients_json = json.dumps(ingredients, ensure_ascii=False)
    raw_json = json.dumps(root, ensure_ascii=False)

    row = [
        recipe_id,
        recipe_title,
        url,
        img_url,
        region,
        sub_region,
        continent,
        source,
        servings,
        calories,

        energy_kcal,
        carbs,
        protein,
        fat,

        cook_time_min,
        prep_time_min,
        total_time_min,

        processes,
        vegan,
        pescetarian,
        ovo_vegetarian,
        lacto_vegetarian,
        ovo_lacto_vegetarian,
        utensils,
        calorie_partition,

        ingredient_phrases_json,

        ingredients_json,
        raw_json
    ]

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)


# -------------------------------------------------------------
# 4. BASIC SEARCH: get recipes list for an ingredient + page
# -------------------------------------------------------------
def fetch_page(ingredient, page, limit=10):
    """
    Call the ingredient search endpoint to get recipe list (basic info).
    We only need Recipe_id from here.
    """
    url = "http://192.168.1.92:3031/recipe2-api/recipebyingredient/by-ingredients-categories-title"

    params = {
        "includeIngredients": ingredient,
        "excludeIngredients": "",
        "includeCategories": "",
        "excludeCategories": "",
        "title": "",
        "page": page,
        "limit": limit
    }

    r = requests.get(url, params=params)
    print(f"🌐 [{ingredient}] Page {page} → Status {r.status_code}")

    if r.status_code != 200:
        print("❌ API error:", r.text)
        return []

    data = r.json()
    return data.get("data", [])


# -------------------------------------------------------------
# 5. FULL DETAILS: /search-recipe/{id}
# -------------------------------------------------------------
def fetch_full_recipe(recipe_id):
    """
    Call full details endpoint and return root JSON with recipe + ingredients.
    Handles both:
      { "recipe": {...}, "ingredients": [...] }
    or
      { "data": { "recipe": {...}, "ingredients": [...] } }
    """
    url = f"http://192.168.1.92:3031/recipe2-api/search-recipe/{recipe_id}"

    r = requests.get(url)
    print(f"    ↳ Fetching full details for {recipe_id} → {r.status_code}")

    if r.status_code != 200:
        print("      ❌ Full-recipe API error:", r.text)
        return None

    data = r.json()
    return data.get("data", data)


# -------------------------------------------------------------
# 6. DISCOVER VALID INGREDIENTS (ONLY CHECK PAGE 1)
# -------------------------------------------------------------
def discover_ingredient_pages():
    """
    Pre-check:
      - Check ONLY page 1 for each ingredient.
      - If no recipes → skip.
      - Do NOT fetch further pages here.
    Page counts will be discovered dynamically later.
    """
    ingredient_pages = {}
    max_page = {}

    for ing in sorted(positive_ings):
        print("\n" + "=" * 60)
        print(f"🔎 Pre-checking ingredient: {ing}")
        print("=" * 60)

        # Check ONLY Page 1
        page1 = fetch_page(ing, 1, limit=10)
        if not page1:
            print(f"⚠️ No recipes found at all for ingredient: {ing}. Skipping.")
            continue

        # Store only page 1 for now
        ingredient_pages[ing] = {1: page1}
        max_page[ing] = 1  # start with 1 page, will grow later

        print(f"✔ Ingredient '{ing}' is valid. Page 1 has {len(page1)} recipes.")

    return ingredient_pages, max_page


# -------------------------------------------------------------
# 7. DUMP ALL REMAINING RECIPES FOR LAST INGREDIENT
# -------------------------------------------------------------
def dump_all_for_ingredient(ing, ingredient_pages, max_page, recipe_ids_seen):
    """
    When only one ingredient is left with recipes, we fetch ALL remaining
    recipes for that ingredient (no randomness).

    We dynamically discover further pages until no more exist.
    """
    print("\n" + "#" * 60)
    print(f"🔥 Only one ingredient left: {ing}")
    print("👉 Fetching ALL remaining recipes for this ingredient...")
    print("#" * 60)

    p = 1
    while True:
        # Discover page if not already known
        if p not in ingredient_pages[ing]:
            page_data = fetch_page(ing, p, limit=10)
            if not page_data:
                break
            ingredient_pages[ing][p] = page_data
            max_page[ing] = max(max_page[ing], p)

        page_recipes = ingredient_pages[ing].get(p, [])
        if not page_recipes:
            break

        for r in page_recipes:
            rid = r.get("Recipe_id")
            if not rid or rid in recipe_ids_seen:
                continue

            recipe_ids_seen.add(rid)

            full_root = fetch_full_recipe(rid)
            if full_root:
                append_to_csv(full_root)
                title = full_root.get("recipe", {}).get("recipe_title")
                print(f"💾 Saved FULL recipe → {title} (ingredient: {ing}, page {p})")

            time.sleep(0.1)

        p += 1

    print(f"✅ Finished dumping all recipes for ingredient: {ing}")


# -------------------------------------------------------------
# 8. ROUND-ROBIN RANDOM SAMPLING ACROSS INGREDIENTS & PAGES
# -------------------------------------------------------------
def process_all_ingredients_round_robin(ingredient_pages, max_page, recipe_ids_seen):
    """
    Page-wise round-robin:

    - For page_index = 1, 2, 3, ...
        * Let live ingredients be those not exhausted.
        * If >1 live ingredients:
              - For each live ingredient:
                    - Dynamically make sure page_index exists (if any).
                    - If page has recipes, randomly choose 1–5 from that page,
                      fetch full details, save.
        * If exactly 1 live ingredient remains:
              - Dump ALL recipes for that ingredient (all pages, not random).
    """
    if not max_page:
        print("⚠️ No valid ingredients with recipes. Nothing to do.")
        return

    ingredients = sorted(ingredient_pages.keys())
    done_ings = set()
    page_index = 1

    while True:
        # Ingredients that are not marked done
        live_ings = [ing for ing in ingredients if ing not in done_ings]

        if not live_ings:
            # Nothing more to do
            break

        if len(live_ings) == 1:
            # Last ingredient → dump all remaining recipes (all pages)
            last_ing = live_ings[0]
            dump_all_for_ingredient(last_ing, ingredient_pages, max_page, recipe_ids_seen)
            break

        print("\n" + "-" * 60)
        print(f"📄 Round-robin processing for PAGE {page_index}")
        print(f"Active ingredients on this page: {live_ings}")
        print("-" * 60)

        any_used = False

        for ing in live_ings:
            # Dynamically discover this page for this ingredient if needed
            if page_index not in ingredient_pages[ing]:
                page_data = fetch_page(ing, page_index, limit=10)
                if page_data:
                    ingredient_pages[ing][page_index] = page_data
                    max_page[ing] = max(max_page[ing], page_index)
                else:
                    # No more pages for this ingredient
                    done_ings.add(ing)
                    continue

            page_recipes = ingredient_pages[ing].get(page_index, [])
            if not page_recipes:
                continue

            # Filter out already-saved recipes
            candidates = [r for r in page_recipes if r.get("Recipe_id") not in recipe_ids_seen]
            if not candidates:
                continue

            any_used = True

            # Random 1–5 recipes from this page (capped by available count)
            max_k = min(5, len(candidates))
            k = random.randint(1, max_k)
            chosen = random.sample(candidates, k)

            for r in chosen:
                rid = r.get("Recipe_id")
                if not rid or rid in recipe_ids_seen:
                    continue

                recipe_ids_seen.add(rid)

                full_root = fetch_full_recipe(rid)
                if full_root:
                    title = full_root.get("recipe", {}).get("recipe_title")
                    print(f"💾 Saved FULL recipe → {title} (ingredient: {ing}, page {page_index})")
                    append_to_csv(full_root)

                time.sleep(0.1)

        if not any_used:
            # No ingredient had data for this page_index → we are done
            break

        page_index += 1


# -------------------------------------------------------------
# 9. MAIN SCRIPT
# -------------------------------------------------------------
def main():
    print("\n🚀 Starting recipe extraction with FULL details, randomness, and realtime CSV saving...")
    init_csv()

    # 1) Discover which ingredients are valid + their page 1
    ingredient_pages, max_page = discover_ingredient_pages()

    # 2) Round-robin sampling across ingredients and pages
    recipe_ids_seen = set()
    process_all_ingredients_round_robin(ingredient_pages, max_page, recipe_ids_seen)

    print(f"\n✅ Done. Total unique recipes saved: {len(recipe_ids_seen)}")
    print(f"📁 CSV file: {CSV_FILE}")


# -------------------------------------------------------------
# RUN
# -------------------------------------------------------------
if __name__ == "__main__":
    main()
