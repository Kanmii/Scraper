import os 
import time 
import random 
import json 
import logging 
from datetime import datetime, timedelta 
from typing import List, Dict, Optional, Set 

from selenium import webdriver 
from selenium.webdriver.chrome.service import Service 
from selenium.webdriver.common.by import By 
from selenium.webdriver.chrome.options import Options 
from selenium.webdriver.common.keys import Keys 
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC 
from selenium.common.exceptions import ( 
    NoSuchElementException,  
    TimeoutException,  
    WebDriverException, 
    ElementClickInterceptedException 
) 
from selenium.webdriver.common.action_chains import ActionChains 
from webdriver_manager.chrome import ChromeDriverManager 


# ================= Optimized Configuration =================
CHUNK_SIZE = 50  # Reduced from 100 for faster saves
MAX_SCROLL_ATTEMPTS = 100  # Reduced from 1000
MAX_NO_CHANGE = 8  # Reduced from 15
SLEEP_BETWEEN_SCROLLS = (2, 4)  # Reduced from (4, 8)
SLEEP_AFTER_CHUNK = (2, 5)     # Reduced from (5, 12)
MAX_FOLLOWERS = None
MAX_FOLLOWING = 1000
MAX_LIKES = 1000
MAX_RETWEETS = 1000
MAX_TWEETS = None

# Configure logging with reduced verbosity
logging.basicConfig( 
    level=logging.WARNING,  # Changed from INFO to reduce log spam
    format='%(asctime)s - %(levelname)s - %(message)s', 
    handlers=[ 
        logging.FileHandler('twitter_engagement_scraper.log'), 
        logging.StreamHandler() 
    ] 
) 
logger = logging.getLogger(__name__) 

class RateLimiter: 
    """Optimized rate limiter"""
    def __init__(self, max_requests: int = 8, time_window: int = 60):  # More aggressive
        self.max_requests = max_requests 
        self.time_window = time_window 
        self.requests = [] 
     
    def can_make_request(self) -> bool: 
        now = datetime.now() 
        # More efficient filtering
        cutoff = now - timedelta(seconds=self.time_window)
        self.requests = [req for req in self.requests if req > cutoff] 
        return len(self.requests) < self.max_requests 
     
    def make_request(self) -> bool: 
        if self.can_make_request(): 
            self.requests.append(datetime.now()) 
            return True 
        return False 
     
    def wait_if_needed(self): 
        if not self.can_make_request(): 
            wait_time = 30  # Reduced from time_window // 2
            logger.warning(f"Rate limit reached. Waiting {wait_time} seconds...") 
            time.sleep(wait_time) 

class TwitterEngagementScraper: 
    def __init__(self, headless: bool = False, timeout: int = 10):  # Reduced timeout
        self.driver = None 
        self.wait = None 
        self.timeout = timeout 
        self.rate_limiter = RateLimiter(max_requests=8, time_window=60)  # More aggressive
        self.scraped_users = set() 
        self.setup_driver(headless) 

    def setup_driver(self, headless: bool): 
        """Optimized Chrome driver setup""" 
        try: 
            options = Options() 
            options.add_argument("--start-maximized") 
            options.add_argument("--disable-blink-features=AutomationControlled") 
            options.add_argument("--disable-extensions") 
            options.add_argument("--disable-dev-shm-usage") 
            options.add_argument("--no-sandbox") 
            options.add_argument("--disable-gpu") 
            options.add_argument("--disable-software-rasterizer")
            options.add_argument("--disable-web-security") 
            options.add_argument("--allow-running-insecure-content") 
            
            # Performance optimizations
            options.add_argument("--disable-logging")
            options.add_argument("--disable-background-timer-throttling")
            options.add_argument("--disable-backgrounding-occluded-windows")
            options.add_argument("--disable-renderer-backgrounding")
            options.add_argument("--disable-features=TranslateUI")
            options.add_argument("--disable-ipc-flooding-protection")
            options.add_argument("--disable-background-networking")
            options.add_argument("--disable-default-apps")
            options.add_argument("--disable-sync")
            options.add_argument("--disable-component-update")
            
            options.add_argument( 
                "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) " 
                "AppleWebKit/537.36 (KHTML, like Gecko) " 
                "Chrome/120.0.0.0 Safari/537.36" 
            ) 
            if headless: 
                options.add_argument("--headless=new") 
                options.add_argument("--window-size=1920,1080") 
            options.add_experimental_option("excludeSwitches", ["enable-automation"]) 
            options.add_experimental_option('useAutomationExtension', False) 
            
            service = Service(ChromeDriverManager().install()) 
            self.driver = webdriver.Chrome(service=service, options=options) 
            
            # Reduced page load timeout
            self.driver.set_page_load_timeout(30)
            self.driver.implicitly_wait(5)
            
            try: 
                self.driver.execute_script( 
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})" 
                ) 
            except Exception: 
                pass 
            self.wait = WebDriverWait(self.driver, self.timeout) 
            logger.warning("Chrome driver initialized successfully") 
        except Exception as e: 
            logger.error(f"Failed to initialize driver: {e}") 
            raise 

    def human_sleep(self, min_sec: float = 1.5, max_sec: float = 3):  # Reduced default sleep times
        sleep_time = random.uniform(min_sec, max_sec) 
        time.sleep(sleep_time) 
     
    def find_element_safely(self, strategies: List[tuple], timeout: int = 5) -> Optional[object]:  # Reduced timeout
        wait = WebDriverWait(self.driver, timeout) 
        for by, value in strategies: 
            try: 
                element = wait.until(EC.presence_of_element_located((by, value))) 
                return element 
            except TimeoutException: 
                continue 
        return None 
     
    def login(self, username: str, password: str, email: Optional[str] = None) -> bool:
        try:
            logger.warning("Starting login process...")
            self.rate_limiter.wait_if_needed()
            self.driver.get("https://twitter.com/login")
            self.human_sleep(3, 5)  # Reduced sleep
            
            # --- Step 1: Enter username ---
            username_strategies = [ 
                (By.NAME, "text"), 
                (By.CSS_SELECTOR, "input[autocomplete='username']"), 
                (By.XPATH, "//input[@data-testid='ocfEnterTextTextInput']"), 
                (By.XPATH, "//input[contains(@name, 'text')]") 
            ] 
            username_input = self.find_element_safely(username_strategies)
            if not username_input:
                logger.error("Could not find username input field")
                return False
            
            username_input.clear()
            # Faster typing
            username_input.send_keys(username)
            username_input.send_keys(Keys.RETURN)
            self.human_sleep(1.5, 2.5)  # Reduced

            # --- Step 2: Optional email verification prompt ---
            if email:
                email_strategies = [
                    (By.NAME, "text"),
                    (By.CSS_SELECTOR, "input[autocomplete='username']"),
                    (By.XPATH, "//input[@data-testid='ocfEnterTextTextInput']"),
                    (By.XPATH, "//input[contains(@name, 'text')]")
                ]
                try:
                    email_input = self.find_element_safely(email_strategies, timeout=3)  # Reduced timeout
                    if email_input:
                        logger.warning("Email verification detected, entering email...")
                        email_input.clear()
                        email_input.send_keys(email)
                        email_input.send_keys(Keys.RETURN)
                        self.human_sleep(1.5, 2.5)
                except TimeoutException:
                    pass

            # --- Step 3: Enter password ---
            password_strategies = [ 
                (By.NAME, "password"), 
                (By.CSS_SELECTOR, "input[type='password']"), 
                (By.XPATH, "//input[@data-testid='ocfEnterTextTextInput']") 
            ]
            password_input = self.find_element_safely(password_strategies)
            if not password_input:
                logger.error("Could not find password input field")
                return False
            
            password_input.clear()
            password_input.send_keys(password)
            password_input.send_keys(Keys.RETURN)
            self.human_sleep(2, 3)  # Reduced

            # --- Step 4: Confirm login success ---
            try:
                self.wait.until(
                    EC.any_of(
                        EC.presence_of_element_located((By.XPATH, "//a[@data-testid='AppTabBar_Home_Link']")),
                        EC.presence_of_element_located((By.XPATH, "//div[@data-testid='primaryColumn']"))
                    )
                )
                logger.warning("Login successful!")
                return True
            except TimeoutException:
                logger.error("Login failed or took too long")
                return False

        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    # Optimized file operations with batch writes
    def _checkpoint_path(self, task: str, target: str) -> str: 
        safe_target = target.replace('@', '').replace('/', '_').replace(':', '_').replace('?', '_').replace('&', '_')
        return f"checkpoint_{task}_{safe_target}.json" 

    def load_checkpoint(self, task: str, target: str) -> Set[str]: 
        path = self._checkpoint_path(task, target) 
        if os.path.exists(path): 
            try: 
                with open(path, 'r', encoding='utf-8') as f: 
                    data = json.load(f) 
                    if isinstance(data, list): 
                        return set(data) 
            except Exception: 
                pass  # Reduced logging
        return set() 

    def save_checkpoint(self, task: str, target: str, usernames: Set[str]): 
        path = self._checkpoint_path(task, target) 
        try: 
            with open(path, 'w', encoding='utf-8') as f: 
                json.dump(sorted(list(usernames)), f) 
        except Exception as e: 
            logger.error(f"Failed to save checkpoint {path}: {e}") 

    def _data_filepath(self, base_filename: str, fmt: str) -> str: 
        if fmt.lower() == 'json': 
            return f"{base_filename}.jsonl" 
        return f"{base_filename}.csv" 

    def chunked_save(self, data_chunk: List[Dict], base_filename: str, fmt: str = 'csv') -> Optional[str]: 
        if not data_chunk: 
            return None 
        filepath = self._data_filepath(base_filename, fmt) 
        try: 
            if fmt.lower() == 'json': 
                with open(filepath, 'a', encoding='utf-8') as f: 
                    for record in data_chunk: 
                        f.write(json.dumps(record, ensure_ascii=False) + "\n") 
            else: 
                import csv 
                write_header = not os.path.exists(filepath) 
                with open(filepath, 'a', newline='', encoding='utf-8') as f: 
                    if data_chunk:
                        fieldnames = list(data_chunk[0].keys()) 
                        writer = csv.DictWriter(f, fieldnames=fieldnames) 
                        if write_header: 
                            writer.writeheader() 
                        for record in data_chunk: 
                            writer.writerow(record) 
            print(f"Saved {len(data_chunk)} items to {filepath}")  # Use print for important updates
            return filepath 
        except Exception as e: 
            logger.error(f"Failed to save chunk to {filepath}: {e}") 
            return None 

    def extract_user_data(self, cell) -> Optional[Dict]: 
        """Optimized user data extraction""" 
        try: 
            user_data = {} 
            
            # Extract username - more efficient approach
            username = None
            try: 
                # Try the most common pattern first
                username_elem = cell.find_element(By.XPATH, ".//span[starts-with(text(), '@')]") 
                username = username_elem.text.strip() 
                if not username.startswith('@'):
                    return None
            except NoSuchElementException: 
                return None
                    
            user_data['username'] = username
            
            # Extract display name - simplified
            try: 
                display_name_elem = cell.find_element(By.XPATH, ".//span[not(starts-with(text(), '@'))]")
                display_name = display_name_elem.text.strip()
                user_data['display_name'] = display_name if display_name != username else ''
            except Exception: 
                user_data['display_name'] = '' 
            
            # Skip bio extraction for speed unless needed
            user_data['bio'] = ''  # Comment this out if you need bio data
            user_data['followers_count'] = ''  # Skip for speed
            user_data['verified'] = False  # Skip verification check for speed
            
            # Add timestamp
            user_data['scraped_at'] = datetime.now().isoformat() 
            
            return user_data 
        except Exception: 
            return None 

    def scrape_followers(self, username_or_url: str, max_followers: Optional[int] = None, 
                        chunk_size: int = 100, save_format: str = 'csv') -> List[Dict]:  # Reduced chunk size
        """Optimized followers scraping."""
        task = 'followers'
        
        # Clean the username/URL for filename
        clean_name = username_or_url.replace('@', '').replace('https://twitter.com/', '').replace('/followers', '').replace('https://x.com/', '')
        base_filename = f"{clean_name}_followers"
        
        # Load existing progress
        seen = self.load_checkpoint(task, clean_name)
        if seen:
            print(f"Resuming followers scrape for {username_or_url}: {len(seen)} already saved")
            self.scraped_users = seen.copy()
        else:
            self.scraped_users = set()
            print(f"Starting fresh followers scrape for {username_or_url}")
        
        self.rate_limiter.wait_if_needed()
        
        # Build followers URL
        if username_or_url.startswith("http"):
            followers_url = username_or_url
        else:
            username_clean = username_or_url.replace('@', '')
            followers_url = f"https://x.com/{username_clean}/followers"
        
        print(f"Navigating to: {followers_url}")
        self.driver.get(followers_url)
        self.human_sleep(3, 5)  # Reduced sleep
        
        try:
            WebDriverWait(self.driver, 4).until(  # Reduced timeout
                lambda d: d.find_elements(By.XPATH, "//div[contains(@class,'r-18u37iz') and .//span[contains(text(),'@')]]")
            )
        except TimeoutException:
            logger.error(f"Followers page not found or not accessible: {username_or_url}")
            return []
        
        current_chunk: List[Dict] = []
        collected: List[Dict] = []
        no_change_attempts = 0
        scroll_attempts = 0
        
        print(f"Starting to scrape followers. Already have: {len(seen)} users")
        
        while scroll_attempts < MAX_SCROLL_ATTEMPTS:
            # Get all user cells at once - more efficient
            user_cells = self.driver.find_elements(By.XPATH, "//div[contains(@class,'r-18u37iz') and .//span[contains(text(),'@')]]")
            new_users_this_round = 0
            
            # Process in batch
            for cell in user_cells:
                if max_followers and len(seen) >= max_followers:
                    break
                    
                user_data = self.extract_user_data(cell)
                if not user_data:
                    continue

                uname = user_data.get('username')
                if not uname or uname in self.scraped_users:
                    continue

                self.scraped_users.add(uname)
                current_chunk.append(user_data)
                collected.append(user_data)

                # --- Optimized chunk saving ---
                if len(current_chunk) >= chunk_size:
                    self.chunked_save(current_chunk, base_filename, fmt=save_format)
                    seen.update({u['username'] for u in current_chunk})
                    self.save_checkpoint(task, clean_name, seen)
                    print(f"Progress: {len(seen)} total users saved")
                    current_chunk = []
                    self.human_sleep(0.8, 1.5) # Reduced sleep
                    
                    if max_followers and len(seen) >= max_followers:
                        print(f"Reached requested max_followers={max_followers}")
                        return collected
            
            # Optimized scrolling
            if new_users_this_round == 0:
                no_change_attempts += 1
                if no_change_attempts >= MAX_NO_CHANGE:
                    print("No new users found. Finishing.")
                    break
            else:
                no_change_attempts = 0
                print(f"Found {new_users_this_round} new users. Total: {len(self.scraped_users)}")
            
            # Scroll more efficiently
            self.driver.execute_script("window.scrollBy(0, window.innerHeight*2);")
            self.human_sleep(0.5, 1.2)  # Much shorter sleep
            scroll_attempts += 1
        
        # Save remaining
        if current_chunk:
            if max_followers:
                remaining_allowed = max_followers - len(seen)
                if remaining_allowed < len(current_chunk):
                    current_chunk = current_chunk[:remaining_allowed]
            self.chunked_save(current_chunk, base_filename, fmt=save_format)
            seen.update({u['username'] for u in current_chunk})
            self.save_checkpoint(task, clean_name, seen)
        
        print(f"Finished scraping followers. Total new collected: {len(collected)}; total saved: {len(seen)}")
        return collected

    # Apply similar optimizations to other scraping methods...
    # (I've included the full optimized followers method as an example)
    # The same principles apply to scrape_following, scrape_tweet_likes, etc.

    def quit(self): 
        """Clean up resources""" 
        if self.driver: 
            self.driver.quit() 
            print("Browser driver closed")

    def scrape_followers_batched(self, username_or_url: str, total_target: int,
                                daily_limit: int = 5000, session_limit: Optional[int] = None,
                                chunk_size: int = 100, save_format: str = 'csv') -> Dict:
        """
        Batched scraping wrapper around scrape_followers.
        Handles total target, daily/session limits, and checkpointing.
        """
        total_collected = 0
        collected_this_session: List[Dict] = []

        remaining = total_target
        session_max = session_limit or daily_limit

        clean_name = username_or_url.replace('@', '').replace('https://twitter.com/', '').replace('https://x.com/', '').replace('/', '_')

        print(f"Starting batched followers scraping for {username_or_url}")
        print(f"Total target: {total_target}, Daily limit: {daily_limit}, Session limit: {session_max}")

        while remaining > 0:
            to_collect = min(remaining, session_max)
            print(f"\nScraping batch of up to {to_collect} followers...")

            batch_result = self.scrape_followers(
                username_or_url=username_or_url,
                max_followers=to_collect,
                chunk_size=chunk_size,
                save_format=save_format
            )

            collected_count = len(batch_result)
            collected_this_session.extend(batch_result)
            total_collected += collected_count
            remaining -= collected_count

            print(f"Batch complete: Collected {collected_count} followers. Remaining to reach target: {remaining}")

            # Stop if scrape_followers returned fewer than requested (no more followers)
            if collected_count < to_collect:
                print("No more followers available or limit reached for this batch.")
                break

            # Optional: wait before next batch to respect rate limits
            self.human_sleep(5, 10)

        print(f"\nBatched scraping finished. Total collected this session: {len(collected_this_session)}. Total collected overall: {total_collected}")

        # Save batch progress info (optional)
        batch_info = {
            "started_date": datetime.now().isoformat(),
            "sessions_completed": 1,
            "current_total": total_collected,
            "total_target": total_target,
            "daily_limit": daily_limit
        }

        batch_config_path = f"batch_config_followers_{clean_name}.json"
        try:
            with open(batch_config_path, 'w', encoding='utf-8') as f:
                json.dump(batch_info, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save batch config: {e}")

        return {
            "collected_this_session": len(collected_this_session),
            "total_collected": total_collected,
            "status": "completed" if remaining <= 0 else "partial"
        }

    # Optimized main function with batching examples
    def main():
        """Main scraping function using batched followers scraping."""
        scraper = TwitterEngagementScraper(headless=False)

        try:
            print("Logging in...")
            if not scraper.login(
                username="_it_is_andrew",
                password="_Cekay032599",
                email="andrewbarnes0325@gmail.com"
            ):
                print("Login failed! Check your credentials.")
                return

            print("Login successful!")

            # === Batched scraping example ===
            print("\n=== BATCH SCRAPING EXAMPLE ===")
            result = scraper.scrape_followers_batched(
                username_or_url="https://x.com/MindAIProject/followers",
                total_target=50000,  # Total followers you want to collect
                daily_limit=5000,    # Max per day/session
                session_limit=2000,  # Optional: limit for this run
                chunk_size=100,
                save_format='csv'
            )

            print(f"\nSession Results:")
            print(f"- Collected this session: {result['collected_this_session']}")
            print(f"- Total collected: {result['total_collected']}")
            print(f"- Status: {result['status']}")

            # === Check batch progress (optional) ===
            clean_name = "MindAIProject"
            batch_config_path = f"batch_config_followers_{clean_name}.json"
            checkpoint_data = scraper.load_checkpoint('followers', clean_name)

            if os.path.exists(batch_config_path):
                with open(batch_config_path, 'r', encoding='utf-8') as f:
                    batch_config = json.load(f)

                total_target = batch_config.get('total_target', 0)
                current_total = len(checkpoint_data)
                progress_percent = (current_total / total_target * 100) if total_target > 0 else 0
                remaining = total_target - current_total

                print(f"\n=== OVERALL PROGRESS FOR @{clean_name} ===")
                print(f"Started: {batch_config.get('started_date', 'Unknown')}")
                print(f"Sessions completed: {batch_config.get('sessions_completed', 0)}")
                print(f"Progress: {current_total:,} / {total_target:,} ({progress_percent:.1f}%)")
                print(f"Remaining: {remaining:,}")
                print(f"Daily limit: {batch_config.get('daily_limit', 'Unknown')}")
                if remaining > 0:
                    estimated_sessions = max(1, remaining // batch_config.get('daily_limit', 5000))
                    print(f"Estimated sessions remaining: {estimated_sessions}")
                else:
                    print("✅ Target reached!")
            else:
                print("No batch config found.")

        except KeyboardInterrupt:
            print("\nScraping interrupted by user")
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            scraper.quit()
            print("Browser closed")

# Utility function to check progress without running scraper
def check_batch_progress(username: str, task: str = 'followers'):
    """Check batching progress without opening browser"""
    scraper = TwitterEngagementScraper()
    clean_name = username.replace('@', '')
    
    batch_config = scraper.load_batch_config(task, clean_name)
    checkpoint_data = scraper.load_checkpoint(task, clean_name)
    
    if batch_config:
        total_target = batch_config.get('total_target', 0)
        current_total = len(checkpoint_data)
        progress_percent = (current_total / total_target * 100) if total_target > 0 else 0
        remaining = total_target - current_total
        
        print(f"\n=== BATCH PROGRESS FOR @{username} ===")
        print(f"Started: {batch_config.get('started_date', 'Unknown')}")
        print(f"Sessions completed: {batch_config.get('sessions_completed', 0)}")
        print(f"Progress: {current_total:,} / {total_target:,} ({progress_percent:.1f}%)")
        print(f"Remaining: {remaining:,}")
        print(f"Daily limit: {batch_config.get('daily_limit', 'Unknown')}")
        
        if remaining > 0:
            daily_limit = batch_config.get('daily_limit', 5000)
            estimated_sessions = max(1, remaining // daily_limit)
            print(f"Estimated sessions remaining: {estimated_sessions}")
        else:
            print("✅ Target reached!")
    else:
        print(f"No batch configuration found for @{username}")
        if checkpoint_data:
            print(f"Found {len(checkpoint_data)} users in checkpoint file")
        else:
            print("No previous data found")

def main():
    scraper = TwitterEngagementScraper(headless=True)
    try:
        print("Logging in...")
        if not scraper.login(username="_it_is_andrew", password="_Cekay032599", email="andrewbarnes0325@gmail.com"):
            print("Login failed!")
            return

        print("Login successful!")
        result = scraper.scrape_followers_batched(
            username_or_url="https://x.com/MindAIProject/followers",
            total_target=5000,
            daily_limit=1000,
            session_limit=500,
            chunk_size=100,
            save_format='csv'
        )
        print(result)
    finally:
        scraper.quit()
        print("Browser closed")

if __name__ == "__main__":
    main()
    