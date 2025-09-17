import os
import time
import random
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from pathlib import Path
import json
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
