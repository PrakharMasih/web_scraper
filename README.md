# Kids Activities Web Scraper
Extracted links
![Screenshot from 2024-11-12 14-37-37](https://github.com/user-attachments/assets/f89a66f2-37c1-4e84-a547-3adc5751d61f)



## Project Overview

This project is a sophisticated web scraper designed to find and collect information about children's activities, events, and classes across different locations according to the postcode. It automatically searches multiple websites, extracts relevant information, and stores it in a structured database for easy access.

## 🎯 Project Aims

- Automatically discover websites offering kids' activities in specified postcodes
- Extract detailed information about activities including:
  - Title and description
  - Location and postcode
  - Age ranges
  - Pricing
  - Website URLs
- Store collected data in a structured SQLite database
- Respect website scraping policies (robots.txt)
- Maintain reliable and ethical scraping practices

## 🔍 How It Works

1. **Website Discovery**

   - Searches Google and Bing using keywords and postcodes
   - Filters out irrelevant websites and respects robots.txt

2. **Data Extraction**

   - Scrapes websites using both BeautifulSoup and Selenium
   - Extracts activity details using pattern matching and NLP
   - Validates and cleans extracted data

3. **Data Storage**
   - Stores activities in SQLite database
   - Tracks website success/failure rates
   - Maintains scraping history

## 🛠️ Technical Features

- Multi-source data collection (Google, Bing)
- Robust error handling and retry mechanisms
- Rate limiting to prevent server overload
- Natural Language Processing (NLP) for content relevance checking
- Support for JavaScript-heavy websites using Selenium
- Structured data storage in SQLite database
- Comprehensive logging system

## 📋 Prerequisites

python
pip install -r requirements.txt

Required packages:

- requests
- beautifulsoup4
- selenium
- spacy
- sqlite3
- urllib3

You'll also need:

- Chrome WebDriver for Selenium
- English language model for spaCy:
  ```python
  python -m spacy download en_core_web_sm
  ```

## 🗄️ Database Structure

### Activities Table

- id (Primary Key)
- title
- description
- location
- postcode
- website_url
- age_range
- price
- scraped_at

### Websites Table

- id (Primary Key)
- url (Unique)
- last_scraped
- is_relevant
- success_count
- fail_count

## 🚀 How to Use

1. Clone the repository
2. Install dependencies
3. Configure the postcodes in the main() function:

python
postcodes = ["SW1A 1AA", "E1 6AN"] # Add your target postcodes

4. Run the script:

## 📝 Configuration Options

You can modify these variables at the top of the script:

- `SEARCH_ENGINES`: Add/remove search engines
- `DATABASE_PATH`: Change database location
- `KEYWORDS`: Modify search keywords
- `RETRY_ATTEMPTS`: Adjust retry attempts for failed requests
- `TIMEOUT`: Modify request timeout
- `MIN_DELAY/MAX_DELAY`: Adjust scraping delays

## 📊 Output

- Detailed logs in `scraper.log`
- SQLite database with all collected data
- Console progress updates

## ⚠️ Important Notes

- Respect website terms of service
- Configure appropriate delays between requests
- Monitor your IP address for potential blocks
- Some websites may block automated access
