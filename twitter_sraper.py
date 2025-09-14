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
 
# Configure logging 
logging.basicConfig( 
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s', 
    handlers=[ 
        logging.FileHandler('twitter_engagement_scraper.log'), 
        logging.StreamHandler() 
    ] 
) 
logger = logging.getLogger(__name__) 
 
class RateLimiter: 
    """Simple rate limiter to avoid overwhelming the server""" 
    def __init__(self, max_requests: int = 5, time_window: int = 120): 
        self.max_requests = max_requests 
        self.time_window = time_window 
        self.requests = [] 
     
    def can_make_request(self) -> bool: 
        now = datetime.now() 
        self.requests = [req for req in self.requests  
                        if now - req < timedelta(seconds=self.time_window)] 
        return len(self.requests) < self.max_requests 
     
    def make_request(self) -> bool: 
        if self.can_make_request(): 
            self.requests.append(datetime.now()) 
            return True 
        return False 
     
    def wait_if_needed(self): 
        if not self.can_make_request(): 
            wait_time = self.time_window // 2 
            logger.warning(f"Rate limit reached. Waiting {wait_time} seconds...") 
            time.sleep(wait_time) 
 
class TwitterEngagementScraper: 
    def __init__(self, headless: bool = False, timeout: int = 15): 
        self.driver = None 
        self.wait = None 
        self.timeout = timeout 
        self.rate_limiter = RateLimiter(max_requests=3, time_window=180) 
        self.scraped_users = set() 
        self.setup_driver(headless) 
 
    def setup_driver(self, headless: bool): 
        """Setup Chrome driver with anti-detection measures""" 
        try: 
            options = Options() 
            options.add_argument("--start-maximized") 
            options.add_argument("--disable-blink-features=AutomationControlled") 
            options.add_argument("--disable-extensions") 
            options.add_argument("--disable-dev-shm-usage") 
            options.add_argument("--no-sandbox") 
            options.add_argument("--disable-gpu") 
            options.add_argument("--disable-web-security") 
            options.add_argument("--allow-running-insecure-content") 
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
            try: 
                self.driver.execute_script( 
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})" 
                ) 
            except Exception: 
                pass 
            self.wait = WebDriverWait(self.driver, self.timeout) 
            logger.info("Chrome driver initialized successfully") 
        except Exception as e: 
            logger.error(f"Failed to initialize driver: {e}") 
            raise 
 
    def human_sleep(self, min_sec: float = 3, max_sec: float = 7): 
        sleep_time = random.uniform(min_sec, max_sec) 
        time.sleep(sleep_time) 
     
    def find_element_safely(self, strategies: List[tuple], timeout: int = 10) -> Optional[object]: 
        wait = WebDriverWait(self.driver, timeout) 
        for by, value in strategies: 
            try: 
                element = wait.until(EC.presence_of_element_located((by, value))) 
                logger.debug(f"Found element using {by}: {value}") 
                return element 
            except TimeoutException: 
                logger.debug(f"Failed to find element using {by}: {value}") 
                continue 
        logger.error("Element not found with any strategy") 
        return None 
     
    def login(self, username: str, password: str) -> bool: 
        try: 
            logger.info("Starting login process...") 
            self.rate_limiter.wait_if_needed() 
            self.driver.get("https://twitter.com/login") 
            self.human_sleep(5, 8) 
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
            for char in username: 
                username_input.send_keys(char) 
                time.sleep(random.uniform(0.05, 0.15)) 
            username_input.send_keys(Keys.RETURN) 
            self.human_sleep(3, 5) 
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
            for char in password: 
                password_input.send_keys(char) 
                time.sleep(random.uniform(0.05, 0.15)) 
            password_input.send_keys(Keys.RETURN) 
            self.human_sleep(8, 12) 
            try: 
                self.wait.until( 
                    EC.any_of( 
                        EC.presence_of_element_located((By.XPATH, "//a[@data-testid='AppTabBar_Home_Link']")), 
                        EC.presence_of_element_located((By.XPATH, "//div[@data-testid='primaryColumn']")) 
                    ) 
                ) 
                logger.info("Login successful!") 
                return True 
            except TimeoutException: 
                logger.error("Login failed or took too long") 
                return False 
        except Exception as e: 
            logger.error(f"Login error: {e}") 
            return False 
 
    def _checkpoint_path(self, task: str, target: str) -> str: 
        safe_target = target.replace('@', '').replace('/', '_') 
        return f"checkpoint_{task}_{safe_target}.json" 
 
    def load_checkpoint(self, task: str, target: str) -> Set[str]: 
        path = self._checkpoint_path(task, target) 
        if os.path.exists(path): 
            try: 
                with open(path, 'r', encoding='utf-8') as f: 
                    data = json.load(f) 
                    if isinstance(data, list): 
                        return set(data) 
            except Exception as e: 
                logger.warning(f"Failed to load checkpoint {path}: {e}") 
        return set() 
 
    def save_checkpoint(self, task: str, target: str, usernames: Set[str]): 
        path = self._checkpoint_path(task, target) 
        try: 
            with open(path, 'w', encoding='utf-8') as f: 
                json.dump(sorted(list(usernames)), f, indent=2) 
            logger.debug(f"Checkpoint saved: {path} ({len(usernames)} users)") 
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
                    fieldnames = list(data_chunk[0].keys()) 
                    writer = csv.DictWriter(f, fieldnames=fieldnames) 
                    if write_header: 
                        writer.writeheader() 
                    for record in data_chunk: 
                        writer.writerow(record) 
            logger.info(f"Saved {len(data_chunk)} items to {filepath}") 
            return filepath 
        except Exception as e: 
            logger.error(f"Failed to save chunk to {filepath}: {e}") 
            return None 
 
    # ------------------------------- 
    # SCRAPER METHODS (moved inside class) 
    # ------------------------------- 
 
    def scrape_followers(self, username_or_url: str, max_followers: Optional[int] = None, 
                         chunk_size: int = 50, save_format: str = 'csv') -> List[Dict]: 
        """Scrape followers with chunked saving and checkpointing.""" 
        task = 'followers' 
        base_filename = f"{username_or_url}_followers" 
        seen = self.load_checkpoint(task, username_or_url) 
        if seen: 
            logger.info(f"Resuming followers scrape for {username_or_url}: {len(seen)} already saved") 
            self.scraped_users.update(seen) 
        self.rate_limiter.wait_if_needed() 
        if username_or_url.startswith("http"): 
            followers_url = username_or_url 
        else: 
            followers_url = f"https://twitter.com/{username_or_url}/followers" 
        self.driver.get(followers_url) 
        self.human_sleep(5, 8) 
        try: 
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//div[@data-testid='UserCell']"))) 
        except TimeoutException: 
            logger.error(f"Followers page not found or not accessible: {username_or_url}") 
            return [] 
        current_chunk: List[Dict] = [] 
        collected: List[Dict] = [] 
        last_seen_count = len(self.scraped_users) 
        no_change_attempts = 0 
        max_no_change = 5 
        while True: 
            user_cells = self.driver.find_elements(By.XPATH, "//div[@data-testid='UserCell']") 
            for cell in user_cells: 
                try: 
                    user_data = self.extract_user_data(cell) 
                except Exception as e: 
                    logger.debug(f"extract_user_data error: {e}") 
                    user_data = None 
                if not user_data: 
                    continue 
                uname = user_data.get('username') 
                if not uname or uname in self.scraped_users: 
                    continue 
                self.scraped_users.add(uname) 
                current_chunk.append(user_data) 
                collected.append(user_data) 
                if len(current_chunk) >= chunk_size: 
                    if max_followers: 
                        already_saved = len(seen) 
                        remaining_allowed = max_followers - already_saved 
                        if remaining_allowed <= 0: 
                            current_chunk = [] 
                            break 
                        if len(current_chunk) > remaining_allowed: 
                            current_chunk = current_chunk[:remaining_allowed] 
                    self.chunked_save(current_chunk, base_filename, fmt=save_format) 
                    seen.update({u['username'] for u in current_chunk}) 
                    self.save_checkpoint(task, username_or_url, seen) 
                    current_chunk = [] 
                    self.human_sleep(1, 3) 
                    if max_followers and len(seen) >= max_followers: 
                        logger.info(f"Reached requested max_followers={max_followers}") 
                        return collected 
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);") 
            self.human_sleep(3, 5) 
            if len(self.scraped_users) == last_seen_count: 
                no_change_attempts += 1 
                logger.info(f"No new followers loaded (attempt {no_change_attempts}/{max_no_change})") 
                if no_change_attempts >= max_no_change: 
                    logger.info("No new users loaded. Finishing followers scraping.") 
                    break 
            else: 
                last_seen_count = len(self.scraped_users) 
                no_change_attempts = 0 
            if max_followers and len(seen) + len(current_chunk) >= max_followers: 
                logger.info(f"Reached limit while scrolling: requested {max_followers}") 
                break 
        if current_chunk: 
            if max_followers: 
                already_saved = len(seen) 
                remaining_allowed = max_followers - already_saved 
                if remaining_allowed < len(current_chunk): 
                    current_chunk = current_chunk[:remaining_allowed] 
            self.chunked_save(current_chunk, base_filename, fmt=save_format) 
            seen.update({u['username'] for u in current_chunk}) 
            self.save_checkpoint(task, username_or_url, seen) 
        logger.info(f"Finished scraping followers. Total new collected this run: {len(collected)}; total saved: {len(seen)}") 
        return collected 
 
    def scrape_tweet_likes(self, tweet_url: str, max_likes: Optional[int] = None, 
                           chunk_size: int = 50, save_format: str = 'csv') -> List[Dict]: 
        """Scrape users who liked a particular tweet (modal) with chunked saving and checkpoints.""" 
        task = 'likes' 
        safe_target = tweet_url.replace('https://', '').replace('/', '_') 
        base_filename = f"{safe_target}_likes" 
 
        seen = self.load_checkpoint(task, safe_target) 
        if seen: 
            logger.info(f"Resuming likes scrape for {tweet_url}: {len(seen)} already saved") 
            self.scraped_users.update(seen) 
 
        self.rate_limiter.wait_if_needed() 
        self.driver.get(tweet_url) 
        self.human_sleep(5, 8) 
 
        like_strategies = [ 
            (By.XPATH, "//a[contains(@href, '/likes') and contains(@role, 'link')]"), 
            (By.CSS_SELECTOR, "a[href*='/likes']"), 
            (By.XPATH, "//span[text()='Liked by']/../..") 
        ] 
 
        likes_link = self.find_element_safely(like_strategies, timeout=7) 
        if not likes_link: 
            logger.error("Could not find likes link") 
            return [] 
 
        try: 
            ActionChains(self.driver).move_to_element(likes_link).click().perform() 
        except Exception: 
            try: 
                likes_link.click() 
            except Exception as e: 
                logger.error(f"Failed to open likes modal: {e}") 
                return [] 
 
        self.human_sleep(3, 5) 
 
        try: 
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//div[@data-testid='UserCell']"))) 
        except TimeoutException: 
            logger.error("Likes modal did not load") 
            return [] 
 
        current_chunk: List[Dict] = [] 
        collected: List[Dict] = [] 
        last_seen_count = len(self.scraped_users) 
        no_change_attempts = 0 
        max_no_change = 5 
 
        while True: 
            user_cells = self.driver.find_elements(By.XPATH, "//div[@data-testid='UserCell']") 
            for cell in user_cells: 
                try: 
                    user_data = self.extract_user_data(cell) 
                except Exception as e: 
                    logger.debug(f"extract_user_data error: {e}") 
                    user_data = None 
 
                if not user_data: 
                    continue 
 
                uname = user_data.get('username') 
                if not uname or uname in self.scraped_users: 
                    continue 
 
                self.scraped_users.add(uname) 
                current_chunk.append(user_data) 
                collected.append(user_data) 
 
                if len(current_chunk) >= chunk_size: 
                    if max_likes: 
                        already_saved = len(seen) 
                        remaining_allowed = max_likes - already_saved 
                        if remaining_allowed <= 0: 
                            current_chunk = [] 
                            break 
                        if len(current_chunk) > remaining_allowed: 
                            current_chunk = current_chunk[:remaining_allowed] 
 
                    self.chunked_save(current_chunk, base_filename, fmt=save_format) 
                    seen.update({u['username'] for u in current_chunk}) 
                    self.save_checkpoint(task, safe_target, seen) 
                    current_chunk = [] 
                    self.human_sleep(1, 3) 
 
                    if max_likes and len(seen) >= max_likes: 
                        logger.info(f"Reached requested max_likes={max_likes}") 
                        return collected 
 
            try: 
                modal = self.driver.find_element(By.XPATH, "//div[@role='dialog']") 
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", modal) 
            except Exception: 
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);") 
 
            self.human_sleep(2, 4) 
 
            if len(self.scraped_users) == last_seen_count: 
                no_change_attempts += 1 
                logger.info(f"No new likers loaded (attempt {no_change_attempts}/{max_no_change})") 
                if no_change_attempts >= max_no_change: 
                    logger.info("No new likers loaded. Finishing likes scraping.") 
                    break 
            else: 
                last_seen_count = len(self.scraped_users) 
                no_change_attempts = 0 
 
            if max_likes and len(seen) + len(current_chunk) >= max_likes: 
                logger.info(f"Reached limit while scrolling likers: requested {max_likes}") 
                break 
 
        if current_chunk: 
            if max_likes: 
                already_saved = len(seen) 
                remaining_allowed = max_likes - already_saved 
                if remaining_allowed < len(current_chunk): 
                    current_chunk = current_chunk[:remaining_allowed] 
            self.chunked_save(current_chunk, base_filename, fmt=save_format) 
            seen.update({u['username'] for u in current_chunk}) 
            self.save_checkpoint(task, safe_target, seen) 
 
        logger.info(f"Finished scraping likers. Total new collected this run: {len(collected)}; total saved: {len(seen)}") 
        return collected 
 
    def scrape_tweet_retweets(self, tweet_url: str, max_retweets: Optional[int] = None, 
                              chunk_size: int = 50, save_format: str = 'csv') -> List[Dict]: 
        """Scrape users who retweeted a particular tweet (modal) with chunked saving and checkpoints.""" 
        task = 'retweets' 
        safe_target = tweet_url.replace('https://', '').replace('/', '_') 
        base_filename = f"{safe_target}_retweets" 
 
        seen = self.load_checkpoint(task, safe_target) 
        if seen: 
            logger.info(f"Resuming retweets scrape for {tweet_url}: {len(seen)} already saved") 
            self.scraped_users.update(seen) 
 
        self.rate_limiter.wait_if_needed() 
        self.driver.get(tweet_url) 
        self.human_sleep(5, 8) 
 
        retweet_strategies = [ 
            (By.XPATH, "//a[contains(@href, '/retweets') and contains(@role, 'link')]"), 
            (By.CSS_SELECTOR, "a[href*='/retweets']"), 
            (By.XPATH, "//span[text()='Retweeted by']/../..") 
        ] 
 
        try: 
            retweets_link = self.find_element_safely(retweet_strategies, timeout=7) 
        except Exception: 
            retweets_link = None 
 
        if not retweets_link: 
            try: 
                retweets_link = self.driver.find_element(By.CSS_SELECTOR, "a[href*='/retweets']") 
            except Exception: 
                logger.error("Could not find retweets link") 
                return [] 
 
        try: 
            ActionChains(self.driver).move_to_element(retweets_link).click().perform() 
        except Exception: 
            try: 
                retweets_link.click() 
            except Exception as e: 
                logger.error(f"Failed to open retweets modal: {e}") 
                return [] 
 
        self.human_sleep(3, 5) 
 
        try: 
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//div[@data-testid='UserCell']"))) 
        except TimeoutException: 
            logger.error("Retweets modal did not load") 
            return [] 
 
        current_chunk: List[Dict] = [] 
        collected: List[Dict] = [] 
        last_seen_count = len(self.scraped_users) 
        no_change_attempts = 0 
        max_no_change = 5 
 
        while True: 
            user_cells = self.driver.find_elements(By.XPATH, "//div[@data-testid='UserCell']") 
            for cell in user_cells: 
                try: 
                    user_data = self.extract_user_data(cell) 
                except Exception as e: 
                    logger.debug(f"extract_user_data error: {e}") 
                    user_data = None 
 
                if not user_data: 
                    continue 
 
                uname = user_data.get('username') 
                if not uname or uname in self.scraped_users: 
                    continue 
 
                self.scraped_users.add(uname) 
                current_chunk.append(user_data) 
                collected.append(user_data) 
 
                if len(current_chunk) >= chunk_size: 
                    if max_retweets: 
                        already_saved = len(seen) 
                        remaining_allowed = max_retweets - already_saved 
                        if remaining_allowed <= 0: 
                            current_chunk = [] 
                            break 
                        if len(current_chunk) > remaining_allowed: 
                            current_chunk = current_chunk[:remaining_allowed] 
 
                    self.chunked_save(current_chunk, base_filename, fmt=save_format) 
                    seen.update({u['username'] for u in current_chunk}) 
                    self.save_checkpoint(task, safe_target, seen) 
                    current_chunk = [] 
                    self.human_sleep(1, 3) 
 
                    if max_retweets and len(seen) >= max_retweets: 
                        logger.info(f"Reached requested max_retweets={max_retweets}") 
                        return collected 
 
            try: 
                modal = self.driver.find_element(By.XPATH, "//div[@role='dialog']") 
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", modal) 
            except Exception: 
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);") 
 
            self.human_sleep(2, 4) 
 
            if len(self.scraped_users) == last_seen_count: 
                no_change_attempts += 1 
                logger.info(f"No new retweeters loaded (attempt {no_change_attempts}/{max_no_change})") 
                if no_change_attempts >= max_no_change: 
                    logger.info("No new retweeters loaded. Finishing retweets scraping.") 
                    break 
            else: 
                last_seen_count = len(self.scraped_users) 
                no_change_attempts = 0 
 
            if max_retweets and len(seen) + len(current_chunk) >= max_retweets: 
                logger.info(f"Reached limit while scrolling retweeters: requested {max_retweets}") 
                break 
 
        if current_chunk: 
            if max_retweets: 
                already_saved = len(seen) 
                remaining_allowed = max_retweets - already_saved 
                if remaining_allowed < len(current_chunk): 
                    current_chunk = current_chunk[:remaining_allowed] 
            self.chunked_save(current_chunk, base_filename, fmt=save_format) 
            seen.update({u['username'] for u in current_chunk}) 
            self.save_checkpoint(task, safe_target, seen) 
 
        logger.info(f"Finished scraping retweeters. Total new collected this run: {len(collected)}; total saved: {len(seen)}") 
        return collected 
 
    def extract_user_data(self, user_cell) -> Optional[Dict]: 
        """Extract user information from a user cell""" 
        try: 
            user_data = {} 
             
            # Extract username 
            username_strategies = [ 
                (By.XPATH, ".//span[starts-with(text(), '@')]"), 
                (By.XPATH, ".//div[@data-testid='User-Name']//span[contains(text(), '@')]"), 
                (By.CSS_SELECTOR, "[data-testid='User-Name'] span") 
            ] 
             
            username_element = None 
            for by, selector in username_strategies: 
                try: 
                    username_element = user_cell.find_element(by, selector) 
                    if username_element.text.startswith('@'): 
                        break 
                except NoSuchElementException: 
                    continue 
             
            if username_element: 
                user_data['username'] = username_element.text.replace('@', '') 
            else: 
                return None 
             
            # Extract display name 
            try: 
                display_name_element = user_cell.find_element( 
                    By.XPATH, ".//div[@data-testid='User-Name']//span[not(starts-with(text(), '@'))]" 
                ) 
                user_data['display_name'] = display_name_element.text 
            except NoSuchElementException: 
                user_data['display_name'] = user_data['username'] 
             
            # Extract bio 
            try: 
                bio_element = user_cell.find_element(By.XPATH, ".//div[@data-testid='UserDescription']") 
                user_data['bio'] = bio_element.text 
            except NoSuchElementException: 
                user_data['bio'] = "" 
             
            # Extract follower count (if visible) 
            try: 
                followers_element = user_cell.find_element(By.XPATH, ".//span[contains(text(), 'followers')]") 
                user_data['followers_text'] = followers_element.text 
            except NoSuchElementException: 
                user_data['followers_text'] = "" 
             
            # Check if verified 
            try: 
                user_cell.find_element(By.XPATH, ".//svg[@data-testid='verificationBadge']") 
                user_data['verified'] = True 
            except NoSuchElementException: 
                user_data['verified'] = False 
             
            user_data['scraped_at'] = datetime.now().isoformat() 
             
            return user_data 
             
        except Exception as e: 
            logger.warning(f"Failed to extract user data: {e}") 
            return None 
 
    def save_data(self, data: List[Dict], filename: str = None, format: str = 'csv'): 
        """Save scraped data to file""" 
        if not filename: 
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") 
            filename = f"twitter_engagement_data_{timestamp}" 
         
        try: 
            if format.lower() == 'json': 
                filepath = f"{filename}.json" 
                with open(filepath, 'w', encoding='utf-8') as f: 
                    json.dump(data, f, indent=2, ensure_ascii=False) 
                 
            elif format.lower() == 'csv': 
                import csv 
                filepath = f"{filename}.csv" 
                if data: 
                    with open(filepath, 'w', newline='', encoding='utf-8') as f: 
                        writer = csv.DictWriter(f, fieldnames=data[0].keys()) 
                        writer.writeheader() 
                        writer.writerows(data) 
             
            logger.info(f"Data saved to {filepath}") 
            return filepath 
             
        except Exception as e: 
            logger.error(f"Failed to save data: {e}") 
            return None 
 
    def quit(self): 
        """Cleanup and close the driver""" 
        if self.driver: 
            try: 
                self.driver.quit() 
                logger.info("Driver closed successfully") 
            except Exception as e: 
                logger.error(f"Error closing driver: {e}") 
            finally: 
                self.driver = None  # mark it as None to prevent double quit 
 
 
def main(): 
    """Main execution function""" 
    # Configuration 
    TWITTER_USERNAME = os.getenv('TWITTER_USERNAME', 'your_username') 
    TWITTER_PASSWORD = os.getenv('TWITTER_PASSWORD', 'your_password') 
     
    if TWITTER_USERNAME == 'your_username' or TWITTER_PASSWORD == 'your_password': 
        logger.error("Please set TWITTER_USERNAME and TWITTER_PASSWORD environment variables") 
        return 
     
    scraper = None 
    try: 
        # Initialize scraper 
        scraper = TwitterEngagementScraper(headless=False) 
         
        # Login 
        if not scraper.login(TWITTER_USERNAME, TWITTER_PASSWORD): 
            logger.error("Login failed. Exiting...") 
            return 
         
        # Example usage - choose what you want to scrape: 
         
        # 1. Scrape followers 
        target_user = "Ga__ke" 
        followers = scraper.scrape_followers(target_user, max_followers=50, chunk_size=25, save_format='csv') 
        if followers: 
            print(f"✅ Scraped {len(followers)} followers of @{target_user}") 
         
        # 2. Scrape following 
        # following = scraper.scrape_following(target_user, max_following=50, chunk_size=25, save_format='csv') 
        # if following: 
        #     print(f"✅ Scraped {len(following)} accounts followed by @{target_user}") 
         
       # 3. Scrape tweet likes 
        tweet_url = "https://x.com/Ga__ke/status/1898941696144252930" 
        likes = scraper.scrape_tweet_likes(tweet_url, max_likes=30, chunk_size=25, save_format='csv') 
        if likes: 
            print(f"✅ Scraped {len(likes)} users who liked the tweet") 
         
       # 4. Scrape tweet retweets 
        retweets = scraper.scrape_tweet_retweets(tweet_url, max_retweets=30, chunk_size=25, save_format='csv') 
        if retweets: 
            print(f"✅ Scraped {len(retweets)} users who retweeted") 
         
    except KeyboardInterrupt: 
        logger.info("Script interrupted by user") 
    except Exception as e: 
        logger.error(f"Unexpected error: {e}") 
    finally: 
        # Ensure the driver is cleaned up properly 
        if scraper and scraper.driver: 
            scraper.quit() 
 
if __name__ == "__main__": 
    main()