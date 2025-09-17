# Advanced Modular Twitter Scraper

This project provides a powerful, scalable, and resilient Twitter/X scraper built with Selenium and Python. It is designed to handle large-scale scraping tasks by breaking them into manageable sessions and storing data efficiently in a MongoDB database.

## Features

- **Scalable**: Uses MongoDB to store millions of records without memory issues.
- **Resilient**: Manages scraping jobs over multiple sessions, allowing you to stop and resume large tasks at any time.
- **Modular**: A clean and well-structured codebase makes it easy to understand and extend.
- **Flexible**: Scrape followers, following, tweet likes, retweets, and user tweets.
- **Configurable**: Choose between a 'fast' mode (for speed) or a 'full' mode (for detail).
- **Stealthy**: Uses optimized Selenium settings to mimic human behavior and avoid detection.
=======
# Selenium Twitter Scraper (CSV Edition)

This project provides a robust Twitter/X scraper built with Selenium and Python. It is designed to be run on your local machine to scrape follower and following lists and save them to CSV files.

## Features

- **Selenium-based**: Scrapes Twitter by controlling a real Chrome browser.
- **CSV Storage**: Saves all data to local CSV files in an `output/` directory.
- **Automatic File Splitting**: Creates a new CSV file after a specified number of rows (default 1,000,000) to keep files manageable for Excel.
- **Resumable**: Remembers which users it has already scraped to avoid duplicates when you stop and restart a job.
- **Cookie-based Login**: After a one-time setup, it uses session cookies for fast and reliable logins, avoiding repeated password entries and verification prompts.

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

=======
You must have **Google Chrome** installed on your system.

### Python Packages

First, clone this repository to your local machine.

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

Once you have these three values, set them as environment variables.

```
# Your MongoDB connection string
MONGO_DB_URI="mongodb+srv://user:password@cluster.mongodb.net/..."

# The headers you copied from your browser
TWITTER_AUTH_TOKEN="Bearer AAAA..."
TWITTER_CSRF_TOKEN="1234567890abcdef1234567890abcdef"
TWITTER_COOKIE="your_full_cookie_string"

# Your MongoDB connection string
MONGO_DB_URI="mongodb+srv://user:password@cluster.mongodb.net/..."
=======
## 2. Configuration

The scraper is configured using a `.env` file.

1.  Create a new file named `.env` in the root of the project directory.
2.  Copy the following into the file and add your Twitter username and password.

```dotenv
# .env file

TWITTER_USERNAME=your_twitter_username
TWITTER_PASSWORD=your_twitter_password

```

## 3. How to Use


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
=======
### First-Time Login (Creating `cookies.json`)

The first time you run the scraper, you need to perform a one-time login to save your session. Twitter will likely ask for a confirmation code sent to your email.

1.  Run the script with the `--login-first` flag. This tells the scraper to perform a full login.
    ```bash
    python twitter_scraper.py --login-first
    ```
2.  The script will open a Chrome window. Log in as you normally would.
3.  You may be prompted for an email/phone confirmation code. **Enter it in the browser window**.
4.  Once you are successfully logged in and see your Twitter timeline, the script will automatically save a `cookies.json` file and then close.

### Running a Scraping Job

Once `cookies.json` has been created, you can run any scraping job without needing to log in again.

The script is controlled via command-line arguments.

**To scrape followers:**
```bash
python twitter_scraper.py --task followers --user elonmusk --limit 5000
```

**To scrape who a user is following:**
```bash
python twitter_scraper.py --task following --user elonmusk --limit 1000
```

#### Arguments:
- `--task`: The type of job to run. Currently supports `followers` or `following`.
- `--user`: The Twitter username of the target account (without the '@').
- `--limit`: (Optional) The maximum number of items you want to scrape for this job. If not provided, it will try to scrape all of them.
- `--login-first`: (Optional) Use this flag only when you need to create or refresh your `cookies.json` file.


## Project Structure

- `twitter_scraper.py`: The main script containing all the scraper logic.
- `requirements.txt`: The list of Python dependencies.

- `jobs/`: A directory that will be automatically created to store the state of your scraping jobs.
=======
- `.env`: Where you store your credentials.
- `cookies.json`: This file will be created automatically to store your login session. **Do not share this file.**
- `output/`: This directory will be created to store the scraped CSV files.
- `jobs/`: This directory will be created to store the state of your scraping jobs for resumability.

- `twitter_scraper.log`: A log file that records the scraper's activity.
