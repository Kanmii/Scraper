import os
import time
import random
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains

from webdriver_manager.chrome import ChromeDriverManager
from pymongo import MongoClient, ASCENDING

# ================= Configuration =================
# General settings
HEADLESS = False # Set to True for production/server environments
TIMEOUT = 10 # Default timeout for Selenium waits

# Scraping behavior
MAX_SCROLL_ATTEMPTS = 100 # Max scrolls per page before giving up
MAX_NO_CHANGE = 10 # Max consecutive scrolls with no new data before stopping
SLEEP_BETWEEN_SCROLLS = (1.5, 3.5) # Wait time between scrolls to mimic human behavior
DATABASE_BATCH_SIZE = 100 # Number of records to hold in memory before writing to DB

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
    handlers=[
        logging.FileHandler('unified_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

import json

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
        """Loads a job's state from a JSON file."""
        job_path = self._get_job_path(job_name)
        if job_path.exists():
            with open(job_path, 'r') as f:
                return json.load(f)
        return None

    def save_job(self, job_name: str, job_data: Dict):
        """Saves a job's state to a JSON file."""
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
        """Get a collection and ensure indexes are created."""
        collection = self.db[collection_name]
        collection.create_index([('id', ASCENDING)], unique=True)
        collection.create_index([('scraped_at', ASCENDING)])
        if 'users' in collection_name:
            collection.create_index([('username', ASCENDING)], unique=True)
            collection.create_index([('source_account', ASCENDING), ('task_type', ASCENDING)])
        return collection

    def batch_upsert(self, collection, documents: List[Dict]):
        """
        Upserts a batch of documents into a collection.
        This updates existing documents or inserts new ones.
        """
        if not documents:
            return 0

        from pymongo import UpdateOne
        operations = []
        for doc in documents:
            # We use 'id' as the unique key for upserting
            filter_query = {'id': doc['id']}
            update_query = {'$set': doc}
            operations.append(UpdateOne(filter_query, update_query, upsert=True))

        try:
            result = collection.bulk_write(operations, ordered=False)
            logger.info(f"Upserted {result.upserted_count} and modified {result.modified_count} documents.")
            return result.upserted_count + result.modified_count
        except Exception as e:
            logger.error(f"An error occurred during batch upsert: {e}")
            return 0

    def get_seen_ids(self, collection) -> Set[str]:
        """Retrieves all existing document IDs from a collection for deduplication."""
        logger.info(f"Loading seen IDs from collection '{collection.name}'...")
        seen_ids = {str(doc['id']) for doc in collection.find({}, {'id': 1})}
        logger.info(f"Loaded {len(seen_ids)} seen IDs.")
        return seen_ids


# ===============================================
# ||            CORE SCRAPER CLASS             ||
# ===============================================
class TwitterScraper:
    """The main class for handling all Twitter scraping operations."""
    def __init__(self, mongo_uri: str, headless: bool = HEADLESS, timeout: int = TIMEOUT):
        self.driver = None
        self.wait = None
        self.timeout = timeout
        self.db_manager = MongoDBManager(uri=mongo_uri)
        self.job_manager = JobManager()
        self.setup_driver(headless)

    def run_scraping_job(self, job_config: Dict):
        """
        Manages and executes a scraping job over potentially multiple sessions.
        """
        job_name = f"{job_config['task']}_{job_config['identifier']}"
        job_state = self.job_manager.load_job(job_name) or {}

        # Initialize job state if it's new
        job_state.setdefault('total_target', job_config.get('total_target', float('inf')))
        job_state.setdefault('session_limit', job_config.get('session_limit', 1000))
        job_state.setdefault('detail_level', job_config.get('detail_level', 'full'))
        job_state.setdefault('completed_sessions', 0)

        # Determine the correct scraping function and parameters
        task_map = {
            'followers': (self.scrape_followers, 'username'),
            'following': (self.scrape_following, 'username'),
            'likes': (self.scrape_tweet_likes, 'tweet_url'),
            'retweets': (self.scrape_tweet_retweets, 'tweet_url'),
            'tweets': (self.scrape_user_tweets, 'username'),
        }

        task_func, identifier_key = task_map[job_config['task']]

        # Scrape in a loop until the total target is met
        while True:
            # Check current progress from the database
            collection_name = 'tweets' if job_config['task'] == 'tweets' else 'users'
            collection = self.db_manager.get_collection(collection_name)
            current_count = collection.count_documents({
                'source_account' if 'user' in identifier_key else 'source_tweet': job_config['identifier']
            })

            remaining = job_state['total_target'] - current_count

            logger.info(f"Job '{job_name}': {current_count}/{job_state['total_target']} collected. {remaining} remaining.")

            if remaining <= 0:
                logger.info(f"Job '{job_name}' target reached. Nothing to do.")
                break

            items_to_scrape = min(remaining, job_state['session_limit'])

            logger.info(f"Starting session for job '{job_name}'. Aiming to scrape {items_to_scrape} items.")

            kwargs = {
                identifier_key: job_config['identifier'],
                'max_items': items_to_scrape,
                'detail_level': job_state['detail_level']
            }

            newly_scraped = task_func(**kwargs)

            job_state['completed_sessions'] += 1
            self.job_manager.save_job(job_name, job_state)

            # If the scraper returned fewer items than we asked for, it means we've hit the end.
            if len(newly_scraped) < items_to_scrape:
                logger.info("Scraping session finished early (likely hit the end of the list). Job complete.")
                break

            # Optional: Add a long pause between sessions if you run this in a continuous loop
            # time.sleep(3600)

    def setup_driver(self, headless: bool):
        """
        Sets up the Selenium Chrome driver with optimized options for performance and stealth.
        """
        logger.info("Setting up Chrome driver...")
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-zygote")
        options.add_argument("--single-process")

        # Performance/Stealth options from previous scripts
        profile_dir = f"/tmp/chrome_profile_{int(time.time())}"
        options.add_argument(f'--user-data-dir={profile_dir}')
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-logging")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")

        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")

        # Set a common user agent
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.set_page_load_timeout(30)
            self.wait = WebDriverWait(self.driver, self.timeout)

            # Anti-detection script
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logger.info("Chrome driver initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize driver: {e}")
            raise

    def login(self, username: str, password: str, email: Optional[str] = None) -> bool:
        """
        Handles the login process for Twitter/X, including an optional email verification step.
        """
        logger.info(f"Starting login for user: {username}")
        try:
            self.driver.get("https://twitter.com/login")

            # Step 1: Enter username
            username_input = self.wait.until(EC.presence_of_element_located((By.NAME, "text")))
            username_input.send_keys(username)
            username_input.send_keys(Keys.RETURN)
            logger.info("Username entered.")
            time.sleep(random.uniform(1.5, 2.5))

            # Step 2: Handle potential unusual prompt (e.g., phone or email)
            # Twitter sometimes asks for a phone number or email for verification after the username.
            try:
                email_input = self.driver.find_element(By.NAME, "text")
                if email and email_input.is_displayed():
                    logger.info("Email/phone verification prompt detected. Entering email.")
                    email_input.send_keys(email)
                    email_input.send_keys(Keys.RETURN)
                    time.sleep(random.uniform(1.5, 2.5))
            except NoSuchElementException:
                logger.info("No email/phone verification prompt detected. Proceeding to password.")

            # Step 3: Enter password
            password_input = self.wait.until(EC.presence_of_element_located((By.NAME, "password")))
            password_input.send_keys(password)
            password_input.send_keys(Keys.RETURN)
            logger.info("Password entered.")

            # Step 4: Verify login success
            self.wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.XPATH, "//a[@data-testid='AppTabBar_Home_Link']")),
                    EC.presence_of_element_located((By.XPATH, "//div[@data-testid='primaryColumn']"))
                )
            )
            logger.info("Login successful!")
            return True
        except TimeoutException:
            logger.error("Login failed. A timeout occurred waiting for an element.")
            # self.driver.save_screenshot('login_failure.png') # Helpful for debugging
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during login: {e}")
            # self.driver.save_screenshot('login_error.png')
            return False

    def _extract_user_data(self, element, source_info: Dict, detail_level: str = 'full') -> Optional[Dict]:
        """
        Extracts data from a user cell element.
        :param detail_level: 'full' or 'fast'. 'fast' only gets the username.
        """
        try:
            # Fast mode: Only get the username, which is the most critical piece of data.
            username_element = element.find_element(By.XPATH, ".//span[contains(text(), '@')]")
            username = username_element.text.strip()

            user_data = {
                'id': username,
                'username': username,
                'scraped_at': datetime.utcnow().isoformat(),
                **source_info
            }

            # Full mode: Get additional details.
            if detail_level == 'full':
                try:
                    display_name = element.find_element(By.XPATH, ".//div[@data-testid='UserCell']//a//div[@dir='ltr']//span[not(contains(text(), '@'))]").text.strip()
                except NoSuchElementException:
                    display_name = username.replace('@', '')

                try:
                    bio = element.find_element(By.XPATH, ".//div[@data-testid='UserCell']//div[@dir='auto']").text.strip()
                except NoSuchElementException:
                    bio = ""

                user_data.update({
                    'display_name': display_name,
                    'bio': bio,
                })

            return user_data
        except NoSuchElementException:
            logger.debug("Could not extract user data, required elements not found.")
            return None

    def _extract_tweet_data(self, element, source_info: Dict, detail_level: str = 'full') -> Optional[Dict]:
        """
        Extracts data from a tweet article element.
        :param detail_level: 'full' or 'fast'. 'fast' only gets the tweet ID and URL.
        """
        try:
            # Find the tweet link to get the URL and ID
            tweet_link_element = element.find_element(By.XPATH, ".//a[contains(@href, '/status/')]")
            tweet_url = tweet_link_element.get_attribute('href')
            tweet_id = tweet_url.split('/status/')[-1].split('?')[0]

            tweet_data = {
                'id': tweet_id,
                'tweet_url': tweet_url,
                'scraped_at': datetime.utcnow().isoformat(),
                **source_info
            }

            if detail_level == 'full':
                try:
                    text = element.find_element(By.XPATH, ".//div[@data-testid='tweetText']").text
                except NoSuchElementException:
                    text = ""

                def get_metric(testid):
                    try:
                        return element.find_element(By.XPATH, f".//div[@data-testid='{testid}']//span").text.strip() or "0"
                    except NoSuchElementException:
                        return "0"

                tweet_data.update({
                    'text': text,
                    'replies': get_metric('reply'),
                    'retweets': get_metric('retweet'),
                    'likes': get_metric('like'),
                })

            return tweet_data
        except NoSuchElementException:
            logger.debug("Could not extract tweet data, required elements not found.")
            return None

    def scrape_followers(self, username: str, max_items: Optional[int] = None, detail_level: str = 'full'):
        """Scrapes the followers of a given user."""
        url = f"https://twitter.com/{username}/followers"
        source_info = {"task_type": "followers", "source_account": username}
        return self._scrape_paginated_data(
            url=url,
            collection_name="users",
            item_selector="div[data-testid='UserCell']",
            extract_func=lambda el, si: self._extract_user_data(el, si, detail_level),
            max_items=max_items,
            source_info=source_info
        )

    def scrape_following(self, username: str, max_items: Optional[int] = None, detail_level: str = 'full'):
        """Scrapes the accounts a given user is following."""
        url = f"https://twitter.com/{username}/following"
        source_info = {"task_type": "following", "source_account": username}
        return self._scrape_paginated_data(
            url=url,
            collection_name="users",
            item_selector="div[data-testid='UserCell']",
            extract_func=lambda el, si: self._extract_user_data(el, si, detail_level),
            max_items=max_items,
            source_info=source_info
        )

    def scrape_tweet_likes(self, tweet_url: str, max_items: Optional[int] = None, detail_level: str = 'full'):
        """Scrapes the users who liked a given tweet."""
        url = f"{tweet_url}/likes"
        source_info = {"task_type": "likes", "source_tweet": tweet_url}
        return self._scrape_paginated_data(
            url=url,
            collection_name="users",
            item_selector="div[data-testid='UserCell']",
            extract_func=lambda el, si: self._extract_user_data(el, si, detail_level),
            max_items=max_items,
            source_info=source_info
        )

    def scrape_tweet_retweets(self, tweet_url: str, max_items: Optional[int] = None, detail_level: str = 'full'):
        """Scrapes the users who retweeted a given tweet."""
        url = f"{tweet_url}/retweets"
        source_info = {"task_type": "retweets", "source_tweet": tweet_url}
        return self._scrape_paginated_data(
            url=url,
            collection_name="users",
            item_selector="div[data-testid='UserCell']",
            extract_func=lambda el, si: self._extract_user_data(el, si, detail_level),
            max_items=max_items,
            source_info=source_info
        )

    def scrape_user_tweets(self, username: str, max_items: Optional[int] = None, detail_level: str = 'full'):
        """Scrapes the tweets from a user's profile."""
        url = f"https://twitter.com/{username}"
        source_info = {"task_type": "user_tweets", "source_account": username}
        return self._scrape_paginated_data(
            url=url,
            collection_name="tweets",
            item_selector="article[data-testid='tweet']",
            extract_func=lambda el, si: self._extract_tweet_data(el, si, detail_level),
            max_items=max_items,
            source_info=source_info
        )

    def _scrape_paginated_data(
        self,
        url: str,
        collection_name: str,
        item_selector: str,
        extract_func: callable,
        max_items: Optional[int],
        source_info: Dict
    ) -> List[Dict]:
        """
        A generic, unified method for scraping data from pages that require scrolling.

        :param url: The URL to scrape.
        :param collection_name: The name of the MongoDB collection to store data in.
        :param item_selector: The CSS selector to find individual items (tweets, users).
        :param extract_func: The function to call to extract data from a single item element.
        :param max_items: The maximum number of items to scrape in this session.
        :param source_info: Metadata about the scraping task (e.g., source account).
        """
        logger.info(f"Starting scrape for URL: {url}")
        self.driver.get(url)
        collection = self.db_manager.get_collection(collection_name)
        seen_ids = self.db_manager.get_seen_ids(collection)

        memory_buffer = []
        collected_items = []
        no_change_count = 0

        for scroll_attempt in range(MAX_SCROLL_ATTEMPTS):
            if max_items and len(collected_items) >= max_items:
                logger.info(f"Reached max_items limit of {max_items}.")
                break

            try:
                # Wait for items to be present
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, item_selector)))

                elements = self.driver.find_elements(By.CSS_SELECTOR, item_selector)

                new_items_found_in_scroll = False
                for element in elements:
                    try:
                        extracted_data = extract_func(element, source_info)
                        if extracted_data and extracted_data['id'] not in seen_ids:
                            seen_ids.add(extracted_data['id'])
                            memory_buffer.append(extracted_data)
                            collected_items.append(extracted_data)
                            new_items_found_in_scroll = True
                            logger.info(f"Scraped new item: {extracted_data['id']}")
                    except Exception as e:
                        logger.warning(f"Failed to extract data from an element: {e}")

                # Flush buffer to DB if it's full
                if len(memory_buffer) >= DATABASE_BATCH_SIZE:
                    logger.info(f"Memory buffer full. Flushing {len(memory_buffer)} items to DB.")
                    self.db_manager.batch_upsert(collection, memory_buffer)
                    memory_buffer.clear()

                # Check if we should stop scrolling
                if not new_items_found_in_scroll:
                    no_change_count += 1
                    logger.info(f"No new items found in this scroll. No-change count: {no_change_count}/{MAX_NO_CHANGE}")
                else:
                    no_change_count = 0 # Reset counter if we found new items

                if no_change_count >= MAX_NO_CHANGE:
                    logger.info("No new items found for several consecutive scrolls. Ending scrape.")
                    break

                # Scroll down
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(*SLEEP_BETWEEN_SCROLLS))

            except TimeoutException:
                logger.warning("Timeout while waiting for items. Page might be empty or not loaded correctly.")
                break
            except Exception as e:
                logger.error(f"An unexpected error occurred during scraping loop: {e}")
                break

        # Final flush of any remaining items in the buffer
        if memory_buffer:
            logger.info(f"Flushing remaining {len(memory_buffer)} items to DB.")
            self.db_manager.batch_upsert(collection, memory_buffer)
            memory_buffer.clear()

        logger.info(f"Scrape finished. Collected {len(collected_items)} new items in this session.")
        return collected_items

    def quit(self):
        """Closes the driver and cleans up resources."""
        if self.driver:
            self.driver.quit()
            logger.info("Browser driver closed.")


# ===============================================
# ||              MAIN EXECUTION               ||
# ===============================================
if __name__ == "__main__":
    # Load credentials from environment variables for security
    TWITTER_USERNAME = os.getenv('TWITTER_USERNAME')
    TWITTER_PASSWORD = os.getenv('TWITTER_PASSWORD')
    TWITTER_EMAIL = os.getenv('TWITTER_EMAIL') # Optional, for verification
    MONGO_DB_URI = os.getenv('MONGO_DB_URI')

    if not all([TWITTER_USERNAME, TWITTER_PASSWORD, MONGO_DB_URI]):
        print("FATAL: Please set TWITTER_USERNAME, TWITTER_PASSWORD, and MONGO_DB_URI environment variables.")
    else:
        scraper = None
        try:
            scraper = TwitterScraper(mongo_uri=MONGO_DB_URI, headless=HEADLESS)

            login_successful = scraper.login(
                username=TWITTER_USERNAME,
                password=TWITTER_PASSWORD,
                email=TWITTER_EMAIL
            )

            if login_successful:
                # --- Example Job: Scrape 500 followers from an account ---
                # This job will run in sessions of 200 until the target of 500 is met.
                # If you run this script again, it will pick up where it left off.
                follower_job = {
                    "task": "followers",
                    "identifier": "MindAIProject",
                    "total_target": 500,
                    "session_limit": 200,
                    "detail_level": "full"
                }
                scraper.run_scraping_job(follower_job)

                # --- Example Job: Scrape the 50 most recent tweets from an account ---
                tweet_job = {
                    "task": "tweets",
                    "identifier": "elonmusk",
                    "total_target": 50,
                    "session_limit": 50, # Will complete in one session
                    "detail_level": "full"
                }
                # scraper.run_scraping_job(tweet_job)

            else:
                print("Could not complete login. Please check your credentials and network.")

        except Exception as e:
            logger.error(f"A critical error occurred in main execution: {e}")
        finally:
            if scraper:
                scraper.quit()
