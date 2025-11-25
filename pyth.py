#!/usr/bin/env python3
"""
extract_and_insert_threaded.py

Threaded extractor for recipe2-api (synchronous requests + threadpool).

Features:
 - Uses ThreadPoolExecutor to fetch pages and recipe-details concurrently.
 - Writes NDJSON and CSV incrementally using thread-safe locks.
 - Optional MySQL insertion (uses mysql-connector-python connection pool).
 - Checkpointing by page so you can resume.
 - CLI flags to control start page, limit pages, and concurrency.

Install requirements:
  pip install requests mysql-connector-python python-dotenv tqdm

Example:
  export MYSQL_HOST=... MYSQL_USER=... MYSQL_PASSWORD=... MYSQL_DB=recipe_db
  python extract_and_insert_threaded.py --limit-pages 100 --workers 40

Notes:
 - The script intentionally keeps DB upserts simple and robust (INSERT ... ON DUPLICATE KEY UPDATE).
 - Because heavy threading + DB + file IO can stress the host, tune --workers accordingly.
"""

import os
import sys
import json
import math
import csv
import time
import argparse
import re
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue, Empty
from threading import Lock
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# optional DB
try:
    import mysql.connector
    from mysql.connector import pooling
except Exception:
    mysql = None
    pooling = None

# ---------- CONFIG ----------
DEFAULT_RECIPES_INFO_EP = os.getenv("RECIPES_INFO_EP", "http://192.168.1.92:3031/recipe2-api/recipe/recipesinfo")
DEFAULT_RECIPE_DETAIL_FMT = os.getenv("RECIPE_DETAIL_FMT", "http://192.168.1.92:3031/recipe2-api/search-recipe/{}")

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./extracted_recipes")
os.makedirs(OUTPUT_DIR, exist_ok=True)
NDJSON_PATH = os.path.join(OUTPUT_DIR, "all_recipes.ndjson")
CSV_PATH = os.path.join(OUTPUT_DIR, "all_recipes.csv")
CHECKPOINT_PATH = os.path.join(OUTPUT_DIR, "checkpoint_page.txt")
DEBUG_DIR = os.path.join(OUTPUT_DIR, "debug")
os.makedirs(DEBUG_DIR, exist_ok=True)

WORKERS = int(os.getenv("WORKERS", "40"))
PAGE_CONCURRENCY = int(os.getenv("PAGE_CONCURRENCY", "4"))
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "20"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_SLEEP = float(os.getenv("REQUEST_SLEEP", "0.01"))
HEADERS = {"Accept": "application/json"}
if os.getenv("RECIPE_API_TOKEN"):
    HEADERS["Authorization"] = os.getenv("RECIPE_API_TOKEN")

# DB config (optional)
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "1234")
MYSQL_DB = os.getenv("MYSQL_DB", "recipe_db")
POOL_NAME = "recipe_pool"
POOL_SIZE = int(os.getenv("MYSQL_POOL_SIZE", "10"))

# ---------- Normalization helpers ----------
PARENS = re.compile(r'\([^)]*\)')
NON_ALNUM = re.compile(r'[^a-z0-9\s]')
QUANTITY_PATTERN = re.compile(r'^\s*(\d+([\/\.\-]\d+)?|\d+\/\d+)\s*')
UNITS = ["cup","cups","teaspoon","teaspoons","tbsp","tablespoon","tablespoons","clove","cloves",
         "package","packages","pound","pounds","oz","ounce","ounces","gram","grams","kg","ml",
         "liter","litre","pinch","slice","slices","small","large","fresh","frozen","diced","chopped",
         "sliced","quartered","minced","ground","thawed","packed","divided","taste","g","lb","tablespoon"]

def normalize_ingredient_token(s):
    if not isinstance(s, str): return ""
    s = s.lower().strip()
    s = PARENS.sub("", s)
    s = QUANTITY_PATTERN.sub("", s)
    for u in UNITS:
        s = re.sub(r'\b' + re.escape(u) + r'\b', ' ', s)
    s = NON_ALNUM.sub(" ", s)
    s = re.sub(r'\s+', ' ', s).strip()
    if s.endswith("s") and len(s) > 3:
        s = s[:-1]
    return s

def extract_ingredient_phrases_and_list(detail):
    phrases = []
    ing_list = []
    if not detail:
        return phrases, ing_list
    if isinstance(detail, dict):
        for k in ("ingredient_Phrase", "ingredientPhrase", "ingredient_phrase", "ingredient_Phrases"):
            if k in detail and isinstance(detail[k], str):
                raw = detail[k]
                if "||" in raw:
                    parts = [p.strip() for p in raw.split("||") if p.strip()]
                else:
                    parts = [p.strip() for p in raw.split(",") if p.strip()]
                phrases.extend(parts)
        candidates = [detail]
        if "recipe" in detail and isinstance(detail["recipe"], dict):
            candidates.append(detail["recipe"])
        for container in candidates:
            for k in ("ingredients", "ingredient_Phrase", "ingredientPhrase", "ingredient_list", "ingredientsList", "ingredient_Phrases"):
                if k in container:
                    v = container[k]
                    if isinstance(v, list):
                        for el in v:
                            if isinstance(el, str):
                                ing_list.append(el.strip())
                            elif isinstance(el, dict):
                                for kk in ("ingredient_phrase", "ingredientPhrase", "ingredient", "name"):
                                    if kk in el and isinstance(el[kk], (str,int)):
                                        ing_list.append(str(el[kk]).strip()); break
                    elif isinstance(v, str):
                        if "||" in v:
                            parts = [p.strip() for p in v.split("||") if p.strip()]
                        else:
                            parts = [p.strip() for p in v.split(",") if p.strip()]
                        ing_list.extend(parts)
    # dedupe
    clean_list = []
    for x in ing_list:
        s = str(x).strip()
        if s and s not in clean_list:
            clean_list.append(s)
    clean_phrases = []
    for p in phrases:
        s = str(p).strip()
        if s and s not in clean_phrases:
            clean_phrases.append(s)
    return clean_phrases, clean_list

# ---------- HTTP session helper with retries ----------
def make_session():
    s = requests.Session()
    retries = Retry(total=MAX_RETRIES, backoff_factor=0.3,
                    status_forcelist=(500,502,503,504))
    adapter = HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update(HEADERS)
    return s

# ---------- DB helpers ----------
def create_mysql_pool():
    if pooling is None:
        return None
    try:
        pool = pooling.MySQLConnectionPool(
            pool_name=POOL_NAME, pool_size=POOL_SIZE,
            host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DB,
            autocommit=True
        )
        return pool
    except Exception as e:
        print("MySQL pool creation failed:", e)
        return None

def upsert_recipe_sync(conn, recrow):
    """
    conn: mysql.connector connection (not pool)
    recrow: dict with keys used below
    """
    try:
        sql = ("INSERT INTO recipes (recipe_id,title,url,region,sub_region,continent,source,img_url,calories,ingredient_phrases,ingredients_joined,raw_detail) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
               "ON DUPLICATE KEY UPDATE title=VALUES(title), url=VALUES(url), raw_detail=VALUES(raw_detail)")
        vals = [
            recrow.get("recipe_id"), recrow.get("title"), recrow.get("url"), recrow.get("region"),
            recrow.get("sub_region"), recrow.get("continent"), recrow.get("source"), recrow.get("img_url"),
            recrow.get("calories"), recrow.get("ingredient_phrases"), recrow.get("ingredients_joined"),
            recrow.get("raw_detail")
        ]
        cur = conn.cursor()
        cur.execute(sql, vals)
        cur.close()
    except Exception:
        # ignore DB errors to keep extraction robust
        pass

# ---------- Worker functions ----------
def fetch_recipes_page_sync(session, recipes_info_ep, page, param_name="page"):
    try:
        r = session.get(recipes_info_ep, params={param_name: page}, timeout=API_TIMEOUT)
        if r.status_code != 200:
            # dump debug
            with open(os.path.join(DEBUG_DIR, f"page_{page}_status_{r.status_code}.txt"), "w", encoding="utf-8") as df:
                df.write(r.text[:20000])
            return [], {}
        data = r.json()
        items = []
        pagination = {}
        if isinstance(data, dict):
            if "payload" in data and isinstance(data["payload"], dict) and "data" in data["payload"]:
                items = data["payload"]["data"]
                pagination = data["payload"].get("pagination", {})
            elif "data" in data and isinstance(data["data"], list):
                items = data["data"]
                pagination = data.get("pagination", {})
            else:
                for v in data.values():
                    if isinstance(v, list):
                        items = v
                        break
                pagination = data.get("payload", {}).get("pagination", data.get("pagination", {})) or {}
        elif isinstance(data, list):
            items = data
        return items, pagination
    except Exception as e:
        with open(os.path.join(DEBUG_DIR, f"page_{page}_error.txt"), "w", encoding="utf-8") as df:
            df.write(str(e) + "\n")
        return [], {}

def fetch_detail_sync(session, recipe_detail_fmt, recipe_id):
    url = recipe_detail_fmt.format(quote_plus(str(recipe_id)))
    try:
        r = session.get(url, timeout=API_TIMEOUT)
        if r.status_code == 200:
            try:
                return r.json(), url, r.status_code
            except Exception:
                return {"_raw_text": r.text}, url, r.status_code
        else:
            try:
                return r.json(), url, r.status_code
            except Exception:
                with open(os.path.join(DEBUG_DIR, f"detail_{recipe_id}_status_{r.status_code}.txt"), "w", encoding="utf-8") as df:
                    df.write(r.text[:20000])
                return None, url, r.status_code
    except Exception as e:
        with open(os.path.join(DEBUG_DIR, f"detail_{recipe_id}_error.txt"), "w", encoding="utf-8") as df:
            df.write(str(e) + "\n")
        return None, url, None

# ---------- Main threaded driver ----------
def run_threaded(recipes_info_ep, recipe_detail_fmt, start_page=1, limit_pages=None, workers=WORKERS, page_concurrency=PAGE_CONCURRENCY, max_empty_streak=6, enable_db=False):
    session = make_session()
    pool = create_mysql_pool() if enable_db else None
    csv_lock = Lock()
    ndjson_lock = Lock()
    db_lock = Lock()  # for getting connection from pool in thread-safe way (mysql-connector pools are thread-safe normally)

    # prepare CSV/NDJSON files
    csv_fieldnames = ["recipe_id","title","url","region","sub_region","continent","source","img_url","calories","ingredient_phrases","ingredients_joined"]
    csv_file = open(CSV_PATH, "a", newline="", encoding="utf-8")
    csv_writer = csv.DictWriter(csv_file, fieldnames=csv_fieldnames)
    if os.stat(CSV_PATH).st_size == 0:
        csv_writer.writeheader()
        csv_file.flush()

    ndjson_file = open(NDJSON_PATH, "a", encoding="utf-8")

    # discover total pages
    items, pagination = fetch_recipes_page_sync(session, recipes_info_ep, page=1)
    total_pages = None
    items_per_page = 10
    if isinstance(pagination, dict):
        total_pages = int(pagination.get("totalPages") or pagination.get("total_pages") or 0) or None
        items_per_page = int(pagination.get("itemsPerPage") or pagination.get("items_per_page") or items_per_page)
        total_count = int(pagination.get("totalCount") or 0)
        if not total_pages and total_count:
            total_pages = math.ceil(total_count / items_per_page)
    if not total_pages:
        total_pages = 200000
    print("Detected total_pages:", total_pages, "items_per_page:", items_per_page)

    # resume from checkpoint
    if start_page == 1 and os.path.exists(CHECKPOINT_PATH):
        try:
            with open(CHECKPOINT_PATH, "r") as ck:
                start_page = int(ck.read().strip() or "1")
            print("Resuming from page", start_page)
        except Exception:
            start_page = 1

    last_page_to_fetch = min(total_pages, start_page + (limit_pages - 1)) if limit_pages else total_pages

    executor = ThreadPoolExecutor(max_workers=workers)
    page_executor = ThreadPoolExecutor(max_workers=page_concurrency)

    page = start_page
    empty_streak = 0
    pages_fetched = 0

    # We'll submit page fetch tasks in chunks to utilize page_concurrency
    while page <= last_page_to_fetch:
        # prepare page batch
        batch_end = min(last_page_to_fetch, page + page_concurrency - 1)
        page_nums = list(range(page, batch_end + 1))

        future_to_page = {page_executor.submit(fetch_recipes_page_sync, session, recipes_info_ep, p): p for p in page_nums}

        for fut in as_completed(future_to_page):
            pnum = future_to_page[fut]
            pages_fetched += 1
            try:
                items, pagination = fut.result()
            except Exception as e:
                items = []
                pagination = {}
                with open(os.path.join(DEBUG_DIR, f"page_{pnum}_exception_fut.txt"), "w", encoding="utf-8") as df:
                    df.write(str(e))

            if not items:
                empty_streak += 1
                print(f"No items on page: {pnum} (empty_streak={empty_streak}/{max_empty_streak})")
                with open(os.path.join(DEBUG_DIR, "empty_pages.log"), "a", encoding="utf-8") as ef:
                    ef.write(f"{time.asctime()} - page {pnum} empty (streak {empty_streak})\n")
                if empty_streak >= max_empty_streak:
                    print("Reached max empty streak. Stopping.")
                    with open(CHECKPOINT_PATH, "w") as ck:
                        ck.write(str(pnum))
                    executor.shutdown(wait=True)
                    page_executor.shutdown(wait=True)
                    csv_file.close()
                    ndjson_file.close()
                    if pool:
                        try:
                            pool._remove_connections()
                        except Exception:
                            pass
                    return
                continue
            else:
                empty_streak = 0

            # extract recipe ids from items
            recipe_ids = []
            for it in items:
                if isinstance(it, dict):
                    rid = it.get("Recipe_id") or it.get("recipe_id") or it.get("id")
                    if rid is not None:
                        recipe_ids.append(rid)

            # submit detail fetch tasks
            futs = {executor.submit(fetch_detail_sync, session, recipe_detail_fmt, rid): rid for rid in recipe_ids}

            for dfut in as_completed(futs):
                rid = futs[dfut]
                try:
                    detail_json, detail_url, status = dfut.result()
                except Exception as e:
                    detail_json, detail_url, status = None, None, None
                    with open(os.path.join(DEBUG_DIR, f"detail_{rid}_exception.txt"), "w", encoding="utf-8") as df:
                        df.write(str(e))

                if detail_json is None:
                    continue

                # extract phrases & ingredients
                phrases, ingredients = extract_ingredient_phrases_and_list(detail_json)
                recrow = {
                    "recipe_id": rid,
                    "title": (detail_json.get("Recipe_title") or detail_json.get("recipe_title") or detail_json.get("title")) if isinstance(detail_json, dict) else None,
                    "url": (detail_json.get("url") or detail_url) if isinstance(detail_json, dict) else detail_url,
                    "region": detail_json.get("Region") if isinstance(detail_json, dict) else None,
                    "sub_region": detail_json.get("Sub_region") if isinstance(detail_json, dict) else None,
                    "continent": detail_json.get("Continent") if isinstance(detail_json, dict) else None,
                    "source": detail_json.get("Source") if isinstance(detail_json, dict) else None,
                    "img_url": detail_json.get("img_url") if isinstance(detail_json, dict) else None,
                    "calories": detail_json.get("Calories") if isinstance(detail_json, dict) else None,
                    "ingredient_phrases": " || ".join(phrases),
                    "ingredients_joined": " || ".join(ingredients),
                    "raw_detail": json.dumps(detail_json, ensure_ascii=False) if isinstance(detail_json, (dict, list)) else str(detail_json)
                }

                # write NDJSON (thread-safe)
                try:
                    with ndjson_lock:
                        ndjson_file.write(json.dumps({
                            "extracted_at": int(time.time()),
                            "recipe_id": rid,
                            "detail_url": detail_url,
                            "detail": detail_json
                        }, ensure_ascii=False) + "\n")
                        ndjson_file.flush()
                except Exception:
                    pass

                # write CSV (thread-safe)
                csv_row = {
                    "recipe_id": recrow["recipe_id"],
                    "title": recrow["title"],
                    "url": recrow["url"],
                    "region": recrow["region"],
                    "sub_region": recrow["sub_region"],
                    "continent": recrow["continent"],
                    "source": recrow["source"],
                    "img_url": recrow["img_url"],
                    "calories": recrow["calories"],
                    "ingredient_phrases": recrow["ingredient_phrases"],
                    "ingredients_joined": recrow["ingredients_joined"]
                }
                try:
                    with csv_lock:
                        csv_writer.writerow(csv_row)
                        csv_file.flush()
                except Exception:
                    pass

                # optional DB upsert
                if pool:
                    try:
                        # get connection from pool and upsert
                        conn = pool.get_connection()
                        upsert_recipe_sync(conn, recrow)
                        conn.close()
                    except Exception:
                        # ignore DB errors; log optionally
                        with open(os.path.join(DEBUG_DIR, "db_errors.log"), "a", encoding="utf-8") as df:
                            df.write(f"{time.asctime()} - db error for recipe {rid}\n")

            # checkpoint after finishing this page
            try:
                with open(CHECKPOINT_PATH, "w") as ck:
                    ck.write(str(pnum))
            except Exception:
                pass

        # advance to next batch
        page = batch_end + 1
        time.sleep(REQUEST_SLEEP)

    # shutdown
    executor.shutdown(wait=True)
    page_executor.shutdown(wait=True)
    csv_file.close()
    ndjson_file.close()
    if pool:
        try:
            pool._remove_connections()
        except Exception:
            pass
    print("Done. Pages fetched:", pages_fetched)

# ---------- CLI ----------
def parse_args():
    p = argparse.ArgumentParser(description="Threaded extractor for recipe2-api")
    p.add_argument("--recipes-info-ep", type=str, default=DEFAULT_RECIPES_INFO_EP, help="Recipes info endpoint")
    p.add_argument("--recipe-detail-fmt", type=str, default=DEFAULT_RECIPE_DETAIL_FMT, help="Recipe detail fmt (use {} for id)")
    p.add_argument("--start-page", type=int, default=1, help="Start page (default 1)")
    p.add_argument("--limit-pages", type=int, help="Limit pages to fetch (for testing)")
    p.add_argument("--workers", type=int, default=WORKERS, help="Number of worker threads for detail fetches")
    p.add_argument("--page-concurrency", type=int, default=PAGE_CONCURRENCY, help="Number of concurrent page fetch threads")
    p.add_argument("--max-empty-streak", type=int, default=6, help="How many consecutive empty pages to tolerate before stopping")
    p.add_argument("--enable-db", action="store_true", help="Enable MySQL upsert (requires mysql-connector-python and DB access)")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run_threaded(
        recipes_info_ep=args.recipes_info_ep,
        recipe_detail_fmt=args.recipe_detail_fmt,
        start_page=args.start_page,
        limit_pages=args.limit_pages,
        workers=args.workers,
        page_concurrency=args.page_concurrency,
        max_empty_streak=args.max_empty_streak,
        enable_db=args.enable_db
    )
