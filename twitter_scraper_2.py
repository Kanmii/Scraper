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


# ================= Scraper Configuration =================
chunk_size = 50
max_scroll_attempt = 200  
max_no_change = 15
sleep_between_scrolls = (2, 4)  # seconds
sleep_after_chunk = (3, 6)     # seconds
max_followers = 2000            # per session, None for unlimited
max_following = 1000            # per session, None for unlimited
max_likes = 1000                # per session, None for unlimited
max_retweets = 1000             # per session, None for unlimited
max_tweets = 2000               # per session, None for unlimited


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
        self.rate_limiter = RateLimiter(max_requests=3, time_window=60) 
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
            options.add_argument("--disable-software-rasterizer")
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
        
    def wait_for_new_content(self, current_count, selector="//div[@data-testid='UserCell']", timeout=10):
        """Wait for new content to load instead of fixed sleep"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            new_count = len(self.driver.find_elements(By.XPATH, selector))
            if new_count > current_count:
                return True
            time.sleep(0.5)
        return False
    
    def wait_for_modal_content(self, current_count, timeout=8):
        """Specific method for waiting in modal contexts"""
        try:
            modal = self.driver.find_element(By.XPATH, "//div[@role='dialog']")
            start_time = time.time()
            while time.time() - start_time < timeout:
                new_count = len(modal.find_elements(By.XPATH, ".//div[@data-testid='UserCell']"))
                if new_count > current_count:
                    return True
                time.sleep(0.5)
        except:
            # Fallback to regular content waiting
            return self.wait_for_new_content(current_count, timeout=timeout)
        return False
     
    def find_element_safely(self, strategies: List[tuple], timeout: int = 3) -> Optional[object]: 
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
     
    def login(self, username: str, password: str, email: Optional[str] = None) -> bool:
        try:
            logger.info("Starting login process...")
            self.rate_limiter.wait_if_needed()
            self.driver.get("https://twitter.com/login")
            self.human_sleep(5, 8)
            
            # --- Step 1: Enter username ---
            username_strategies = [ 
                (By.XPATH, "//input[@data-testid='ocfEnterTextTextInput']"),  # Most specific - try first
                (By.CSS_SELECTOR, "input[autocomplete='username']"),         # Moderately specific
                (By.XPATH, "//input[contains(@name, 'text')]"),              # Less specific
                (By.NAME, "text")                                            # Generic fallback
]
            username_input = self.find_element_safely(username_strategies)
            if not username_input:
                logger.error("Could not find username input field")
                return False
            
            username_input.clear()
            username_input.send_keys(username)
            username_input.send_keys(Keys.RETURN)
            self.human_sleep(1, 2)

            # --- Step 2: Optional email verification prompt ---
            if email:
                email_strategies = [
                    (By.XPATH, "//input[@data-testid='ocfEnterTextTextInput']"),  # Most specific - try first
                    (By.CSS_SELECTOR, "input[autocomplete='username']"),         # Moderately specific
                    (By.XPATH, "//input[contains(@name, 'text')]"),              # Less specific
                    (By.NAME, "text")
                ]
                try:
                    email_input = self.find_element_safely(email_strategies, timeout=5)
                    if email_input:
                        logger.info("Email verification detected, entering email...")
                        email_input.clear()
                        email_input.send_keys(email)
                        email_input.send_keys(Keys.RETURN)
                        self.human_sleep(1, 2)
                except TimeoutException:
                    logger.info("No email verification step detected, continuing login...")

            # --- Step 3: Enter password ---
            password_strategies = [  
                (By.CSS_SELECTOR, "input[type='password']"), 
                (By.NAME, "password"),
                (By.XPATH, "//input[@data-testid='ocfEnterTextTextInput']")
            ]
            password_input = self.find_element_safely(password_strategies)
            if not password_input:
                logger.error("Could not find password input field")
                return False
            
            password_input.clear()
            password_input.send_keys(password)
            password_input.send_keys(Keys.RETURN)
            self.human_sleep(2, 4)

            # --- Step 4: Confirm login success ---
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
                    if data_chunk:
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

    def extract_user_data(self, cell) -> Optional[Dict]:
        """Extract user data based on the actual X.com HTML structure"""
        try:
            user_data = {}
            
            # Extract username from the profile link href
            try:
                # Look for profile links with href="/username" pattern
                profile_link = cell.find_element(By.XPATH, ".//a[starts-with(@href, '/') and not(contains(@href, '/search')) and not(contains(@href, '/followers')) and not(contains(@href, '/following')) and not(contains(@href, '/status'))]")
                href = profile_link.get_attribute('href')
                
                if href:
                    # Extract username from href (e.g., "/byte_og" -> "byte_og")
                    username = href.strip('/').split('/')[-1]
                    if username and len(username) > 0:
                        user_data['username'] = '@' + username
                        print(f"DEBUG: Found username: @{username}")
                    else:
                        print("DEBUG: Empty username extracted")
                        return None
                else:
                    print("DEBUG: No href found in profile link")
                    return None
                    
            except NoSuchElementException:
                print("DEBUG: No profile link found")
                return None
            
            # Extract display name - look for the span with the actual name (not @username)
            try:
                # The display name is in a span that doesn't contain @ symbol
                display_name_spans = cell.find_elements(By.XPATH, ".//span[contains(@class, 'css-1jxf684') and not(starts-with(text(), '@')) and not(text()='Follow') and string-length(text()) > 0]")
                
                display_name = ""
                for span in display_name_spans:
                    text = span.text.strip()
                    # Take the first substantial text that looks like a display name
                    if text and len(text) > 0 and text != 'Follow' and not text.startswith('@'):
                        display_name = text
                        break
                        
                user_data['display_name'] = display_name
                print(f"DEBUG: Found display name: '{display_name}'")
                
            except Exception as e:
                print(f"DEBUG: Error getting display name: {e}")
                user_data['display_name'] = ''
            
            # Extract bio - look for the overflow hidden div with bio text
            try:
                # Bio is in a div with overflow: hidden style
                bio_div = cell.find_element(By.XPATH, ".//div[contains(@style, 'overflow: hidden')]")
                bio_text = bio_div.text.strip()
                
                # Clean up the bio text - remove the display name and username if they appear
                if bio_text:
                    # Remove display name from bio if it appears at the start
                    if user_data.get('display_name') and bio_text.startswith(user_data['display_name']):
                        bio_text = bio_text[len(user_data['display_name']):].strip()
                    
                    # Remove username from bio if it appears
                    username_clean = user_data.get('username', '').replace('@', '')
                    if username_clean and username_clean in bio_text:
                        bio_text = bio_text.replace(username_clean, '').strip()
                    
                    # Remove "Follow" if it appears at the end
                    if bio_text.endswith('Follow'):
                        bio_text = bio_text[:-6].strip()
                    
                    user_data['bio'] = bio_text
                    print(f"DEBUG: Found bio: '{bio_text[:50]}...'")
                else:
                    user_data['bio'] = ''
                    
            except NoSuchElementException:
                user_data['bio'] = ''
                print("DEBUG: No bio found")
            
            # Check for verification badge
            try:
                cell.find_element(By.XPATH, ".//svg[@data-testid='icon-verified']")
                user_data['verified'] = True
            except NoSuchElementException:
                user_data['verified'] = False
            
            # Extract follower count if visible (might not be available in follower lists)
            user_data['followers_count'] = ''
            
            # Add timestamp
            user_data['scraped_at'] = datetime.now().isoformat()
            
            print(f"DEBUG: Final extracted data: {user_data}")
            return user_data
            
        except Exception as e:
            print(f"DEBUG: Error in extract_user_data: {e}")
            return None
    
    
    def scrape_followers(self, username_or_url: str, max_followers: Optional[int] = None, 
                    chunk_size: int = 50, save_format: str = 'csv') -> List[Dict]:
        """Scrape followers with chunked saving and checkpointing (updated for new X/Twitter markup)."""
        task = 'followers'
        
        # Clean the username/URL for filename
        clean_name = username_or_url.replace('@', '').replace('https://twitter.com/', '').replace('/followers', '').replace('https://x.com/', '')
        base_filename = f"{clean_name}_followers"
        
        # Load existing progress
        seen = self.load_checkpoint(task, clean_name)
        if seen:
            logger.info(f"Resuming followers scrape for {username_or_url}: {len(seen)} already saved")
            self.scraped_users = seen.copy()
        else:
            self.scraped_users = set()
            logger.info(f"Starting fresh followers scrape for {username_or_url}")
        
        self.rate_limiter.wait_if_needed()
        
        # Build followers URL
        if username_or_url.startswith("http"):
            followers_url = username_or_url
        else:
            username_clean = username_or_url.replace('@', '')
            # Use twitter.com instead of x.com for consistency with login
            followers_url = f"https://twitter.com/{username_clean}/followers"
            
        logger.info(f"Navigating to: {followers_url}")
        self.driver.get(followers_url)
        self.human_sleep(5, 8)
        
        print(f"DEBUG: Current URL after navigation: {self.driver.current_url}")
        print(f"DEBUG: Page title: {self.driver.title}")
        print(f"DEBUG: Page source preview: {self.driver.page_source[:500]}")
        
        try:
            # Wait for page to load - try multiple indicators
            WebDriverWait(self.driver, 15).until(
                lambda d: len(d.find_elements(By.XPATH, "//div[@data-testid='UserCell']")) > 0 or
                        len(d.find_elements(By.XPATH, "//span[contains(text(), 'This account is private')]")) > 0 or
                        len(d.find_elements(By.XPATH, "//span[contains(text(), \"Doesn't follow anyone\")]")) > 0 or
                        len(d.find_elements(By.XPATH, "//span[contains(text(), 'Something went wrong')]")) > 0
            )
            
            # Check for various error conditions
            if self.driver.find_elements(By.XPATH, "//span[contains(text(), 'This account is private')]"):
                logger.error(f"Account is private: {username_or_url}")
                return []
            
            if self.driver.find_elements(By.XPATH, "//span[contains(text(), \"Doesn't follow anyone\")]"):
                logger.error(f"Account has no followers: {username_or_url}")
                return []
                
            if self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Something went wrong')]"):
                logger.error(f"Twitter error page detected: {username_or_url}")
                return []
                
        except TimeoutException:
            logger.error(f"Followers page not found or not accessible: {username_or_url}")
            print(f"DEBUG: Current URL: {self.driver.current_url}")
            print(f"DEBUG: Page title: {self.driver.title}")
            return []
        
        current_chunk: List[Dict] = []
        collected: List[Dict] = []
        
        # Enhanced scrolling parameters
        scroll_attempts = 0
        no_change_count = 0
        max_scroll_attempts = 200
        patience_threshold = 15
        
        logger.info(f"Starting to scrape followers. Already have: {len(seen)} users")
        
        while scroll_attempts < max_scroll_attempts:
            current_user_count = len(self.driver.find_elements(By.XPATH, "//div[@data-testid='UserCell']"))
            
            # Enhanced scrolling strategies
            if scroll_attempts % 4 == 0:
                # Aggressive scroll to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            elif scroll_attempts % 4 == 1:
                # Scroll by viewport height
                self.driver.execute_script("window.scrollBy(0, window.innerHeight);")
            elif scroll_attempts % 4 == 2:
                # Try scrolling within modal if present
                try:
                    modal = self.driver.find_element(By.XPATH, "//div[@role='dialog']")
                    self.driver.execute_script("arguments[0].scrollTop += 1000", modal)
                except:
                    self.driver.execute_script("window.scrollBy(0, 500);")
            else:
                # Small incremental scroll
                self.driver.execute_script("window.scrollBy(0, 200);")
            
            # Wait for new content to load
            time.sleep(random.uniform(2, 4))
            
            # Get current user cells
            user_cells = self.driver.find_elements(By.XPATH, "//div[@data-testid='UserCell']")
            new_user_count = len(user_cells)
            new_users_this_round = 0
            
            print(f"DEBUG: Found {len(user_cells)} user cells on attempt {scroll_attempts}")
            if len(user_cells) > 0 and scroll_attempts % 10 == 0:  # Only show HTML preview every 10 attempts
                print(f"DEBUG: First cell HTML preview: {user_cells[0].get_attribute('outerHTML')[:200]}")
            
            # Process user cells
            for cell in user_cells:
                try:
                    user_data = self.extract_user_data(cell)
                    if user_data:
                        print(f"DEBUG: Extracted user data: {user_data}")
                    else:
                        print("DEBUG: No user data extracted from cell")
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
                new_users_this_round += 1
                
                # Save chunk if needed
                if len(current_chunk) >= chunk_size:
                    if max_followers:
                        remaining_allowed = max_followers - len(seen)
                        if remaining_allowed <= 0:
                            current_chunk = []
                            break
                        if len(current_chunk) > remaining_allowed:
                            current_chunk = current_chunk[:remaining_allowed]
                    
                    self.chunked_save(current_chunk, base_filename, fmt=save_format)
                    seen.update({u['username'] for u in current_chunk})
                    self.save_checkpoint(task, clean_name, seen)
                    logger.info(f"Progress: {len(seen)} total users saved")
                    current_chunk = []
                    self.human_sleep(3, 6)
                    
                    if max_followers and len(seen) >= max_followers:
                        logger.info(f"Reached requested max_followers={max_followers}")
                        return collected
            
            # Check if we got new content
            if new_user_count > current_user_count:
                no_change_count = 0
                logger.info(f"Progress: {new_user_count} users loaded, {new_users_this_round} new users processed")
            else:
                no_change_count += 1
                logger.info(f"No new content loaded (attempt {no_change_count}/{patience_threshold})")
                
            if no_change_count >= patience_threshold:
                logger.info("No new content after several attempts. Stopping.")
                break
                
            scroll_attempts += 1
            
            # Extended pause every 20 scrolls to avoid rate limits
            if scroll_attempts % 20 == 0:
                wait_time = random.uniform(45, 90)
                logger.info(f"Rate limiting pause after {scroll_attempts} scrolls... waiting {wait_time:.1f} seconds")
                time.sleep(wait_time)
            
            # Check if we've hit our target
            if max_followers and len(seen) + len(current_chunk) >= max_followers:
                logger.info(f"Approaching limit: {len(seen) + len(current_chunk)} users collected")
                break
        
        # Save remaining data
        if current_chunk:
            if max_followers:
                remaining_allowed = max_followers - len(seen)
                if remaining_allowed < len(current_chunk):
                    current_chunk = current_chunk[:remaining_allowed]
            self.chunked_save(current_chunk, base_filename, fmt=save_format)
            seen.update({u['username'] for u in current_chunk})
            self.save_checkpoint(task, clean_name, seen)
        
        logger.info(f"Finished scraping followers. Total new collected this run: {len(collected)}; total saved: {len(seen)}")
        return collected
    
    def scrape_followers_with_retry(self, username_or_url: str, max_retries: int = 3, **kwargs):
        """Wrapper method with retry logic"""
        for attempt in range(max_retries):
            try:
                result = self.scrape_followers(username_or_url, **kwargs)
                if result is not None:  # Success
                    return result
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    self.human_sleep(10, 15)  # Wait before retry
        return []
    
    def multi_session_scrape(self, username: str, total_target: int = 2000, session_limit: int = 300):
        """Scrape across multiple sessions to get more complete data"""
        all_scraped = set()
        session_count = 0
        base_filename = f"{username.replace('@', '')}_multi_session"
        
        while len(all_scraped) < total_target and session_count < 5:  # Max 5 sessions
            session_count += 1
            logger.info(f"Starting session {session_count}")
            
            # Don't restart browser for first session
            if session_count > 1:
                self.quit()
                wait_time = random.uniform(300, 900)  # 5-15 min break
                logger.info(f"Waiting {wait_time/60:.1f} minutes between sessions...")
                time.sleep(wait_time)
                
                self.setup_driver(headless=self.driver is None)
                if not self.login(self.username, self.password, self.email):
                    logger.error("Login failed in multi-session scrape")
                    break
            
            session_data = self.scrape_followers(username, max_followers=session_limit)
            new_users = {user['username'] for user in session_data if user.get('username')}
            
            previously_unseen = new_users - all_scraped
            all_scraped.update(new_users)
            
            logger.info(f"Session {session_count}: {len(previously_unseen)} new users, total unique: {len(all_scraped)}")
            
            if len(previously_unseen) < 20:  # Diminishing returns
                logger.info("Diminishing returns detected, ending multi-session scrape")
                break
        
        return list(all_scraped)
    
    def scrape_active_followers(self, username: str, recent_tweets: int = 5):
        """Get followers who recently interacted with the account"""
        active_followers = set()
        username_clean = username.replace('@', '')
        
        logger.info(f"Scraping active followers for {username}")
        
        # Get recent tweets first
        tweets = self.scrape_user_tweets(username, max_tweets=recent_tweets)
        
        if not tweets:
            logger.warning(f"No tweets found for {username}")
            return []
        
        for i, tweet in enumerate(tweets, 1):
            tweet_url = tweet.get('tweet_url')
            if not tweet_url:
                continue
                
            logger.info(f"Processing tweet {i}/{len(tweets)}: {tweet_url}")
            
            try:
                # Get likers (more likely to be followers)
                likers = self.scrape_tweet_likes(tweet_url, max_likes=50)
                active_followers.update({user['username'] for user in likers if user.get('username')})
                
                # Brief pause between likes and retweets
                time.sleep(random.uniform(30, 60))
                
                # Get retweeters
                retweeters = self.scrape_tweet_retweets(tweet_url, max_retweets=25)
                active_followers.update({user['username'] for user in retweeters if user.get('username')})
                
                logger.info(f"Found {len(active_followers)} active users so far")
                
                # Longer pause between tweets
                if i < len(tweets):
                    time.sleep(random.uniform(60, 120))
                    
            except Exception as e:
                logger.error(f"Error processing tweet {tweet_url}: {e}")
                continue
        
        # Save active followers
        if active_followers:
            active_data = [{'username': username, 'scraped_at': datetime.now().isoformat()} 
                        for username in active_followers]
            self.chunked_save(active_data, f"{username_clean}_active_followers", fmt='csv')
        
        return list(active_followers)


    def scrape_following(self, username_or_url: str, max_following: Optional[int] = None, 
                        chunk_size: int = 50, save_format: str = 'csv') -> List[Dict]: 
        """Scrape users that the target account is following.""" 
        task = 'following' 
        clean_name = username_or_url.replace('@', '').replace('https://twitter.com/', '').replace('/following', '').replace('https://x.com/', '')
        base_filename = f"{clean_name}_following" 
        
        # Load existing progress
        seen = self.load_checkpoint(task, clean_name) 
        if seen: 
            logger.info(f"Resuming following scrape for {username_or_url}: {len(seen)} already saved") 
            self.scraped_users = seen.copy()
        else:
            self.scraped_users = set()
            logger.info(f"Starting fresh following scrape for {username_or_url}")
            
        self.rate_limiter.wait_if_needed() 
        if username_or_url.startswith("http"): 
            following_url = username_or_url 
        else: 
            username_clean = username_or_url.replace('@', '')
            following_url = f"https://x.com/{username_clean}/following"
        logger.info(f"Navigating to: {following_url}")
        self.driver.get(following_url) 
        self.human_sleep(5, 8) 
        
        try: 
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//div[@data-testid='UserCell']"))) 
        except TimeoutException: 
            logger.error(f"Following page not found or not accessible: {username_or_url}") 
            return [] 
        
        current_chunk: List[Dict] = [] 
        collected: List[Dict] = [] 
        no_change_attempts = 0 
        max_no_change = 8
        scroll_attempts = 0
        max_scroll_attempts = 100
        
        logger.info(f"Starting to scrape following. Already have: {len(seen)} users")
        
        while scroll_attempts < max_scroll_attempts: 
            user_cells = self.driver.find_elements(By.XPATH, "//div[@data-testid='UserCell']") 
            new_users_this_round = 0
            
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
                new_users_this_round += 1
                
                if len(current_chunk) >= chunk_size: 
                    if max_following: 
                        already_saved = len(seen) 
                        remaining_allowed = max_following - already_saved 
                        if remaining_allowed <= 0: 
                            logger.info("Reached maximum following limit")
                            current_chunk = [] 
                            break 
                        if len(current_chunk) > remaining_allowed: 
                            current_chunk = current_chunk[:remaining_allowed] 
                    
                    self.chunked_save(current_chunk, base_filename, fmt=save_format) 
                    seen.update({u['username'] for u in current_chunk}) 
                    self.save_checkpoint(task, clean_name, seen) 
                    logger.info(f"Progress: {len(seen)} total users saved")
                    current_chunk = [] 
                    self.human_sleep(2, 4)
                    
                    if max_following and len(seen) >= max_following: 
                        logger.info(f"Reached requested max_following={max_following}") 
                        return collected 
            
            current_user_count = len(self.driver.find_elements(By.XPATH, "//div[@data-testid='UserCell']"))
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            if not self.wait_for_new_content(current_user_count, timeout=5):
                no_change_attempts += 1
            else:
                no_change_attempts = 0
            scroll_attempts += 1
            
            if new_users_this_round == 0: 
                no_change_attempts += 1 
                logger.info(f"No new following loaded (attempt {no_change_attempts}/{max_no_change})") 
                if no_change_attempts >= max_no_change: 
                    logger.info("No new users loaded for several attempts. Finishing following scraping.") 
                    break 
            else: 
                no_change_attempts = 0 
                logger.info(f"Found {new_users_this_round} new users in this scroll. Total scraped: {len(self.scraped_users)}")
            
            if max_following and len(seen) + len(current_chunk) >= max_following: 
                logger.info(f"Reached limit while scrolling: requested {max_following}") 
                break 
        
        if current_chunk: 
            if max_following: 
                already_saved = len(seen) 
                remaining_allowed = max_following - already_saved 
                if remaining_allowed < len(current_chunk): 
                    current_chunk = current_chunk[:remaining_allowed] 
            self.chunked_save(current_chunk, base_filename, fmt=save_format) 
            seen.update({u['username'] for u in current_chunk}) 
            self.save_checkpoint(task, clean_name, seen) 
        
        logger.info(f"Finished scraping following. Total new collected this run: {len(collected)}; total saved: {len(seen)}") 
        return collected

    def scrape_tweet_likes(self, tweet_url: str, max_likes: Optional[int] = None, 
                           chunk_size: int = 50, save_format: str = 'csv') -> List[Dict]: 
        """Scrape users who liked a particular tweet (modal) with chunked saving and checkpoints.""" 
        task = 'likes' 
        safe_target = tweet_url.replace('https://', '').replace('/', '_').replace(':', '_').replace('?', '_').replace('&', '_')
        base_filename = f"{safe_target}_likes" 

        # Load existing progress
        seen = self.load_checkpoint(task, safe_target) 
        if seen: 
            logger.info(f"Resuming likes scrape for {tweet_url}: {len(seen)} already saved") 
            self.scraped_users = seen.copy()
        else:
            self.scraped_users = set()
            logger.info(f"Starting fresh likes scrape for {tweet_url}")

        self.rate_limiter.wait_if_needed() 
        self.driver.get(tweet_url) 
        self.human_sleep(5, 8) 

        like_strategies = [ 
            (By.CSS_SELECTOR, "a[href*='/likes']"),                                                           # Most direct and fast
            (By.XPATH, "//div[@data-testid='like']//ancestor::div[contains(@role, 'button')]//following-sibling::a"), # Specific data-testid
            (By.XPATH, "//a[contains(@href, '/likes') and contains(@role, 'link')]"),                        # Multiple conditions
            (By.XPATH, "//span[text()='Liked by']/../..")  
    ] 

        likes_link = self.find_element_safely(like_strategies, timeout=10) 
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

        # For modals, check content within the modal
        current_user_count = len(self.driver.find_elements(By.XPATH, "//div[@data-testid='UserCell']"))
        if not self.wait_for_new_content(current_user_count, timeout=3):
            # Brief fallback sleep only if no new content
            time.sleep(1)

        try: 
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//div[@data-testid='UserCell']"))) 
        except TimeoutException: 
            logger.error("Likes modal did not load") 
            return [] 

        current_chunk: List[Dict] = [] 
        collected: List[Dict] = [] 
        no_change_attempts = 0 
        max_no_change = 8
        scroll_attempts = 0
        max_scroll_attempts = 50

        logger.info(f"Starting to scrape likes. Already have: {len(seen)} users")

        while scroll_attempts < max_scroll_attempts: 
            user_cells = self.driver.find_elements(By.XPATH, "//div[@data-testid='UserCell']") 
            new_users_this_round = 0
            
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
                new_users_this_round += 1

                if len(current_chunk) >= chunk_size: 
                    if max_likes: 
                        already_saved = len(seen) 
                        remaining_allowed = max_likes - already_saved 
                        if remaining_allowed <= 0: 
                            logger.info("Reached maximum likes limit")
                            current_chunk = [] 
                            break 
                        if len(current_chunk) > remaining_allowed: 
                            current_chunk = current_chunk[:remaining_allowed] 

                    self.chunked_save(current_chunk, base_filename, fmt=save_format) 
                    seen.update({u['username'] for u in current_chunk}) 
                    self.save_checkpoint(task, safe_target, seen) 
                    logger.info(f"Progress: {len(seen)} total users saved")
                    current_chunk = [] 
                    self.human_sleep(2, 4) 

                    if max_likes and len(seen) >= max_likes: 
                        logger.info(f"Reached requested max_likes={max_likes}") 
                        return collected 

            # Scroll within the modal
            try: 
                modal = self.driver.find_element(By.XPATH, "//div[@role='dialog']") 
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", modal) 
            except Exception: 
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);") 

            current_user_count = len(self.driver.find_elements(By.XPATH, "//div[@data-testid='UserCell']"))
            if not self.wait_for_new_content(current_user_count, timeout=3):
                # Brief fallback sleep only if no new content
                time.sleep(1)
            scroll_attempts += 1

            if new_users_this_round == 0: 
                no_change_attempts += 1 
                logger.info(f"No new likers loaded (attempt {no_change_attempts}/{max_no_change})") 
                if no_change_attempts >= max_no_change: 
                    logger.info("No new likers loaded. Finishing likes scraping.") 
                    break 
            else: 
                no_change_attempts = 0 
                logger.info(f"Found {new_users_this_round} new likers in this scroll. Total scraped: {len(self.scraped_users)}")

            if max_likes and len(seen) + len(current_chunk) >= max_likes: 
                logger.info(f"Reached limit while scrolling likers: requested {max_likes}") 
                break 

        # Save remaining data
        if current_chunk: 
            if max_likes: 
                already_saved = len(seen) 
                remaining_allowed = max_likes - already_saved 
                if remaining_allowed < len(current_chunk): 
                    current_chunk = current_chunk[:remaining_allowed] 
            self.chunked_save(current_chunk, base_filename, fmt=save_format) 
            seen.update({u['username'] for u in current_chunk}) 
            self.save_checkpoint(task, safe_target, seen) 

        logger.info(f"Finished scraping likes. Total new collected this run: {len(collected)}; total saved: {len(seen)}") 
        return collected

    def scrape_tweet_retweets(self, tweet_url: str, max_retweets: Optional[int] = None, 
                             chunk_size: int = 50, save_format: str = 'csv') -> List[Dict]: 
        """Scrape users who retweeted a particular tweet.""" 
        task = 'retweets' 
        safe_target = tweet_url.replace('https://', '').replace('/', '_').replace(':', '_').replace('?', '_').replace('&', '_')
        base_filename = f"{safe_target}_retweets" 

        # Load existing progress
        seen = self.load_checkpoint(task, safe_target) 
        if seen: 
            logger.info(f"Resuming retweets scrape for {tweet_url}: {len(seen)} already saved") 
            self.scraped_users = seen.copy()
        else:
            self.scraped_users = set()
            logger.info(f"Starting fresh retweets scrape for {tweet_url}")

        self.rate_limiter.wait_if_needed() 
        self.driver.get(tweet_url) 
        self.human_sleep(5, 8) 

        retweet_strategies = [ 
            (By.CSS_SELECTOR, "a[href*='/retweets']"),                                                        # Fastest - direct CSS selector
            (By.XPATH, "//div[@data-testid='retweet']//ancestor::div[contains(@role, 'button')]//following-sibling::a"), # Specific data-testid
            (By.XPATH, "//a[contains(@href, '/retweets') and contains(@role, 'link')]")                      # Multi-condition fallback
        ] 

        retweets_link = self.find_element_safely(retweet_strategies, timeout=10) 
        if not retweets_link: 
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
        no_change_attempts = 0 
        max_no_change = 8
        scroll_attempts = 0
        max_scroll_attempts = 50

        logger.info(f"Starting to scrape retweets. Already have: {len(seen)} users")

        while scroll_attempts < max_scroll_attempts: 
            user_cells = self.driver.find_elements(By.XPATH, "//div[@data-testid='UserCell']") 
            new_users_this_round = 0
            
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
                new_users_this_round += 1

                if len(current_chunk) >= chunk_size: 
                    if max_retweets: 
                        already_saved = len(seen) 
                        remaining_allowed = max_retweets - already_saved 
                        if remaining_allowed <= 0: 
                            logger.info("Reached maximum retweets limit")
                            current_chunk = [] 
                            break 
                        if len(current_chunk) > remaining_allowed: 
                            current_chunk = current_chunk[:remaining_allowed] 

                    self.chunked_save(current_chunk, base_filename, fmt=save_format) 
                    seen.update({u['username'] for u in current_chunk}) 
                    self.save_checkpoint(task, safe_target, seen) 
                    logger.info(f"Progress: {len(seen)} total users saved")
                    current_chunk = [] 
                    self.human_sleep(2, 4) 

                    if max_retweets and len(seen) >= max_retweets: 
                        logger.info(f"Reached requested max_retweets={max_retweets}") 
                        return collected 

            # Scroll within the modal
            try: 
                modal = self.driver.find_element(By.XPATH, "//div[@role='dialog']") 
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", modal) 
            except Exception: 
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);") 

            current_user_count = len(self.driver.find_elements(By.XPATH, "//div[@data-testid='UserCell']"))
            if not self.wait_for_new_content(current_user_count, timeout=3):
                # Brief fallback sleep only if no new content
                time.sleep(1)
            scroll_attempts += 1

            if new_users_this_round == 0: 
                no_change_attempts += 1 
                logger.info(f"No new retweeters loaded (attempt {no_change_attempts}/{max_no_change})") 
                if no_change_attempts >= max_no_change: 
                    logger.info("No new retweeters loaded. Finishing retweets scraping.") 
                    break 
            else: 
                no_change_attempts = 0 
                logger.info(f"Found {new_users_this_round} new retweeters in this scroll. Total scraped: {len(self.scraped_users)}")

            if max_retweets and len(seen) + len(current_chunk) >= max_retweets: 
                logger.info(f"Reached limit while scrolling retweeters: requested {max_retweets}") 
                break 

        # Save remaining data
        if current_chunk: 
            if max_retweets: 
                already_saved = len(seen) 
                remaining_allowed = max_retweets - already_saved 
                if remaining_allowed < len(current_chunk): 
                    current_chunk = current_chunk[:remaining_allowed] 
            self.chunked_save(current_chunk, base_filename, fmt=save_format) 
            seen.update({u['username'] for u in current_chunk}) 
            self.save_checkpoint(task, safe_target, seen) 

        logger.info(f"Finished scraping retweets. Total new collected this run: {len(collected)}; total saved: {len(seen)}") 
        return collected

    def scrape_user_tweets(self, username_or_url: str, max_tweets: Optional[int] = None, 
                          chunk_size: int = 50, save_format: str = 'csv') -> List[Dict]: 
        """Scrape tweets from a user's profile.""" 
        task = 'tweets' 
        clean_name = username_or_url.replace('@', '').replace('https://twitter.com/', '').replace('https://x.com/', '')
        base_filename = f"{clean_name}_tweets" 
        
        # For tweets, we track tweet IDs instead of usernames
        seen_tweets = self.load_checkpoint(task, clean_name) 
        if seen_tweets: 
            logger.info(f"Resuming tweets scrape for {username_or_url}: {len(seen_tweets)} already saved") 
        else:
            logger.info(f"Starting fresh tweets scrape for {username_or_url}")
            
        self.rate_limiter.wait_if_needed() 
        if username_or_url.startswith("http"): 
            profile_url = username_or_url 
        else: 
            username_clean = username_or_url.replace('@', '')
            profile_url = f"https://twitter.com/{username_clean}" 
            
        logger.info(f"Navigating to: {profile_url}")
        self.driver.get(profile_url) 
        self.human_sleep(5, 8) 
        
        try: 
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//article[@data-testid='tweet']"))) 
        except TimeoutException: 
            logger.error(f"Profile page not found or no tweets accessible: {username_or_url}") 
            return [] 
        
        current_chunk: List[Dict] = [] 
        collected: List[Dict] = [] 
        no_change_attempts = 0 
        max_no_change = 8
        scroll_attempts = 0
        max_scroll_attempts = 100
        
        logger.info(f"Starting to scrape tweets. Already have: {len(seen_tweets)} tweets")
        
        while scroll_attempts < max_scroll_attempts: 
            tweet_articles = self.driver.find_elements(By.XPATH, "//article[@data-testid='tweet']") 
            new_tweets_this_round = 0
            
            for article in tweet_articles: 
                try: 
                    tweet_data = self.extract_tweet_data(article) 
                except Exception as e: 
                    logger.debug(f"extract_tweet_data error: {e}") 
                    tweet_data = None 
                
                if not tweet_data: 
                    continue 
                
                tweet_id = tweet_data.get('tweet_id') 
                if not tweet_id or tweet_id in seen_tweets: 
                    continue 
                
                seen_tweets.add(tweet_id) 
                current_chunk.append(tweet_data) 
                collected.append(tweet_data) 
                new_tweets_this_round += 1
                
                if len(current_chunk) >= chunk_size: 
                    if max_tweets: 
                        already_saved = len(seen_tweets) - len(current_chunk)  # Subtract current chunk since we just added it
                        remaining_allowed = max_tweets - already_saved 
                        if remaining_allowed <= 0: 
                            logger.info("Reached maximum tweets limit")
                            current_chunk = [] 
                            break 
                        if len(current_chunk) > remaining_allowed: 
                            current_chunk = current_chunk[:remaining_allowed] 
                    
                    self.chunked_save(current_chunk, base_filename, fmt=save_format) 
                    self.save_checkpoint(task, clean_name, seen_tweets) 
                    logger.info(f"Progress: {len(seen_tweets)} total tweets saved")
                    current_chunk = [] 
                    self.human_sleep(2, 4)
                    
                    if max_tweets and len(seen_tweets) >= max_tweets: 
                        logger.info(f"Reached requested max_tweets={max_tweets}") 
                        return collected 
            
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);") 
            self.human_sleep(4, 6)
            scroll_attempts += 1
            
            if new_tweets_this_round == 0: 
                no_change_attempts += 1 
                logger.info(f"No new tweets loaded (attempt {no_change_attempts}/{max_no_change})") 
                if no_change_attempts >= max_no_change: 
                    logger.info("No new tweets loaded for several attempts. Finishing tweets scraping.") 
                    break 
            else: 
                no_change_attempts = 0 
                logger.info(f"Found {new_tweets_this_round} new tweets in this scroll. Total scraped: {len(seen_tweets)}")
            
            if max_tweets and len(seen_tweets) + len(current_chunk) >= max_tweets: 
                logger.info(f"Reached limit while scrolling: requested {max_tweets}") 
                break 
        
        if current_chunk: 
            if max_tweets: 
                already_saved = len(seen_tweets) - len(current_chunk)
                remaining_allowed = max_tweets - already_saved 
                if remaining_allowed < len(current_chunk): 
                    current_chunk = current_chunk[:remaining_allowed] 
            self.chunked_save(current_chunk, base_filename, fmt=save_format) 
            self.save_checkpoint(task, clean_name, seen_tweets) 
        
        logger.info(f"Finished scraping tweets. Total new collected this run: {len(collected)}; total saved: {len(seen_tweets)}") 
        return collected

    def extract_tweet_data(self, article) -> Optional[Dict]:
        """Extract tweet data from a tweet article element (updated for new X/Twitter HTML)."""
        try:
            tweet_data = {}

            # Extract tweet ID and URL
            try:
                tweet_link = article.find_element(By.XPATH, ".//a[contains(@href, '/status/')]")
                tweet_url = tweet_link.get_attribute('href')
                tweet_id = tweet_url.split('/status/')[-1].split('?')[0]
                tweet_data['tweet_id'] = tweet_id
                tweet_data['tweet_url'] = tweet_url
            except NoSuchElementException:
                return None

            # Extract tweet text
            try:
                tweet_text_elem = article.find_element(By.XPATH, ".//div[contains(@class,'r-bnwqim') and contains(@class,'r-18u37iz')]")
                tweet_data['text'] = tweet_text_elem.text.strip()
            except NoSuchElementException:
                tweet_data['text'] = ""

            # Extract username handle (starts with @)
            try:
                username_elem = article.find_element(By.XPATH, ".//span[contains(text(), '@')]")
                tweet_data['username'] = username_elem.text.strip().replace('@', '')
            except NoSuchElementException:
                tweet_data['username'] = ""

            # Extract display name
            try:
                display_name_elem = article.find_element(By.XPATH, ".//div[@dir='ltr']/span[contains(@class,'css-1jxf684')]")
                tweet_data['display_name'] = display_name_elem.text.strip()
            except NoSuchElementException:
                tweet_data['display_name'] = ""

            # Extract timestamp
            try:
                time_elem = article.find_element(By.XPATH, ".//time")
                tweet_data['timestamp'] = time_elem.get_attribute('datetime')
            except NoSuchElementException:
                tweet_data['timestamp'] = ""

            # Extract engagement metrics
            def get_metric(testid):
                try:
                    elem = article.find_element(By.XPATH, f".//div[@data-testid='{testid}']//span")
                    return elem.text.strip() or "0"
                except NoSuchElementException:
                    return "0"

            tweet_data['replies'] = get_metric('reply')
            tweet_data['retweets'] = get_metric('retweet')
            tweet_data['likes'] = get_metric('like')

            # Add scraping timestamp
            tweet_data['scraped_at'] = datetime.now().isoformat()

            return tweet_data

        except Exception as e:
            logger.debug(f"Error extracting tweet data: {e}")
            return None

    def quit(self): 
        """Clean up resources""" 
        if self.driver: 
            self.driver.quit() 
            logger.info("Browser driver closed")

# Example usage and utility functions
def main():
    """Enhanced usage of the Twitter scraper"""
    scraper = TwitterEngagementScraper(headless=False)
    
    try:
        # Login
        print("Logging in...")
        if not scraper.login(
            username="_it_is_andrew",
            password="_Cekay032599", 
            email="andrewbarnes0325@gmail.com"
        ):
            print("❌ Login failed!")
            return
        
        print("✅ Login successful!")
        target_account = "@MindAIProject"
        
        # Strategy 1: Enhanced single session (try first)
        print(f"\n🔄 Enhanced followers scraping for {target_account}...")
        followers = scraper.scrape_followers_with_retry(
            username_or_url=target_account,
            max_followers=2000,
            chunk_size=50,
            save_format='csv',
            max_retries=2
        )
        print(f"✅ Enhanced scrape: {len(followers)} new followers")
        
        # Strategy 2: Multi-session if first session was successful
        if len(followers) > 50:  # Only if first session worked well
            print(f"\n🔄 Multi-session scraping for {target_account}...")
            multi_followers = scraper.multi_session_scrape(
                username=target_account,
                total_target=1500,
                session_limit=400
            )
            print(f"✅ Multi-session: {len(multi_followers)} total unique followers")
        
        # Strategy 3: Active followers (always try this)
        print(f"\n🔄 Active followers scraping for {target_account}...")
        active_followers = scraper.scrape_active_followers(
            username=target_account,
            recent_tweets=3
        )
        print(f"✅ Active followers: {len(active_followers)} engaged users")
        
    except KeyboardInterrupt:
        print("\n⚠️ Scraping interrupted by user")
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        logger.error(f"Main execution error: {e}")
    finally:
        scraper.quit()
        print("🔚 Browser closed")

if __name__ == "__main__":
    main()