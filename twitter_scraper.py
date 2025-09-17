import os
import time
import random
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from pathlib import Path
import json
import requests

from pymongo import MongoClient, ASCENDING

# ================= Configuration =================
# General settings
TIMEOUT = 10 # Default timeout for requests

# Scraping behavior
DATABASE_BATCH_SIZE = 100 # Number of records to hold in memory before writing to DB

import csv
import argparse

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

# ================= Configuration =================
# General settings
HEADLESS = False # Set to False for login, can be True for scraping runs
TIMEOUT = 15

# Scraping behavior
DATABASE_BATCH_SIZE = 100
MAX_SCROLL_ATTEMPTS = 500 # Increased for larger scrapes
MAX_NO_CHANGE = 10
MAX_CSV_SIZE_MB = 100 # Warn user if file exceeds this size

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
    handlers=[
        logging.FileHandler('twitter_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===============================================
# ||            API CLIENT CLASS               ||
# ===============================================
class APIClient:
    """A lightweight client for making direct requests to Twitter's internal GraphQL API."""
    def __init__(self, headers: Dict):
        if not all(k in headers for k in ["authorization", "x-csrf-token"]):
            raise ValueError("Headers must include 'authorization' and 'x-csrf-token'")
        self.headers = headers
        self.features = {
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
        }
        self.graphql_endpoints = {
            "followers": "SOV5_5_1J1s2gN4Jm2i6pQ",
            "following": "p2A2osV822aij1aDk3uyPA",
            "user_tweets": "Uil22sL2OA_v58aWILY2CA",
        }

    def make_request(self, url: str, params: Dict) -> Optional[Dict]:
        """Makes a GET request to the specified GraphQL endpoint."""
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None

    def get_user_by_screen_name(self, screen_name: str) -> Optional[Dict]:
        """Gets a user's ID from their screen name."""
        url = "https://twitter.com/i/api/graphql/rePnxwe9hM4oD3M5f2p-dg/UserByScreenName"
        params = {
            "variables": json.dumps({"screen_name": screen_name, "withSafetyModeUserFields": True}),
            "features": json.dumps(self.features)
        }
        data = self.make_request(url, params)
        if data and data.get("data", {}).get("user", {}).get("result", {}).get("rest_id"):
            return data["data"]["user"]["result"]
        return None

    def get_followers(self, user_id: str, count: int = 20, cursor: Optional[str] = None) -> Optional[Dict]:
        url = f"https://twitter.com/i/api/graphql/{self.graphql_endpoints['followers']}/Followers"
        variables = {"userId": user_id, "count": count, "includePromotedContent": False}
        if cursor:
            variables["cursor"] = cursor
        params = {"variables": json.dumps(variables), "features": json.dumps(self.features)}
        return self.make_request(url, params)

    def get_following(self, user_id: str, count: int = 20, cursor: Optional[str] = None) -> Optional[Dict]:
        url = f"https://twitter.com/i/api/graphql/{self.graphql_endpoints['following']}/Following"
        variables = {"userId": user_id, "count": count, "includePromotedContent": False}
        if cursor:
            variables["cursor"] = cursor
        params = {"variables": json.dumps(variables), "features": json.dumps(self.features)}
        return self.make_request(url, params)

    def get_user_tweets(self, user_id: str, count: int = 20, cursor: Optional[str] = None) -> Optional[Dict]:
        url = f"https://twitter.com/i/api/graphql/{self.graphql_endpoints['user_tweets']}/UserTweets"
        variables = {"userId": user_id, "count": count, "includePromotedContent": True, "withVoice": True}
        if cursor:
            variables["cursor"] = cursor
        params = {"variables": json.dumps(variables), "features": json.dumps(self.features)}
        return self.make_request(url, params)

# ===============================================
# ||           JOB MANAGER CLASS               ||
# ===============================================
class JobManager:
    """Handles the state of long-running scraping jobs."""
    def __init__(self, job_dir: str = 'jobs'):
        self.job_dir = Path(job_dir)
        self.job_dir.mkdir(exist_ok=True)

    def _get_job_path(self, job_name: str) -> Path:
        return self.job_dir / f"{job_name}.json"

    def load_job(self, job_name: str) -> Optional[Dict]:
        job_path = self._get_job_path(job_name)
        if job_path.exists():
            with open(job_path, 'r') as f:
                return json.load(f)
        return None

    def save_job(self, job_name: str, job_data: Dict):
        job_path = self._get_job_path(job_name)
        with open(job_path, 'w') as f:
            json.dump(job_data, f, indent=4)

# ===============================================
# ||          DATABASE MANAGER CLASS           ||
# ===============================================
class MongoDBManager:
    """Manages all interactions with the MongoDB database."""
    def __init__(self, uri: str, db_name: str = 'twitter_scraping'):
        try:
            self.client = MongoClient(uri)
            self.db = self.client[db_name]
            logger.info("Successfully connected to MongoDB.")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def get_collection(self, collection_name: str):
        collection = self.db[collection_name]
        collection.create_index([('id', ASCENDING)], unique=True)
        return collection

    def batch_upsert(self, collection, documents: List[Dict]):
        if not documents:
            return 0
        from pymongo import UpdateOne
        operations = [UpdateOne({'id': doc['id']}, {'$set': doc}, upsert=True) for doc in documents]
        try:
            result = collection.bulk_write(operations, ordered=False)
            logger.info(f"Upserted {result.upserted_count} and modified {result.modified_count} documents.")
            return result.upserted_count + result.modified_count
        except Exception as e:
            logger.error(f"An error occurred during batch upsert: {e}")
            return 0

    def get_seen_ids(self, collection) -> Set[str]:
        logger.info(f"Loading seen IDs from collection '{collection.name}'...")
        seen_ids = {str(doc['id']) for doc in collection.find({}, {'id': 1})}
        logger.info(f"Loaded {len(seen_ids)} seen IDs.")
        return seen_ids

# ===============================================
# ||            CORE SCRAPER CLASS             ||
# ===============================================
class TwitterScraper:
    """The main class for handling all Twitter scraping operations."""
    def __init__(self, api_client: APIClient, mongo_uri: str):
        self.api_client = api_client
        self.db_manager = MongoDBManager(uri=mongo_uri)
        self.job_manager = JobManager()

    def scrape_followers(self, username: str, max_items: Optional[int] = None):
        return self._scrape_api_generic_user_list(username, "followers", max_items)

    def scrape_following(self, username: str, max_items: Optional[int] = None):
        return self._scrape_api_generic_user_list(username, "following", max_items)

    def run_scraping_job(self, job_config: Dict):
        job_name = f"{job_config['task']}_{job_config['identifier']}"
        job_state = self.job_manager.load_job(job_name) or {}

        job_state.setdefault('total_target', job_config.get('total_target', float('inf')))
        job_state.setdefault('session_limit', job_config.get('session_limit', 1000))

        task_map = {
            'followers': self.scrape_followers,
            'following': self.scrape_following,
        }
        task_func = task_map[job_config['task']]

        collection = self.db_manager.get_collection("users")

        while True:
            current_count = collection.count_documents({"source_account": job_config['identifier'], "task_type": job_config['task']})
            remaining = job_state['total_target'] - current_count

            if remaining <= 0:
                logger.info(f"Job '{job_name}' target reached.")
                break

            items_to_scrape = min(remaining, job_state['session_limit'])
            logger.info(f"Starting session for job '{job_name}'. Aiming to scrape {items_to_scrape} items.")

            newly_scraped = task_func(username=job_config['identifier'], max_items=items_to_scrape)

            job_state['completed_sessions'] = job_state.get('completed_sessions', 0) + 1
            self.job_manager.save_job(job_name, job_state)

            if len(newly_scraped) < items_to_scrape:
                logger.info("Scraping session finished early (likely hit the end of the list). Job complete.")
                break

    def _scrape_api_generic_user_list(self, username: str, task_type: str, max_items: Optional[int] = None) -> List[Dict]:
        logger.info(f"Starting API {task_type} scrape for user: {username}")
        user_info = self.api_client.get_user_by_screen_name(username)
        if not user_info:
            logger.error(f"Could not get user ID for {username}. Aborting {task_type} scrape.")
            return []

        user_id = user_info['rest_id']
        source_info = {"task_type": task_type, "source_account": username}
        collection = self.db_manager.get_collection("users")
        seen_ids = self.db_manager.get_seen_ids(collection)

        collected_items = []
        memory_buffer = []
        cursor = None

        api_method = getattr(self.api_client, f"get_{task_type}")

        while True:
            if max_items and len(collected_items) >= max_items:
                break

            response_data = api_method(user_id, count=100, cursor=cursor)
            if not response_data:
                break

            instructions = response_data.get("data", {}).get("user", {}).get("result", {}).get("timeline", {}).get("timeline", {}).get("instructions", [])
            new_cursor = None

            for instruction in instructions:
                if instruction.get("type") == "TimelineAddEntries":
                    entries = instruction.get("entries", [])
                    for entry in entries:
                        content = entry.get("content", {})
                        if content.get("entryType") == "TimelineTimelineCursor" and content.get("cursorType") == "Bottom":
                            new_cursor = content.get("value")
                            continue

                        if content.get("entryType") == "TimelineTimelineItem":
                            item_content = content.get("itemContent", {}).get("user_results", {}).get("result", {})
                            user_id_scraped = item_content.get("rest_id")

                            if user_id_scraped and user_id_scraped not in seen_ids:
                                legacy_data = item_content.get("legacy", {})
                                user_data = {
                                    "id": user_id_scraped,
                                    "username": legacy_data.get("screen_name"),
                                    "display_name": legacy_data.get("name"),
                                    "bio": legacy_data.get("description"),
                                    "followers_count": legacy_data.get("followers_count"),
                                    "following_count": legacy_data.get("friends_count"),
                                    "scraped_at": datetime.utcnow().isoformat(),
                                    **source_info
                                }
                                seen_ids.add(user_id_scraped)
                                memory_buffer.append(user_data)
                                collected_items.append(user_data)

            if len(memory_buffer) >= DATABASE_BATCH_SIZE:
                self.db_manager.batch_upsert(collection, memory_buffer)
                memory_buffer.clear()

            if not new_cursor or new_cursor == cursor:
                break

            cursor = new_cursor
            time.sleep(random.uniform(1, 3))

        if memory_buffer:
            self.db_manager.batch_upsert(collection, memory_buffer)

        logger.info(f"{task_type.capitalize()} scrape finished. Collected {len(collected_items)} new items.")
        return collected_items

    # ... other scrape methods ...

if __name__ == "__main__":
    # Load configuration from environment variables
    MONGO_DB_URI = os.getenv('MONGO_DB_URI')
    AUTH_TOKEN = os.getenv('TWITTER_AUTH_TOKEN')
    CSRF_TOKEN = os.getenv('TWITTER_CSRF_TOKEN')
    COOKIE = os.getenv('TWITTER_COOKIE')

    if not all([MONGO_DB_URI, AUTH_TOKEN, CSRF_TOKEN, COOKIE]):
        print("FATAL: Please set all required environment variables: MONGO_DB_URI, TWITTER_AUTH_TOKEN, TWITTER_CSRF_TOKEN, TWITTER_COOKIE")
    else:
        try:
            # 1. Create the headers dictionary
            headers = {
                "authorization": AUTH_TOKEN,
                "x-csrf-token": CSRF_TOKEN,
                "cookie": COOKIE
            }

            # 2. Initialize the clients
            api_client = APIClient(headers)
            scraper = TwitterScraper(api_client=api_client, mongo_uri=MONGO_DB_URI)

            # 3. Define and run a job
            follower_job = {
                "task": "followers",
                "identifier": "elonmusk",
                "total_target": 500,
                "session_limit": 200,
            }
            scraper.run_scraping_job(follower_job)

        except Exception as e:
            logger.error(f"A critical error occurred in main execution: {e}")

# ===============================================
# ||            CSV MANAGER CLASS              ||
# ===============================================
class CSVManager:
    """Handles all CSV file operations."""
    def __init__(self, output_dir: str = 'output', max_rows_per_file: int = 1000000):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.max_rows_per_file = max_rows_per_file
        self.file_handles = {}
        self.writers = {}
        self.row_counts = {}

    def get_current_filepath(self, base_filename: str) -> Path:
        file_index = 1
        while True:
            filepath = self.output_dir / f"{base_filename}_{file_index}.csv"
            if not filepath.exists():
                return filepath
            if self.row_counts.get(str(filepath)) is None:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        self.row_counts[str(filepath)] = sum(1 for row in f) - 1
                except FileNotFoundError:
                     self.row_counts[str(filepath)] = 0
            if self.row_counts[str(filepath)] < self.max_rows_per_file:
                return filepath
            file_index += 1

    def write_data(self, base_filename: str, data: List[Dict]):
        if not data:
            return
        filepath = self.get_current_filepath(base_filename)
        filepath_str = str(filepath)
        if filepath_str not in self.file_handles:
            is_new_file = not filepath.exists()
            self.file_handles[filepath_str] = open(filepath, 'a', newline='', encoding='utf-8')
            fieldnames = data[0].keys()
            self.writers[filepath_str] = csv.DictWriter(self.file_handles[filepath_str], fieldnames=fieldnames)
            if is_new_file:
                self.writers[filepath_str].writeheader()
                self.row_counts[filepath_str] = 0
        self.writers[filepath_str].writerows(data)
        self.row_counts[filepath_str] += len(data)
        logger.info(f"Wrote {len(data)} rows to {filepath_str}")

    def get_seen_ids(self, base_filename: str) -> Set[str]:
        seen_ids = set()
        file_index = 1
        while True:
            filepath = self.output_dir / f"{base_filename}_{file_index}.csv"
            if not filepath.exists():
                break

            # Warn user if file is large
            if filepath.stat().st_size > MAX_CSV_SIZE_MB * 1024 * 1024:
                logger.warning(f"File {filepath} is large. Loading seen IDs may be slow.")

            logger.info(f"Loading seen IDs from {filepath}...")
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if 'id' in row:
                            seen_ids.add(row['id'])
            except Exception as e:
                logger.error(f"Could not read {filepath}: {e}")
            file_index += 1
        logger.info(f"Loaded {len(seen_ids)} unique IDs from all files for '{base_filename}'.")
        return seen_ids

    def close_files(self):
        for f in self.file_handles.values():
            f.close()
        self.file_handles.clear()
        self.writers.clear()

# ===============================================
# ||            CORE SCRAPER CLASS             ||
# ===============================================
class TwitterScraper:
    """The main class for handling all Twitter scraping operations."""
    def __init__(self, headless: bool = HEADLESS, timeout: int = TIMEOUT, cookies_file: str = 'cookies.json'):
        self.driver = None
        self.wait = None
        self.timeout = timeout
        self.cookies_file = Path(cookies_file)
        self.csv_manager = CSVManager()
        self.setup_driver(headless)

    def setup_driver(self, headless: bool):
        logger.info("Setting up Selenium driver...")
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, self.timeout)
            logger.info("Selenium driver initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Selenium driver: {e}")
            raise

    def load_cookies(self):
        logger.info(f"Loading cookies from {self.cookies_file}...")
        with open(self.cookies_file, 'r') as f:
            cookies = json.load(f)
        self.driver.get("https://twitter.com")
        for cookie in cookies:
            self.driver.add_cookie(cookie)
        logger.info("Cookies loaded successfully.")

    def save_cookies(self):
        logger.info(f"Saving cookies to {self.cookies_file}...")
        with open(self.cookies_file, 'w') as f:
            json.dump(self.driver.get_cookies(), f)
        logger.info("Cookies saved successfully.")

    def login(self, username: str, password: str):
        logger.info("Performing full login... Please follow instructions in the browser window.")
        try:
            self.driver.get("https://twitter.com/login")
            user_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="text"]')))
            user_input.send_keys(username)
            user_input.send_keys(Keys.RETURN)

            # User will handle the rest manually in the browser
            logger.info("Username entered. Please complete login (password, confirmation codes) in the browser.")
            logger.info("Waiting for you to be logged in...")

            # Wait for the user to be redirected to the home timeline
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href='/home']")))
            logger.info("Login detected!")

            self.save_cookies()
            return True
        except Exception as e:
            logger.error(f"Login process failed: {e}")
            return False

    def _extract_user_data(self, element, source_info: Dict) -> Optional[Dict]:
        try:
            username_element = element.find_element(By.XPATH, ".//span[contains(text(), '@')]")
            username = username_element.text.strip()

            user_data = {
                'id': username,
                'username': username,
                'scraped_at': datetime.utcnow().isoformat(),
                **source_info
            }
            return user_data
        except NoSuchElementException:
            return None

    def _scrape_selenium_page(self, url: str, base_filename: str, item_selector: str, extract_func: callable, max_items: Optional[int], source_info: Dict) -> List[Dict]:
        logger.info(f"Starting Selenium scrape for URL: {url}")
        self.driver.get(url)
        seen_ids = self.csv_manager.get_seen_ids(base_filename)
        collected_items = []
        memory_buffer = []
        no_change_count = 0

        for _ in range(MAX_SCROLL_ATTEMPTS):
            if max_items and len(collected_items) >= max_items:
                logger.info(f"Reached max_items limit of {max_items}.")
                break
            try:
                elements = self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, item_selector)))
                new_items_found = False
                for element in elements:
                    data = extract_func(element, source_info)
                    if data and data['id'] not in seen_ids:
                        new_items_found = True
                        seen_ids.add(data['id'])
                        memory_buffer.append(data)
                        collected_items.append(data)

                if not new_items_found:
                    no_change_count += 1
                else:
                    no_change_count = 0
                if no_change_count >= MAX_NO_CHANGE:
                    logger.info("No new items found for several scrolls. Ending scrape.")
                    break
                if len(memory_buffer) >= DATABASE_BATCH_SIZE:
                    self.csv_manager.write_data(base_filename, memory_buffer)
                    memory_buffer.clear()
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(2, 4))
            except TimeoutException:
                logger.warning("No more items found on page.")
                break

        if memory_buffer:
            self.csv_manager.write_data(base_filename, memory_buffer)
        logger.info(f"Scrape finished. Collected {len(collected_items)} new items.")
        return collected_items

    def scrape_followers(self, username: str, max_items: Optional[int] = None):
        url = f"https://twitter.com/{username}/followers"
        source_info = {"task_type": "followers", "source_account": username}
        base_filename = f"{username}_followers"
        return self._scrape_selenium_page(url=url, base_filename=base_filename, item_selector="div[data-testid='UserCell']", extract_func=self._extract_user_data, max_items=max_items, source_info=source_info)

    def scrape_following(self, username: str, max_items: Optional[int] = None):
        url = f"https://twitter.com/{username}/following"
        source_info = {"task_type": "following", "source_account": username}
        base_filename = f"{username}_following"
        return self._scrape_selenium_page(url=url, base_filename=base_filename, item_selector="div[data-testid='UserCell']", extract_func=self._extract_user_data, max_items=max_items, source_info=source_info)

    def quit(self):
        if self.driver:
            self.driver.quit()
            logger.info("Browser closed.")
        self.csv_manager.close_files()

if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description="A Selenium-based scraper for Twitter.")
    parser.add_argument("--task", type=str, choices=['followers', 'following'], help="The scraping task to perform.")
    parser.add_argument("--user", type=str, help="The target Twitter username.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of items to scrape.")
    parser.add_argument("--login-first", action='store_true', help="Perform a manual login to create/update cookies.json.")

    args = parser.parse_args()

    TWITTER_USERNAME = os.getenv('TWITTER_USERNAME')
    TWITTER_PASSWORD = os.getenv('TWITTER_PASSWORD')

    if not all([TWITTER_USERNAME, TWITTER_PASSWORD]):
        print("FATAL: Please set TWITTER_USERNAME and TWITTER_PASSWORD in your .env file.")
    else:
        scraper = None
        try:
            # For the first run, force headed mode to make login easier
            run_headless = False if args.login_first else HEADLESS
            scraper = TwitterScraper(headless=run_headless)

            if args.login_first:
                scraper.login(TWITTER_USERNAME, TWITTER_PASSWORD)
            else:
                if not scraper.cookies_file.exists():
                    print("FATAL: cookies.json not found. Please run with --login-first to create it.")
                else:
                    scraper.load_cookies()
                    scraper.driver.get("https://twitter.com/home")
                    scraper.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href='/home']")))
                    logger.info("Login successful using cookies.")

                    if args.task and args.user:
                        if args.task == 'followers':
                            scraper.scrape_followers(args.user, max_items=args.limit)
                        elif args.task == 'following':
                            scraper.scrape_following(args.user, max_items=args.limit)
                    else:
                        print("Please provide a --task and --user for scraping.")

        except Exception as e:
            logger.error(f"A critical error occurred in main execution: {e}")
        finally:
            if scraper:
                scraper.quit()