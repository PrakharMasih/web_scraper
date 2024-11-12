import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import logging

# import os
import random
import urllib.robotparser
import urllib.parse
from typing import List, Optional
from functools import wraps
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import spacy
import re
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("scraper.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Configuration
SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q=",
    "bing": "https://www.bing.com/search?q=",
}
DATABASE_PATH = "activities.db"
KEYWORDS = ["kids activities", "children events", "family activities", "kids classes"]
RETRY_ATTEMPTS = 3
TIMEOUT = 10
MIN_DELAY = 1
MAX_DELAY = 3


@dataclass
class Activity:
    """Data class for storing activity information"""

    title: str
    description: str
    location: str
    postcode: str
    website_url: str
    age_range: Optional[str] = None
    price: Optional[str] = None
    scraped_at: datetime = datetime.now()


class RetryableError(Exception):
    """Custom exception for errors that should trigger a retry."""

    pass


def retry_on_failure(func):
    """Decorator to retry failed requests."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        for attempt in range(RETRY_ATTEMPTS):
            try:
                return func(*args, **kwargs)
            except (requests.RequestException, RetryableError) as e:
                if attempt == RETRY_ATTEMPTS - 1:
                    logger.error(f"Failed after {RETRY_ATTEMPTS} attempts: {str(e)}")
                    raise
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                time.sleep(2**attempt)  # Exponential backoff

    return wrapper


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.initialize_db()

    def initialize_db(self):
        """Create the database and tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    location TEXT NOT NULL,
                    postcode TEXT NOT NULL,
                    website_url TEXT NOT NULL,
                    age_range TEXT,
                    price TEXT,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS websites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    last_scraped TIMESTAMP,
                    is_relevant BOOLEAN DEFAULT TRUE,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0
                )
            """)

    def save_activity(self, activity: Activity):
        """Save a single activity to the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO activities (
                    title, description, location, postcode,
                    website_url, age_range, price, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    activity.title,
                    activity.description,
                    activity.location,
                    activity.postcode,
                    activity.website_url,
                    activity.age_range,
                    activity.price,
                    activity.scraped_at,
                ),
            )

    def update_website_status(self, url: str, was_successful: bool):
        """Update website tracking information."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if was_successful:
                cursor.execute(
                    """
                    INSERT INTO websites (url, last_scraped, success_count)
                    VALUES (?, CURRENT_TIMESTAMP, 1)
                    ON CONFLICT(url) DO UPDATE SET
                    last_scraped = CURRENT_TIMESTAMP,
                    success_count = success_count + 1
                """,
                    (url,),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO websites (url, last_scraped, fail_count)
                    VALUES (?, CURRENT_TIMESTAMP, 1)
                    ON CONFLICT(url) DO UPDATE SET
                    last_scraped = CURRENT_TIMESTAMP,
                    fail_count = fail_count + 1
                """,
                    (url,),
                )


class ActivityScraper:
    def __init__(self):
        self.session = requests.Session()
        self.nlp = spacy.load("en_core_web_sm")
        self.setup_selenium()
        self.db = Database(DATABASE_PATH)

    def setup_selenium(self):
        """Initialize Selenium for JavaScript-heavy sites."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        self.driver = webdriver.Chrome(options=chrome_options)

    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, "driver"):
            self.driver.quit()

    @retry_on_failure
    def get_page(self, url: str) -> BeautifulSoup:
        """Fetch and parse a webpage."""
        try:
            response = self.session.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as e:
            logger.error(f"Error fetching page {url}: {str(e)}")
            raise RetryableError(f"Failed to fetch page: {str(e)}")

    def discover_websites(self, postcode: str) -> List[str]:
        """Find relevant websites for kids activities in a given postcode."""
        discovered_urls = set()

        for keyword in KEYWORDS:
            search_query = f"{keyword} {postcode}"
            for search_engine in SEARCH_ENGINES.values():
                try:
                    self.driver.get(search_engine + search_query)
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "a"))
                    )

                    links = self.driver.find_elements(By.TAG_NAME, "a")
                    for link in links:
                        url = link.get_attribute("href")
                        if url and self.is_valid_url(url):
                            discovered_urls.add(url)

                    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

                except Exception as e:
                    logger.error(f"Error searching {search_engine}: {str(e)}")

        return list(discovered_urls)

    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and relevant."""
        try:
            return url.startswith("http") and not any(
                x in url for x in ["google", "bing", "facebook", "twitter"]
            )
        except:
            return False

    def validate_robots_txt(self, url: str) -> bool:
        """Check if scraping is allowed for this URL."""
        try:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(urllib.parse.urljoin(url, "/robots.txt"))
            rp.read()
            return rp.can_fetch("*", url)
        except Exception as e:
            logger.warning(f"Could not check robots.txt for {url}: {str(e)}")
            return False

    def extract_activity_data(
        self, url: str, target_postcode: str
    ) -> Optional[Activity]:
        """Extract structured activity data from a webpage."""
        try:
            soup = self.get_page(url)
            text_content = soup.get_text()

            if not self.is_relevant_content(text_content):
                return None

            # Extract basic information
            title = self.extract_title(soup)
            description = self.extract_description(soup)
            location, postcode = self.extract_location_info(
                soup, text_content, target_postcode
            )

            if not all([title, description, location, postcode]):
                return None

            # Extract additional information
            age_range = self.extract_age_range(text_content)
            price = self.extract_price(text_content)

            return Activity(
                title=title,
                description=description,
                location=location,
                postcode=postcode,
                website_url=url,
                age_range=age_range,
                price=price,
            )

        except Exception as e:
            logger.error(f"Error extracting data from {url}: {str(e)}")
            return None

    def is_relevant_content(self, text: str) -> bool:
        """Use NLP to determine if content is relevant to kids activities."""
        doc = self.nlp(text.lower())
        relevant_terms = ["kid", "child", "family", "activity", "class", "event"]
        content_terms = [token.text for token in doc if not token.is_stop]
        return any(term in content_terms for term in relevant_terms)

    def extract_title(self, soup: BeautifulSoup) -> str:
        """Extract activity title from the page."""
        title = soup.find("h1")
        if title:
            return title.get_text().strip()
        return soup.title.string if soup.title else ""

    def extract_description(self, soup: BeautifulSoup) -> str:
        """Extract activity description from the page."""
        meta_desc = soup.find("meta", {"name": "description"})
        if meta_desc:
            return meta_desc.get("content", "")

        paragraphs = soup.find_all("p")
        if paragraphs:
            return " ".join(p.get_text().strip() for p in paragraphs[:3])

        return ""

    def extract_location_info(
        self, soup: BeautifulSoup, text: str, target_postcode: str
    ) -> tuple:
        """Extract location and postcode information."""
        # First try to find postcode in the text
        uk_postcode_pattern = r"[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}"
        postcodes = re.findall(uk_postcode_pattern, text)

        if postcodes:
            # Use the first found postcode
            found_postcode = postcodes[0]
            # Try to find an address near the postcode
            location = self.find_address_near_postcode(text, found_postcode)
            return location, found_postcode

        # If no postcode found, use the target postcode
        return "Location not specified", target_postcode

    def find_address_near_postcode(self, text: str, postcode: str) -> str:
        """Find address information near a postcode in text."""
        # Simple implementation - could be improved with better NLP
        words_before = 10
        text_parts = text.split()
        try:
            postcode_index = text_parts.index(postcode)
            address_part = " ".join(
                text_parts[max(0, postcode_index - words_before) : postcode_index]
            )
            return address_part if address_part else "Address not found"
        except ValueError:
            return "Address not found"

    def extract_age_range(self, text: str) -> Optional[str]:
        """Extract age range information from text."""
        age_patterns = [
            r"ages?\s*\d+\s*-\s*\d+",
            r"\d+\s*to\s*\d+\s*years?",
            r"\d+\+\s*years?",
        ]

        for pattern in age_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    def extract_price(self, text: str) -> Optional[str]:
        """Extract price information from text."""
        price_patterns = [
            r"£\d+(?:\.\d{2})?(?:\s*-\s*£\d+(?:\.\d{2})?)?",
            r"\d+(?:\.\d{2})?\s*pounds?",
        ]

        for pattern in price_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    def process_postcode(self, postcode: str) -> List[Activity]:
        """Main method to process a single postcode."""
        activities = []

        # Discover relevant websites
        websites = self.discover_websites(postcode)
        logger.info(f"Discovered {len(websites)} potential websites for {postcode}")

        for url in websites:
            if not self.validate_robots_txt(url):
                logger.info(f"Skipping {url} - robots.txt disallowed")
                continue

            # Add rate limiting
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

            # Extract and validate data
            activity_data = self.extract_activity_data(url, postcode)
            if activity_data:
                activities.append(activity_data)
                self.db.save_activity(activity_data)
                self.db.update_website_status(url, True)
            else:
                self.db.update_website_status(url, False)

        return activities


def main():
    try:
        scraper = ActivityScraper()

        # Process list of postcodes
        postcodes = ["SW1A 1AA", "E1 6AN"]  # Example postcodes

        for postcode in postcodes:
            logger.info(f"Processing postcode: {postcode}")
            activities = scraper.process_postcode(postcode)

            if activities:
                logger.info(f"Found {len(activities)} activities for {postcode}")
                # Log sample of found activities
                for activity in activities[:3]:
                    logger.info(f"\nTitle: {activity.title}")
                    logger.info(f"Location: {activity.location}")
                    logger.info(f"Age Range: {activity.age_range}")
                    logger.info(f"Price: {activity.price}")
            else:
                logger.warning(f"No activities found for {postcode}")

        logger.info("Scraping completed successfully!")

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        raise
    finally:
        scraper.cleanup()


if __name__ == "__main__":
    main()
