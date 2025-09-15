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
