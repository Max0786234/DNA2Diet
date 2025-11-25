"""
Dynamic Recipe Fetcher Module
Fetches recipes from the recipe API dynamically for positive ingredients
"""

import requests
import json
import time
from typing import List, Dict, Optional, Set
import os

# Recipe API configuration
RECIPE_API_BASE = os.getenv("RECIPE_API_BASE", "http://192.168.1.92:3031/recipe2-api")
RECIPE_SEARCH_ENDPOINT = f"{RECIPE_API_BASE}/recipebyingredient/by-ingredients-categories-title"
RECIPE_DETAIL_ENDPOINT = f"{RECIPE_API_BASE}/search-recipe"

# API request settings
API_TIMEOUT = 10
REQUEST_DELAY = 0.1  # Delay between API requests to avoid rate limiting


def fetch_recipe_page(ingredient: str, page: int = 1, limit: int = 10) -> List[Dict]:
    """
    Fetch a page of recipes for a specific ingredient from the API
    Returns list of recipe basic info (with Recipe_id)
    """
    try:
        params = {
            "includeIngredients": ingredient,
            "excludeIngredients": "",
            "includeCategories": "",
            "excludeCategories": "",
            "title": "",
            "page": page,
            "limit": limit
        }
        
        response = requests.get(RECIPE_SEARCH_ENDPOINT, params=params, timeout=API_TIMEOUT)
        
        if response.status_code != 200:
            print(f"API error for ingredient '{ingredient}', page {page}: {response.status_code}")
            return []
        
        data = response.json()
        return data.get("data", [])
    except requests.exceptions.Timeout:
        print(f"Timeout fetching recipes for ingredient '{ingredient}', page {page}")
        return []
    except Exception as e:
        print(f"Error fetching recipes for ingredient '{ingredient}', page {page}: {e}")
        return []


def fetch_full_recipe_details(recipe_id: str) -> Optional[Dict]:
    """
    Fetch full recipe details from the API
    Returns recipe object with full details or None
    """
    try:
        url = f"{RECIPE_DETAIL_ENDPOINT}/{recipe_id}"
        response = requests.get(url, timeout=API_TIMEOUT)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        return data.get("data", data)
    except Exception as e:
        print(f"Error fetching recipe details for {recipe_id}: {e}")
        return None


def discover_all_pages_for_ingredient(ingredient: str, max_pages: int = 100) -> Dict[int, List[Dict]]:
    """
    Discover all available pages for an ingredient
    Returns dict mapping page number to list of recipe basic info
    """
    all_pages = {}
    
    for page in range(1, max_pages + 1):
        recipes = fetch_recipe_page(ingredient, page, limit=10)
        time.sleep(REQUEST_DELAY)  # Rate limiting
        
        if not recipes:
            break  # No more recipes
        
        all_pages[page] = recipes
        
        # If we got fewer recipes than requested, we've reached the end
        if len(recipes) < 10:
            break
    
    return all_pages


def fetch_recipes_for_ingredients_dynamically(
    positive_ingredients: Set[str],
    page: int = 1,
    per_page: int = 12,
    recipe_ids_seen: Optional[Set[str]] = None
) -> Dict:
    """
    Dynamically fetch recipes from API for multiple ingredients
    Uses round-robin approach across ingredients and pages
    Returns paginated result
    """
    if recipe_ids_seen is None:
        recipe_ids_seen = set()
    
    # Get all recipe pages for each ingredient (lazy loading - fetch as needed)
    # For now, we'll fetch page-by-page dynamically
    all_recipes = []
    ingredients_list = sorted(list(positive_ingredients))
    
    if not ingredients_list:
        return {
            'recipes': [],
            'total': 0,
            'page': page,
            'per_page': per_page,
            'total_pages': 0,
            'has_next': False,
            'has_prev': False
        }
    
    # Strategy: Fetch recipes in a round-robin manner across ingredients
    # For each ingredient, fetch up to a certain page number
    # We'll start with page 1 for all ingredients, then page 2, etc.
    max_page_to_check = 20  # Limit to prevent too many API calls
    
    # Fetch recipes round-robin style
    for page_num in range(1, max_page_to_check + 1):
        for ingredient in ingredients_list:
            recipes_on_page = fetch_recipe_page(ingredient, page_num, limit=10)
            time.sleep(REQUEST_DELAY)
            
            for recipe_info in recipes_on_page:
                recipe_id = recipe_info.get("Recipe_id")
                if recipe_id and recipe_id not in recipe_ids_seen:
                    recipe_ids_seen.add(recipe_id)
                    
                    # Fetch full recipe details
                    full_recipe = fetch_full_recipe_details(recipe_id)
                    time.sleep(REQUEST_DELAY)
                    
                    if full_recipe:
                        # Convert to our format
                        recipe = format_recipe_from_api(full_recipe)
                        if recipe:
                            all_recipes.append(recipe)
    
    # Paginate results
    total = len(all_recipes)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 0
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_recipes = all_recipes[start_idx:end_idx]
    
    return {
        'recipes': page_recipes,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'has_next': page < total_pages,
        'has_prev': page > 1
    }


def format_recipe_from_api(api_recipe: Dict) -> Optional[Dict]:
    """Convert API recipe format to our standard format"""
    try:
        recipe_data = api_recipe.get("recipe", {})
        ingredients_data = api_recipe.get("ingredients", [])
        
        # Extract ingredient phrases
        ingredient_phrases = [
            ing.get("ingredient_phrase", "")
            for ing in ingredients_data
            if ing.get("ingredient_phrase")
        ]
        
        return {
            'recipe_id': recipe_data.get("recipe_id"),
            'recipe_title': recipe_data.get("recipe_title"),
            'url': recipe_data.get("url"),
            'img_url': recipe_data.get("img_url"),
            'region': recipe_data.get("region"),
            'servings': recipe_data.get("servings"),
            'calories': recipe_data.get("calories"),
            'energy_kcal': recipe_data.get("energy (kcal)"),
            'protein_g': recipe_data.get("protein (g)"),
            'carbohydrate_by_difference_g': recipe_data.get("carbohydrate, by difference (g)"),
            'total_lipid_fat_g': recipe_data.get("total lipid (fat) (g)"),
            'cook_time_min': recipe_data.get("cook_time"),
            'prep_time_min': recipe_data.get("prep_time"),
            'total_time_min': recipe_data.get("total_time"),
            'ingredient_phrases': ingredient_phrases,
            'vegan': recipe_data.get("vegan"),
            'pescetarian': recipe_data.get("pescetarian"),
        }
    except Exception as e:
        print(f"Error formatting recipe: {e}")
        return None

