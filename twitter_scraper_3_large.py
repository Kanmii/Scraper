# import os 
# import time 
# import random 
# import json 
# import logging 
# import sqlite3
# import hashlib
# from datetime import datetime, timedelta 
# from typing import List, Dict, Optional, Set 
# from pathlib import Path
# import gzip
# import csv

# from selenium import webdriver 
# from selenium.webdriver.chrome.service import Service 
# from selenium.webdriver.common.by import By 
# from selenium.webdriver.chrome.options import Options 
# from selenium.webdriver.common.keys import Keys 
# from selenium.webdriver.support.ui import WebDriverWait 
# from selenium.webdriver.support import expected_conditions as EC 
# from selenium.common.exceptions import ( 
#     NoSuchElementException,  
#     TimeoutException,  
#     WebDriverException, 
#     ElementClickInterceptedException 
# ) 
# from selenium.webdriver.common.action_chains import ActionChains 
# from webdriver_manager.chrome import ChromeDriverManager 


# # ================= Million-Scale Configuration =================
# CHUNK_SIZE = 500   # Larger chunks for efficiency
# MAX_SCROLL_ATTEMPTS = 50  # Shorter sessions
# MAX_NO_CHANGE = 5  # Faster session termination
# SLEEP_BETWEEN_SCROLLS = (0.5, 1.5)  # Faster scrolling
# SLEEP_AFTER_CHUNK = (0.5, 1)  # Faster saves

# # Million-scale specific settings
# MEGA_ACCOUNT_THRESHOLD = 100000  # Followers count to trigger mega-mode
# MEGA_DAILY_LIMIT = 20000  # Higher daily limits for massive accounts
# MEGA_SESSION_DURATION = 45  # Minutes per session
# MEGA_MEMORY_LIMIT = 50000  # Users in memory before forced save
# DATABASE_BATCH_SIZE = 5000  # SQLite batch insert size
# SCROLL_HEIGHT_MULTIPLIER = 3  # New: scroll 3x window height per scroll

# # Configure logging for production
# logging.basicConfig( 
#     level=logging.WARNING,
#     format='%(asctime)s - %(levelname)s - %(message)s', 
#     handlers=[ 
#         logging.FileHandler('million_scale_scraper.log'), 
#         logging.StreamHandler() 
#     ] 
# ) 
# logger = logging.getLogger(__name__) 

# class DatabaseManager:
#     """SQLite database for million-scale user storage"""
    
#     def __init__(self, db_path: str):
#         self.db_path = db_path
#         self.connection = None
#         self.init_database()
    
#     def init_database(self):
#         """Initialize SQLite database with optimized schema"""
#         self.connection = sqlite3.connect(self.db_path)
#         self.connection.execute('''
#             CREATE TABLE IF NOT EXISTS users (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 username TEXT UNIQUE NOT NULL,
#                 display_name TEXT,
#                 bio TEXT,
#                 followers_count TEXT,
#                 verified INTEGER DEFAULT 0,
#                 scraped_at TEXT,
#                 source_account TEXT,
#                 task_type TEXT
#             )
#         ''')
        
#         # Create indexes for performance
#         self.connection.execute('CREATE INDEX IF NOT EXISTS idx_username ON users(username)')
#         self.connection.execute('CREATE INDEX IF NOT EXISTS idx_source_task ON users(source_account, task_type)')
#         self.connection.execute('CREATE INDEX IF NOT EXISTS idx_scraped_at ON users(scraped_at)')
        
#         self.connection.commit()
    
#     def batch_insert_users(self, users: List[Dict], source_account: str, task_type: str):
#         """Batch insert users for performance"""
#         if not users:
#             return 0
        
#         inserted = 0
#         cursor = self.connection.cursor()
        
#         for user in users:
#             try:
#                 cursor.execute('''
#                     INSERT OR IGNORE INTO users 
#                     (username, display_name, bio, followers_count, verified, scraped_at, source_account, task_type)
#                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)
#                 ''', (
#                     user.get('username', ''),
#                     user.get('display_name', ''),
#                     user.get('bio', ''),
#                     user.get('followers_count', ''),
#                     1 if user.get('verified', False) else 0,
#                     user.get('scraped_at', ''),
#                     source_account,
#                     task_type
#                 ))
#                 if cursor.rowcount > 0:
#                     inserted += 1
#             except sqlite3.IntegrityError:
#                 continue  # Duplicate username
        
#         self.connection.commit()
#         return inserted
    
#     def get_user_count(self, source_account: str, task_type: str) -> int:
#         """Get current user count for progress tracking"""
#         cursor = self.connection.cursor()
#         cursor.execute(
#             'SELECT COUNT(*) FROM users WHERE source_account = ? AND task_type = ?',
#             (source_account, task_type)
#         )
#         return cursor.fetchone()[0]
    
#     def get_existing_usernames(self, source_account: str, task_type: str) -> Set[str]:
#         """Get existing usernames for deduplication"""
#         cursor = self.connection.cursor()
#         cursor.execute(
#             'SELECT username FROM users WHERE source_account = ? AND task_type = ?',
#             (source_account, task_type)
#         )
#         return {row[0] for row in cursor.fetchall()}
    
#     def export_to_csv(self, filepath: str, source_account: str, task_type: str):
#         """Export data to compressed CSV"""
#         cursor = self.connection.cursor()
#         cursor.execute(
#             'SELECT username, display_name, bio, followers_count, verified, scraped_at FROM users WHERE source_account = ? AND task_type = ?',
#             (source_account, task_type)
#         )
        
#         with gzip.open(f"{filepath}.gz", 'wt', newline='', encoding='utf-8') as f:
#             writer = csv.writer(f)
#             writer.writerow(['username', 'display_name', 'bio', 'followers_count', 'verified', 'scraped_at'])
#             writer.writerows(cursor.fetchall())
    
#     def close(self):
#         if self.connection:
#             self.connection.close()

# class MillionScaleRateLimiter: 
#     """Advanced rate limiter with dynamic adjustment"""
    
#     def __init__(self, base_requests: int = 10, base_window: int = 60):
#         self.base_requests = base_requests
#         self.base_window = base_window
#         self.requests = []
#         self.penalty_until = None
#         self.consecutive_limits = 0
        
#     def can_make_request(self) -> bool: 
#         now = datetime.now()
        
#         # Check if we're in penalty period
#         if self.penalty_until and now < self.penalty_until:
#             return False
        
#         # Clear penalty
#         if self.penalty_until and now >= self.penalty_until:
#             self.penalty_until = None
#             self.consecutive_limits = 0
        
#         # Dynamic window adjustment based on consecutive limits
#         current_window = self.base_window * (1 + self.consecutive_limits * 0.5)
#         cutoff = now - timedelta(seconds=current_window)
#         self.requests = [req for req in self.requests if req > cutoff]
        
#         # Dynamic request limit
#         current_limit = max(3, self.base_requests - self.consecutive_limits * 2)
#         return len(self.requests) < current_limit
     
#     def make_request(self) -> bool: 
#         if self.can_make_request(): 
#             self.requests.append(datetime.now()) 
#             return True 
        
#         # Apply penalty for repeated rate limiting
#         self.consecutive_limits += 1
#         penalty_minutes = min(30, self.consecutive_limits * 5)
#         self.penalty_until = datetime.now() + timedelta(minutes=penalty_minutes)
        
#         logger.warning(f"Rate limit hit. Penalty: {penalty_minutes} minutes")
#         return False
     
#     def wait_if_needed(self): 
#         if not self.can_make_request(): 
#             if self.penalty_until:
#                 wait_time = (self.penalty_until - datetime.now()).total_seconds()
#                 logger.warning(f"In penalty period. Waiting {wait_time/60:.1f} minutes...")
#                 time.sleep(min(wait_time, 1800))  # Max 30 min wait
#             else:
#                 time.sleep(60)

# class MillionScaleTwitterScraper: 
#     def __init__(self, headless: bool = True, timeout: int = 8, reset_scraped_users: bool = False):
#         self.driver = None 
#         self.wait = None 
#         self.timeout = timeout 
#         self.rate_limiter = MillionScaleRateLimiter(base_requests=15, base_window=90)
#         self.scraped_users = set() 
#         self.session_start_time = datetime.now()
#         self.memory_users = []  # In-memory buffer
#         self.db_manager = None
#         self.reset_scraped_users = reset_scraped_users  # <-- new
#         self.setup_driver(headless) 


#     def setup_driver(self, headless: bool): 
#         """Production-optimized Chrome driver setup""" 
#         try: 
#             options = Options() 
            
#             # Production optimizations
#             options.add_argument("--no-sandbox") 
#             options.add_argument("--disable-dev-shm-usage") 
#             options.add_argument("--disable-gpu") 
#             options.add_argument("--disable-software-rasterizer")
#             options.add_argument("--disable-extensions") 
#             options.add_argument("--disable-logging")
#             options.add_argument("--disable-background-timer-throttling")
#             options.add_argument("--disable-backgrounding-occluded-windows")
#             options.add_argument("--disable-renderer-backgrounding")
#             options.add_argument("--disable-features=TranslateUI")
#             options.add_argument("--disable-ipc-flooding-protection")
#             options.add_argument("--disable-background-networking")
#             options.add_argument("--disable-default-apps")
#             options.add_argument("--disable-sync")
#             options.add_argument("--disable-component-update")
#             options.add_argument("--disable-web-security") 
#             options.add_argument("--allow-running-insecure-content") 
            
#             # Memory optimizations for long sessions
#             options.add_argument("--memory-pressure-off")
#             options.add_argument("--max_old_space_size=4096")
            
#             if headless: 
#                 options.add_argument("--headless=new") 
#                 options.add_argument("--window-size=1920,1080") 
#             else:
#                 options.add_argument("--start-maximized") 
            
#             # Rotating user agents for better stealth
#             user_agents = [
#                 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
#                 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
#                 "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
#             ]
#             options.add_argument(f"user-agent={random.choice(user_agents)}")
            
#             options.add_experimental_option("excludeSwitches", ["enable-automation"]) 
#             options.add_experimental_option('useAutomationExtension', False) 
            
#             service = Service(ChromeDriverManager().install()) 
#             self.driver = webdriver.Chrome(service=service, options=options) 
            
#             # Optimized timeouts for production
#             self.driver.set_page_load_timeout(45)
#             self.driver.implicitly_wait(3)
            
#             # Stealth modifications
#             try: 
#                 self.driver.execute_script( 
#                     "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})" 
#                 ) 
#             except Exception: 
#                 pass 
#             self.wait = WebDriverWait(self.driver, self.timeout) 
#             logger.warning("Production Chrome driver initialized successfully") 
#         except Exception as e: 
#             logger.error(f"Failed to initialize driver: {e}") 
#             raise 

#     def init_database(self, target_account: str, task_type: str):
#         """Initialize database for the scraping session"""
#         db_filename = f"million_scale_{task_type}_{target_account.replace('@', '').replace('/', '_')}.db"
#         self.db_manager = DatabaseManager(db_filename)
        
#         if not self.reset_scraped_users:
#             # Load existing usernames for deduplication
#             self.scraped_users = self.db_manager.get_existing_usernames(target_account, task_type)
#             logger.warning(f"Loaded {len(self.scraped_users)} existing users from database")
#         else:
#             # Start fresh
#             self.scraped_users = set()
#             logger.warning("Starting fresh: ignoring DB preload of usernames")

#     def human_sleep(self, min_sec: float = 0.5, max_sec: float = 2):  # Faster for production
#         sleep_time = random.uniform(min_sec, max_sec) 
#         time.sleep(sleep_time) 
     
#     def find_element_safely(self, strategies: List[tuple], timeout: int = 5) -> Optional[object]:
#         wait = WebDriverWait(self.driver, timeout) 
#         for by, value in strategies: 
#             try: 
#                 element = wait.until(EC.presence_of_element_located((by, value))) 
#                 return element 
#             except TimeoutException: 
#                 continue 
#         return None 

#     def login(self, username: str, password: str, email: Optional[str] = None) -> bool:
#         """Production login with better error handling"""
#         try:
#             logger.warning("Starting production login...")
#             self.rate_limiter.wait_if_needed()
#             self.driver.get("https://twitter.com/login")
#             self.human_sleep(3, 5)
            
#             # Username
#             username_strategies = [ 
#                 (By.NAME, "text"), 
#                 (By.CSS_SELECTOR, "input[autocomplete='username']"), 
#                 (By.XPATH, "//input[@data-testid='ocfEnterTextTextInput']"), 
#                 (By.XPATH, "//input[contains(@name, 'text')]") 
#             ] 
#             username_input = self.find_element_safely(username_strategies, timeout=8)
#             if not username_input:
#                 logger.error("Could not find username input field")
#                 return False
            
#             username_input.clear()
#             username_input.send_keys(username)
#             username_input.send_keys(Keys.RETURN)
#             self.human_sleep(2, 4)

#             # Email verification if needed
#             if email:
#                 email_strategies = [
#                     (By.NAME, "text"),
#                     (By.CSS_SELECTOR, "input[autocomplete='username']"),
#                     (By.XPATH, "//input[@data-testid='ocfEnterTextTextInput']"),
#                 ]
#                 try:
#                     email_input = self.find_element_safely(email_strategies, timeout=5)
#                     if email_input:
#                         logger.warning("Email verification detected")
#                         email_input.clear()
#                         email_input.send_keys(email)
#                         email_input.send_keys(Keys.RETURN)
#                         self.human_sleep(2, 4)
#                 except TimeoutException:
#                     pass

#             # Password
#             password_strategies = [ 
#                 (By.NAME, "password"), 
#                 (By.CSS_SELECTOR, "input[type='password']"), 
#                 (By.XPATH, "//input[@data-testid='ocfEnterTextTextInput']") 
#             ]
#             password_input = self.find_element_safely(password_strategies, timeout=8)
#             if not password_input:
#                 logger.error("Could not find password input field")
#                 return False
            
#             password_input.clear()
#             password_input.send_keys(password)
#             password_input.send_keys(Keys.RETURN)
#             self.human_sleep(5, 8)

#             # Verify login
#             try:
#                 self.wait.until(
#                     EC.any_of(
#                         EC.presence_of_element_located((By.XPATH, "//a[@data-testid='AppTabBar_Home_Link']")),
#                         EC.presence_of_element_located((By.XPATH, "//div[@data-testid='primaryColumn']"))
#                     )
#                 )
#                 logger.warning("Production login successful!")
#                 return True
#             except TimeoutException:
#                 logger.error("Login verification failed")
#                 return False

#         except Exception as e:
#             logger.error(f"Login error: {e}")
#             return False

#     def flush_memory_buffer(self, target_account: str, task_type: str) -> int:
#         """Flush in-memory buffer to database"""
#         if not self.memory_users:
#             return 0
        
#         inserted = self.db_manager.batch_insert_users(self.memory_users, target_account, task_type)
#         self.memory_users.clear()
#         return inserted

#     def check_session_limits(self) -> bool:
#         """Check if session should end due to time or memory limits"""
#         # Time limit check
#         session_duration = (datetime.now() - self.session_start_time).total_seconds() / 60
#         if session_duration > MEGA_SESSION_DURATION:
#             logger.warning(f"Session time limit reached: {session_duration:.1f} minutes")
#             return True
        
#         # Memory limit check
#         if len(self.memory_users) > MEGA_MEMORY_LIMIT:
#             logger.warning(f"Memory limit reached: {len(self.memory_users)} users in buffer")
#             return True
            
#         return False

#     def extract_user_data_optimized(self, cell) -> Optional[Dict]:
#         """Optimized for million-scale username collection only"""
#         try:
#             username_elem = cell.find_element(By.XPATH, ".//span[starts-with(text(), '@')]")
#             username = username_elem.text.strip()
#             if not username.startswith('@'):
#                 return None

#             return {
#                 'username': username,
#                 'scraped_at': datetime.now().isoformat()  # optional timestamp
#             }
#         except NoSuchElementException:
#             return None
#         except Exception:
#             return None


#     def scrape_mega_followers(self, username_or_url: str, total_target: int = 1000000,
#                             daily_limit: int = MEGA_DAILY_LIMIT, session_limit: int = None) -> Dict:
#         """
#         Optimized million-scale username-only scraper.
#         Accurately tracks collected usernames in real time.
#         """

#         task = 'followers'
#         clean_name = username_or_url.replace('@', '').replace('https://twitter.com/', '').replace('/followers', '').replace('https://x.com/', '')

#         # Initialize DB and load existing usernames
#         self.init_database(clean_name, task)
#         current_total = self.db_manager.get_user_count(clean_name, task)
#         remaining_needed = total_target - current_total

#         current_session_limit = min(session_limit or daily_limit, remaining_needed)
#         if current_session_limit <= 0:
#             print("Target already reached!")
#             return {'status': 'completed', 'collected_this_session': 0}

#         followers_url = username_or_url if username_or_url.startswith("http") else f"https://x.com/{clean_name}/followers"
#         self.driver.get(followers_url)
#         self.human_sleep(2, 4)

#         collected_this_session = 0
#         scroll_attempts = 0
#         no_new_found = 0

#         print(f"Starting session. DB has {current_total:,} users.")

#         while scroll_attempts < MAX_SCROLL_ATTEMPTS and collected_this_session < current_session_limit:
#             if self.check_session_limits():
#                 print("Session limits reached.")
#                 break

#             # Collect all user cells currently visible
#             user_cells = self.driver.find_elements(By.XPATH, "//div[contains(@class,'r-18u37iz') and .//span[starts-with(text(), '@')]]")
#             print(f"Found {len(user_cells)} user cells this scroll")

#             new_users_this_round = 0

#             for cell in user_cells:
#                 if collected_this_session >= current_session_limit:
#                     break

#                 user_data = self.extract_user_data_optimized(cell)
#                 if not user_data:
#                     continue

#                 username = user_data['username']
#                 if username in self.scraped_users:
#                     continue

#                 # Add username to memory and counters
#                 self.scraped_users.add(username)
#                 self.memory_users.append(user_data)
#                 collected_this_session += 1
#                 new_users_this_round += 1

#                 print(f"Collected: {username} | Total this session: {collected_this_session}")

#                 # Flush buffer to DB if needed
#                 if len(self.memory_users) >= DATABASE_BATCH_SIZE:
#                     inserted = self.flush_memory_buffer(clean_name, task)
#                     current_total += inserted
#                     progress_percent = (current_total / total_target) * 100
#                     print(f"Flushed {inserted} users | Total progress: {current_total:,}/{total_target:,} ({progress_percent:.1f}%)")
#                     self.human_sleep(0.5, 1)

#             # Check if no new users were found
#             if new_users_this_round == 0:
#                 no_new_found += 1
#                 if no_new_found >= MAX_NO_CHANGE:
#                     print("No new users found, ending session.")
#                     break
#             else:
#                 no_new_found = 0

#             # Scroll the page and wait for new users to load
#             self.driver.execute_script("window.scrollBy(0, window.innerHeight * 3);")
#             self.human_sleep(1.5, 2.5)
#             scroll_attempts += 1

#             # Apply rate limiting if needed
#             if not self.rate_limiter.make_request():
#                 self.rate_limiter.wait_if_needed()

#         # Final flush to DB
#         if self.memory_users:
#             inserted = self.flush_memory_buffer(clean_name, task)
#             current_total += inserted

#         final_progress_percent = (current_total / total_target) * 100
#         remaining = total_target - current_total

#         print(f"\nSession complete | Collected this session: {collected_this_session:,} | Total in DB: {current_total:,}")

#         if remaining <= 0:
#             export_path = f"{clean_name}_followers_complete"
#             self.db_manager.export_to_csv(export_path, clean_name, task)
#             print(f"Data exported to {export_path}.gz")

#         return {
#             'collected_this_session': collected_this_session,
#             'total_collected': current_total,
#             'progress_percent': final_progress_percent,
#             'remaining': remaining,
#             'status': 'completed' if remaining <= 0 else 'in_progress'
#         }


#     def quit(self): 
#         """Clean up resources""" 
#         if self.db_manager:
#             self.db_manager.close()
#         if self.driver: 
#             self.driver.quit() 
#             print("Production browser closed")

# def main_million_scale():
#     """Million-scale scraping example"""
#     scraper = MillionScaleTwitterScraper(headless=True, reset_scraped_users=True)  # Headless for production
    
#     try:
#         print("Production login...")
#         if not scraper.login(
#             username="_it_is_andrew",
#             password="_Cekay032599",
#             email="andrebarnes0325@gmail.com"
#         ):
#             print("Login failed!")
#             return
        
#         print("Login successful!")
        
#         # Million-scale scraping
#         result = scraper.scrape_mega_followers(
#             username_or_url="https://x.com/Ga__ke/followers",  # Account with millions
#             total_target=1000000,    # 1 million followers target
#             daily_limit=20000,       # 20K per session
#             session_limit=10000      # Optional: limit this specific run
#         )
        
#         print(f"\nMillion-scale results:")
#         print(f"- Status: {result['status']}")
#         print(f"- Collected this session: {result['collected_this_session']:,}")
#         print(f"- Total collected: {result['total_collected']:,}")
        
#     except KeyboardInterrupt:
#         print("\nMillion-scale scraping interrupted")
#     except Exception as e:
#         print(f"Error: {e}")
#     finally:
#         scraper.quit()

# if __name__ == "__main__":
#     main_million_scale()



import os
import time
import random
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
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from webdriver_manager.chrome import ChromeDriverManager
from pymongo import MongoClient, ASCENDING

# ================= Configuration =================
MAX_SCROLL_ATTEMPTS = 50
MAX_NO_CHANGE = 5
SLEEP_BETWEEN_SCROLLS = (0.5, 1.5)
MEGA_SESSION_DURATION = 45
MEGA_MEMORY_LIMIT = 50000
DATABASE_BATCH_SIZE = 5000

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('million_scale_scraper.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ---------------- MongoDB Manager ----------------
class MongoDBManager:
    def __init__(self, db_name='million_scale', collection_name='users', uri=None):
        if uri is None:
            uri = 'mongodb://localhost:27017'
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        # Ensure unique index on username
        self.collection.create_index([('username', ASCENDING)], unique=True)
        self.collection.create_index([('source_account', ASCENDING), ('task_type', ASCENDING)])
        self.collection.create_index([('scraped_at', ASCENDING)])

    def batch_insert_users(self, users: List[Dict]):
        if not users:
            return 0
        inserted_count = 0
        for user in users:
            try:
                self.collection.update_one(
                    {'username': user['username']},
                    {'$setOnInsert': user},
                    upsert=True
                )
                inserted_count += 1
            except Exception:
                continue
        return inserted_count

    def get_user_count(self, source_account: str, task_type: str) -> int:
        return self.collection.count_documents({'source_account': source_account, 'task_type': task_type})

    def get_existing_usernames(self, source_account: str, task_type: str) -> Set[str]:
        return {doc['username'] for doc in self.collection.find({'source_account': source_account, 'task_type': task_type}, {'username': 1})}

    def export_to_csv(self, filepath: str, source_account: str, task_type: str):
        import csv, gzip
        cursor = self.collection.find({'source_account': source_account, 'task_type': task_type})
        with gzip.open(f"{filepath}.gz", 'wt', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['username', 'display_name', 'bio', 'followers_count', 'verified', 'scraped_at'])
            for doc in cursor:
                writer.writerow([
                    doc.get('username', ''),
                    doc.get('display_name', ''),
                    doc.get('bio', ''),
                    doc.get('followers_count', ''),
                    doc.get('verified', 0),
                    doc.get('scraped_at', '')
                ])

# ---------------- Scraper ----------------
class MillionScaleTwitterScraper:
    def __init__(self, mongo_uri, headless=True, reset_scraped_users=True):
        self.driver = None
        self.wait = None
        self.scraped_users = set()
        self.memory_users = []
        self.session_start_time = datetime.now()
        self.reset_scraped_users = reset_scraped_users
        self.db_manager = MongoDBManager(uri=mongo_uri)
        self.setup_driver(headless)

    def setup_driver(self, headless: bool):
        options = Options()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-dev-shm-usage")
        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
        else:
            options.add_argument("--start-maximized")
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.implicitly_wait(3)
        self.wait = WebDriverWait(self.driver, 8)

    def human_sleep(self, min_sec=0.5, max_sec=2):
        time.sleep(random.uniform(min_sec, max_sec))

    def find_element_safely(self, strategies: List[tuple], timeout=5):
        wait = WebDriverWait(self.driver, timeout)
        for by, value in strategies:
            try:
                return wait.until(EC.presence_of_element_located((by, value)))
            except TimeoutException:
                continue
        return None

    def login(self, username: str, password: str, email: Optional[str] = None) -> bool:
        try:
            self.driver.get("https://twitter.com/login")
            self.human_sleep(3, 5)
            # Username input
            username_input = self.find_element_safely([(By.NAME, "text"), (By.CSS_SELECTOR, "input[autocomplete='username']")])
            if not username_input: return False
            username_input.send_keys(username, Keys.RETURN)
            self.human_sleep(2, 4)
            # Password input
            password_input = self.find_element_safely([(By.NAME, "password"), (By.CSS_SELECTOR, "input[type='password']")])
            if not password_input: return False
            password_input.send_keys(password, Keys.RETURN)
            self.human_sleep(5, 8)
            return True
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    def flush_memory_buffer(self, source_account: str, task_type: str):
        if not self.memory_users:
            return 0
        inserted = self.db_manager.batch_insert_users(self.memory_users)
        self.memory_users.clear()
        return inserted

    def check_session_limits(self):
        if (datetime.now() - self.session_start_time).total_seconds() / 60 > MEGA_SESSION_DURATION:
            return True
        if len(self.memory_users) > MEGA_MEMORY_LIMIT:
            return True
        return False

    def extract_user_data_optimized(self, cell):
        try:
            username_elem = cell.find_element(By.XPATH, ".//span[starts-with(text(), '@')]")
            username = username_elem.text.strip()
            if not username.startswith('@'):
                return None
            return {
                'username': username,
                'scraped_at': datetime.now().isoformat()
            }
        except Exception:
            return None

    def scrape_mega_followers(self, username_or_url: str, total_target: int = 1000000, session_limit: int = None):
        task = 'followers'
        clean_name = username_or_url.replace('@', '').replace('https://twitter.com/', '').replace('/followers', '')

        # Load existing usernames
        if not self.reset_scraped_users:
            self.scraped_users = self.db_manager.get_existing_usernames(clean_name, task)
        else:
            self.scraped_users = set()

        current_total = len(self.scraped_users)
        remaining_needed = total_target - current_total
        current_session_limit = min(session_limit or remaining_needed, remaining_needed)
        if current_session_limit <= 0:
            print("Target already reached!")
            return {'status': 'completed', 'collected_this_session': 0}

        self.driver.get(username_or_url if username_or_url.startswith("http") else f"https://x.com/{clean_name}/followers")
        self.human_sleep(2, 4)
        collected_this_session = 0
        scroll_attempts = 0
        no_new_found = 0

        print(f"Starting session. DB has {current_total:,} users.")

        while scroll_attempts < MAX_SCROLL_ATTEMPTS and collected_this_session < current_session_limit:
            if self.check_session_limits():
                break
            user_cells = self.driver.find_elements(By.XPATH, "//div[contains(@class,'r-18u37iz') and .//span[starts-with(text(), '@')]]")
            new_users_this_round = 0
            for cell in user_cells:
                if collected_this_session >= current_session_limit:
                    break
                user_data = self.extract_user_data_optimized(cell)
                if not user_data:
                    continue
                username = user_data['username']
                if username in self.scraped_users:
                    continue
                self.scraped_users.add(username)
                self.memory_users.append(user_data)
                collected_this_session += 1
                new_users_this_round += 1
                print(f"Collected: {username} | Total this session: {collected_this_session}")

                if len(self.memory_users) >= DATABASE_BATCH_SIZE:
                    self.flush_memory_buffer(clean_name, task)
            if new_users_this_round == 0:
                no_new_found += 1
                if no_new_found >= MAX_NO_CHANGE:
                    break
            else:
                no_new_found = 0
            self.driver.execute_script("window.scrollBy(0, window.innerHeight * 3);")
            self.human_sleep(1.5, 2.5)
            scroll_attempts += 1

        if self.memory_users:
            self.flush_memory_buffer(clean_name, task)
        current_total = self.db_manager.get_user_count(clean_name, task)
        print(f"\nSession complete | Collected this session: {collected_this_session:,} | Total in DB: {current_total:,}")
        return {'collected_this_session': collected_this_session, 'total_collected': current_total, 'status': 'completed'}

    def quit(self):
        if self.driver:
            self.driver.quit()
            print("Production browser closed")

# ---------------- Run ----------------
if __name__ == "__main__":
    mongo_uri = "mongodb+srv://JustTyy:_Cekay032599@mongodb.wostxtt.mongodb.net/?retryWrites=true&w=majority&appName=MongoDB"
    scraper = MillionScaleTwitterScraper(mongo_uri=mongo_uri, headless=True, reset_scraped_users=True)
    if scraper.login("_it_is_andrew", "_Cekay032599", "andrebarnes0325@gmail.com"):
        scraper.scrape_mega_followers("https://x.com/MindAIProject/followers", total_target=1000000, session_limit=10000)
    scraper.quit()
