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

You must have **Google Chrome** installed on your system.

### Python Packages

First, clone this repository to your local machine.

Then, install the required Python packages using the `requirements.txt` file:
```bash
pip install -r requirements.txt
```

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
- `.env`: Where you store your credentials.
- `cookies.json`: This file will be created automatically to store your login session. **Do not share this file.**
- `output/`: This directory will be created to store the scraped CSV files.
- `jobs/`: This directory will be created to store the state of your scraping jobs for resumability.
- `twitter_scraper.log`: A log file that records the scraper's activity.
