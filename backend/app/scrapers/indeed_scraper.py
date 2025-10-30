import os
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db.models import create_job

class IndeedScraper:
    def __init__(self):
        self.base_url = "https://www.indeed.com/jobs"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def scrape_jobs(self, keywords="software engineer", location="United States", limit=50):
        """
        Scrape job listings from Indeed
        
        Args:
            keywords: Job search keywords
            location: Job location
            limit: Maximum number of jobs to scrape
        """
        jobs = []
        start = 0
        
        try:
            while len(jobs) < limit:
                # Construct search URL
                params = {
                    'q': keywords,
                    'l': location,
                    'start': start
                }
                
                response = requests.get(self.base_url, params=params, headers=self.headers)
                
                if response.status_code != 200:
                    print(f"Error: Status code {response.status_code}")
                    break
                
                # Parse the page
                soup = BeautifulSoup(response.content, 'html.parser')
                job_cards = soup.find_all('div', class_='job_seen_beacon')
                
                if not job_cards:
                    print("No more jobs found")
                    break
                
                for card in job_cards:
                    if len(jobs) >= limit:
                        break
                    
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
                
                start += 10  # Indeed shows 10-15 jobs per page
                time.sleep(2)  # Be respectful to the server
        
        except Exception as e:
            print(f"Error scraping Indeed: {str(e)}")
        
        return jobs
    
    def _extract_job_data(self, card):
        """
        Extract job information from a job card
        """
        try:
            # Extract title
            title_elem = card.find('h2', class_='jobTitle')
            if title_elem:
                title_link = title_elem.find('a')
                title = title_link.text.strip() if title_link else title_elem.text.strip()
            else:
                title = None
            
            # Extract company
            company_elem = card.find('span', class_='companyName')
            company = company_elem.text.strip() if company_elem else None
            
            # Extract location
            location_elem = card.find('div', class_='companyLocation')
            location = location_elem.text.strip() if location_elem else None
            
            # Extract job URL
            job_key_elem = card.find('a', class_='jcs-JobTitle')
            if job_key_elem and 'href' in job_key_elem.attrs:
                job_url = f"https://www.indeed.com{job_key_elem['href']}"
            else:
                job_url = None
            
            # Extract description snippet
            desc_elem = card.find('div', class_='job-snippet')
            description = desc_elem.text.strip() if desc_elem else "No description available"
            
            # Extract salary if available
            salary_elem = card.find('div', class_='salary-snippet')
            salary = salary_elem.text.strip() if salary_elem else None
            
            if title and company and job_url:
                return {
                    'title': title,
                    'company': company,
                    'location': location,
                    'description': description,
                    'url': job_url,
                    'source': 'Indeed',
                    'salary': salary,
                    'scraped_at': datetime.utcnow(),
                    'remote': 'remote' in description.lower() if description else False
                }
        
        except Exception as e:
            print(f"Error in _extract_job_data: {str(e)}")
            return None

if __name__ == "__main__":
    scraper = IndeedScraper()
    jobs = scraper.scrape_jobs(keywords="software engineer intern", limit=20)
    print(f"Total jobs scraped: {len(jobs)}")
