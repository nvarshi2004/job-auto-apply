import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from datetime import datetime
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db.models import create_job

class LinkedInScraper:
    def __init__(self):
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        self.driver = webdriver.Chrome(options=options)
        self.base_url = "https://www.linkedin.com/jobs/search/"
    
    def scrape_jobs(self, keywords="software engineer", location="United States", limit=50):
        """
        Scrape job listings from LinkedIn
        
        Args:
            keywords: Job search keywords
            location: Job location
            limit: Maximum number of jobs to scrape
        """
        jobs = []
        
        try:
            # Construct search URL
            url = f"{self.base_url}?keywords={keywords}&location={location}"
            self.driver.get(url)
            
            # Wait for job listings to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "jobs-search__results-list"))
            )
            
            # Scroll to load more jobs
            scroll_count = 0
            while scroll_count < 5:  # Adjust based on needs
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                scroll_count += 1
            
            # Parse the page
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            job_cards = soup.find_all('div', class_='base-card', limit=limit)
            
            for card in job_cards:
                try:
                    job_data = self._extract_job_data(card)
                    if job_data:
                        jobs.append(job_data)
                        # Save to database
                        create_job(job_data)
                        print(f"Scraped: {job_data['title']} at {job_data['company']}")
                except Exception as e:
                    print(f"Error extracting job: {str(e)}")
                    continue
        
        except Exception as e:
            print(f"Error scraping LinkedIn: {str(e)}")
        
        finally:
            self.driver.quit()
        
        return jobs
    
    def _extract_job_data(self, card):
        """
        Extract job information from a job card
        """
        try:
            # Extract title
            title_elem = card.find('h3', class_='base-search-card__title')
            title = title_elem.text.strip() if title_elem else None
            
            # Extract company
            company_elem = card.find('h4', class_='base-search-card__subtitle')
            company = company_elem.text.strip() if company_elem else None
            
            # Extract location
            location_elem = card.find('span', class_='job-search-card__location')
            location = location_elem.text.strip() if location_elem else None
            
            # Extract job URL
            link_elem = card.find('a', class_='base-card__full-link')
            url = link_elem['href'] if link_elem and 'href' in link_elem.attrs else None
            
            # Extract description snippet
            desc_elem = card.find('p', class_='base-search-card__snippet')
            description = desc_elem.text.strip() if desc_elem else "No description available"
            
            if title and company and url:
                return {
                    'title': title,
                    'company': company,
                    'location': location,
                    'description': description,
                    'url': url,
                    'source': 'LinkedIn',
                    'scraped_at': datetime.utcnow(),
                    'remote': 'remote' in location.lower() if location else False
                }
        
        except Exception as e:
            print(f"Error in _extract_job_data: {str(e)}")
            return None

if __name__ == "__main__":
    scraper = LinkedInScraper()
    jobs = scraper.scrape_jobs(keywords="software engineer intern", limit=20)
    print(f"Total jobs scraped: {len(jobs)}")
