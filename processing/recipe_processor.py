"""
Recipe Processor Module
Filters and processes recipes from CSV based on positive ingredients
"""

import csv
import json
import re
from pathlib import Path
from typing import List, Dict, Set, Optional


def normalize_ingredient(ingredient: str) -> str:
    """Normalize ingredient name for matching"""
    if not ingredient:
        return ""
    # Convert to lowercase and remove extra spaces
    normalized = ingredient.lower().strip()
    # Remove common prefixes/suffixes
    normalized = re.sub(r'\b(fresh|dried|chopped|sliced|minced|ground|frozen|raw|cooked)\b', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    # Remove plural 's'
    if normalized.endswith('s') and len(normalized) > 3:
        normalized = normalized[:-1]
    return normalized


def ingredient_match(recipe_ingredients: List[str], positive_ingredients: Set[str]) -> bool:
    """
    Check if any recipe ingredient matches any positive ingredient
    Returns True if at least one match is found
    Uses flexible matching to catch variations
    """
    if not recipe_ingredients or not positive_ingredients:
        return False
    
    normalized_positive = {normalize_ingredient(ing) for ing in positive_ingredients}
    
    for recipe_ing in recipe_ingredients:
        if not recipe_ing or not isinstance(recipe_ing, str):
            continue
            
        normalized_recipe = normalize_ingredient(recipe_ing)
        if not normalized_recipe:
            continue
        
        # Check exact match or substring match (bidirectional)
        for pos_ing in normalized_positive:
            if not pos_ing:
                continue
            # Check if positive ingredient appears in recipe ingredient or vice versa
            if pos_ing in normalized_recipe or normalized_recipe in pos_ing:
                return True
            # Also check word-by-word matching for compound ingredients
            pos_words = pos_ing.split()
            recipe_words = normalized_recipe.split()
            if len(pos_words) > 0 and any(word in recipe_words for word in pos_words if len(word) > 2):
                return True
    
    return False


def load_positive_ingredients(ingredient_json_path: str) -> Set[str]:
    """Load positive ingredients (prefer) from ingredient recommendations JSON"""
    try:
        with open(ingredient_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        positive_ings = set()
        recommendations = data.get('ingredient_recommendations', {})
        
        for ing_name, info in recommendations.items():
            if info.get('final_action', '').lower().strip() == 'prefer':
                positive_ings.add(ing_name.lower().strip())
        
        return positive_ings
    except Exception as e:
        print(f"Error loading positive ingredients: {e}")
        return set()


def load_recipes_from_csv(csv_path: str) -> List[Dict]:
    """Load all recipes from CSV file"""
    recipes = []
    row_count = 0
    error_count = 0
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):  # Start at 2 because row 1 is header
                row_count += 1
                try:
                    # Parse ingredient_phrases JSON
                    ingredient_phrases_str = row.get('ingredient_phrases', '[]')
                    ingredient_phrases = []
                    
                    if ingredient_phrases_str:
                        try:
                            ingredient_phrases = json.loads(ingredient_phrases_str)
                            if not isinstance(ingredient_phrases, list):
                                ingredient_phrases = []
                        except json.JSONDecodeError as e:
                            # Try to handle malformed JSON
                            print(f"Warning: Row {row_num} has invalid ingredient_phrases JSON: {e}")
                            ingredient_phrases = []
                    
                    # Ensure recipe_id exists
                    recipe_id = row.get('recipe_id')
                    if not recipe_id:
                        print(f"Warning: Row {row_num} missing recipe_id, skipping")
                        error_count += 1
                        continue
                    
                    recipe = {
                        'recipe_id': recipe_id,
                        'recipe_title': row.get('recipe_title', 'Untitled Recipe'),
                        'url': row.get('url', ''),
                        'img_url': row.get('img_url', ''),
                        'region': row.get('region', ''),
                        'servings': row.get('servings', ''),
                        'calories': row.get('calories', ''),
                        'energy_kcal': row.get('energy_kcal', ''),
                        'protein_g': row.get('protein_g', ''),
                        'carbohydrate_by_difference_g': row.get('carbohydrate_by_difference_g', ''),
                        'total_lipid_fat_g': row.get('total_lipid_fat_g', ''),
                        'cook_time_min': row.get('cook_time_min', ''),
                        'prep_time_min': row.get('prep_time_min', ''),
                        'total_time_min': row.get('total_time_min', ''),
                        'ingredient_phrases': ingredient_phrases,
                        'vegan': row.get('vegan', ''),
                        'pescetarian': row.get('pescetarian', ''),
                    }
                    recipes.append(recipe)
                except Exception as e:
                    print(f"Error processing row {row_num} in CSV: {e}")
                    error_count += 1
                    continue
        
        print(f"Loaded {len(recipes)} recipes from CSV (processed {row_count} rows, {error_count} errors)")
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_path}")
    except Exception as e:
        print(f"Error loading recipes from CSV: {e}")
        import traceback
        traceback.print_exc()
    
    return recipes


def filter_recipes_by_ingredients(
    recipes: List[Dict], 
    positive_ingredients: Set[str]
) -> List[Dict]:
    """Filter recipes that contain at least one positive ingredient"""
    filtered = []
    for recipe in recipes:
        ingredient_phrases = recipe.get('ingredient_phrases', [])
        if ingredient_match(ingredient_phrases, positive_ingredients):
            filtered.append(recipe)
    return filtered


def get_recipes_for_analysis(
    analysis_id: int,
    ingredient_json_path: str,
    csv_path: str = "recipe_recommendations.csv",
    page: int = 1,
    per_page: int = 12
) -> Dict:
    """
    Get paginated recipes for a specific analysis
    Returns dict with recipes, total count, page info
    """
    # Load positive ingredients
    positive_ings = load_positive_ingredients(ingredient_json_path)
    
    if not positive_ings:
        print(f"No positive ingredients found for analysis {analysis_id}")
        return {
            'recipes': [],
            'total': 0,
            'page': page,
            'per_page': per_page,
            'total_pages': 0,
            'has_next': False,
            'has_prev': False
        }
    
    print(f"Loaded {len(positive_ings)} positive ingredients: {list(positive_ings)[:5]}...")
    
    # Load and filter recipes
    all_recipes = load_recipes_from_csv(csv_path)
    print(f"Total recipes loaded from CSV: {len(all_recipes)}")
    
    if not all_recipes:
        print(f"Warning: No recipes found in CSV file: {csv_path}")
        return {
            'recipes': [],
            'total': 0,
            'page': page,
            'per_page': per_page,
            'total_pages': 0,
            'has_next': False,
            'has_prev': False
        }
    
    filtered_recipes = filter_recipes_by_ingredients(all_recipes, positive_ings)
    print(f"Recipes after filtering: {len(filtered_recipes)}")
    
    # If filtering returns very few recipes (< 10% of total), show all recipes instead
    # This ensures users can see recipes even if ingredient matching is too strict
    if len(filtered_recipes) < len(all_recipes) * 0.1 and len(all_recipes) > 0:
        print(f"Filtering too strict ({len(filtered_recipes)}/{len(all_recipes)}), showing all recipes")
        recipes_to_show = all_recipes
    else:
        recipes_to_show = filtered_recipes
    
    # Calculate pagination
    total = len(recipes_to_show)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 0
    
    # Validate page number
    if page < 1:
        page = 1
    if page > total_pages and total_pages > 0:
        page = total_pages
    
    # Get recipes for current page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_recipes = recipes_to_show[start_idx:end_idx]
    
    print(f"Page {page}: Returning {len(page_recipes)} recipes (total: {total}, pages: {total_pages}, has_next: {page < total_pages})")
    
    return {
        'recipes': page_recipes,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'has_next': page < total_pages,
        'has_prev': page > 1
    }

