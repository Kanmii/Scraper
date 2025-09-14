# Advanced Modular Twitter Scraper

This project provides a powerful, scalable, and resilient Twitter/X scraper built with Selenium and Python. It is designed to handle large-scale scraping tasks by breaking them into manageable sessions and storing data efficiently in a MongoDB database.

## Features

- **Scalable**: Uses MongoDB to store millions of records without memory issues.
- **Resilient**: Manages scraping jobs over multiple sessions, allowing you to stop and resume large tasks at any time.
- **Modular**: A clean and well-structured codebase makes it easy to understand and extend.
- **Flexible**: Scrape followers, following, tweet likes, retweets, and user tweets.
- **Configurable**: Choose between a 'fast' mode (for speed) or a 'full' mode (for detail).
- **Stealthy**: Uses optimized Selenium settings to mimic human behavior and avoid detection.

## 1. Installation

### System Dependencies

This scraper uses Selenium to control a real web browser. You must have Google Chrome installed on your system.

On Debian/Ubuntu, you can install it with the following commands:
```bash
# Get Google's signing key
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -

# Add the Google Chrome repository
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list

# Update and install
sudo apt-get update
sudo apt-get install -y google-chrome-stable
```

### Python Packages

First, clone the repository and navigate into the project directory.

Then, install the required Python packages using the `requirements.txt` file:

```bash
pip install -r requirements.txt
```

### Database

You will also need a running MongoDB instance. You can use a local instance or a cloud-based one like MongoDB Atlas.

## 2. Configuration

The scraper is configured using environment variables to keep your credentials secure. Create a `.env` file in the project root or set these variables in your shell:

```
# Your Twitter/X login credentials
TWITTER_USERNAME="your_twitter_username"
TWITTER_PASSWORD="your_twitter_password"

# (Optional) Your email, in case Twitter asks for it during login
TWITTER_EMAIL="your_twitter_email@example.com"

# Your MongoDB connection string
MONGO_DB_URI="mongodb+srv://user:password@cluster.mongodb.net/..."
```

## 3. How to Use

The main entry point is the `unified_scraper.py` script. You can run it directly from your terminal.

The primary way to use the scraper is by defining a **job**. A job is a dictionary that tells the scraper what you want to do.

### Running a Scraping Job

To run the scraper, you modify the `if __name__ == "__main__":` block at the bottom of `unified_scraper.py`.

Here is an example of a job to scrape the first 500 followers of the `MindAIProject` Twitter account:

```python
if __name__ == "__main__":
    # ... (login logic) ...

    if login_successful:
        # Define the job
        follower_job = {
            "task": "followers",          # The type of task to run
            "identifier": "MindAIProject",  # The target username or tweet URL
            "total_target": 500,          # The total number of items you want
            "session_limit": 200,         # How many items to scrape per run
            "detail_level": "full"        # 'full' or 'fast'
        }

        # Run the job
        scraper.run_scraping_job(follower_job)
```

When you run `python unified_scraper.py`, this job will start. It will run in sessions of 200 followers until the total target of 500 is met. If you stop the script and run it again, it will automatically check the database and resume where it left off.

### Available Tasks

You can set the `"task"` key in your job dictionary to any of the following:

- `followers`: Scrapes the followers of a user.
  - `"identifier"`: The target username (e.g., `"MindAIProject"`).
- `following`: Scrapes who a user is following.
  - `"identifier"`: The target username.
- `likes`: Scrapes users who liked a tweet.
  - `"identifier"`: The full URL of the tweet.
- `retweets`: Scrapes users who retweeted a tweet.
  - `"identifier"`: The full URL of the tweet.
- `tweets`: Scrapes the tweets from a user's profile.
  - `"identifier"`: The target username.

## Project Structure

- `twitter_scraper.py`: The main script containing all the scraper logic.
- `requirements.txt`: The list of Python dependencies.
- `jobs/`: A directory that will be automatically created to store the state of your scraping jobs.
- `twitter_scraper.log`: A log file that records the scraper's activity.
