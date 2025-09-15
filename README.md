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

The scraper is configured using environment variables to keep your credentials secure. Create a `.env` file in the project root or set these variables in your shell.

### Finding Your Authentication Headers

This scraper uses Twitter's internal API for maximum speed and reliability. To do this, you need to provide your personal authentication headers. This is a one-time setup.

1.  **Log in to Twitter/X** in your normal web browser (e.g., Chrome, Firefox).
2.  Open the **Developer Tools**. You can usually do this by pressing `F12` or right-clicking on the page and selecting "Inspect".
3.  Go to the **Network** tab in the Developer Tools.
4.  In the filter box of the Network tab, type `UserBy` to filter the requests.
5.  Click on a user's profile on the Twitter website to trigger an API call. You should see a request named `UserByScreenName` or similar appear in the Network tab.
6.  Click on this request. A new panel will open.
7.  Go to the **Headers** tab within this new panel.
8.  Scroll down to **Request Headers**. You need to find and copy the values for three headers:
    *   `authorization`: This is a very long string starting with `Bearer AAAA...`
    *   `x-csrf-token`: This is a 32-character hexadecimal string.
    *   `cookie`: This is a very long string containing all your session cookies.

### Setting Environment Variables

The easiest way to set these environment variables is to create a new file named `.env` in the root of the project directory.

Copy the following template into your `.env` file and replace the placeholder values with your actual credentials and headers. **Do not use quotes** inside the `.env` file.

```dotenv
# .env file

# Your MongoDB connection string
MONGO_DB_URI=mongodb+srv://user:password@cluster.mongodb.net/...

# The headers you copied from your browser
TWITTER_AUTH_TOKEN=Bearer AAAA...
TWITTER_CSRF_TOKEN=1234567890abcdef1234567890abcdef
TWITTER_COOKIE=your_full_cookie_string
```

The script will automatically load these variables when you run it.

## 3. Troubleshooting

### FATAL: Please set all required environment variables...

If you see this error, it means you have not set up your `.env` file correctly.

1.  Make sure you have created a file named exactly `.env` in the main project folder (the same folder that contains `twitter_scraper.py`).
2.  Ensure the `.env` file contains the four required variables: `MONGO_DB_URI`, `TWITTER_AUTH_TOKEN`, `TWITTER_CSRF_TOKEN`, and `TWITTER_COOKIE`.
3.  Make sure you have replaced the placeholder values with your actual credentials.
4.  There should be **no quotes** around the values in the `.env` file.

## 4. How to Use

The main entry point is the `twitter_scraper.py` script. You can run it directly from your terminal.

The primary way to use the scraper is by defining a **job**. A job is a dictionary that tells the scraper what you want to do.

### Running a Scraping Job

To run the scraper, you modify the `if __name__ == "__main__":` block at the bottom of `twitter_scraper.py`.

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
