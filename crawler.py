#!/usr/bin/env python3
"""
Web Crawler for Word Counting
Crawls multiple pages simultaneously using async Playwright with JavaScript support.
"""

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
import asyncio
import time
import re
import argparse
from typing import Set, Dict
import sys
import csv
import os
from datetime import datetime
import requests
from tradcrawler import WebCrawler
from domain_analyzer import DomainAnalyzer

# Field list for domain analysis CSV
DOMAIN_FIELDS = [
    'domain', 'timestamp', 'elapsed_ms', 'ip', 'tls_valid', 'tls_not_before', 
    'tls_not_after', 'tls_days_to_expiry', 'tls_issuer', 'primary_cms', 
    'cms_wordpress', 'cms_drupal', 'cms_joomla', 'cms_typo3', 'cms_shopify', 
    'cms_wix', 'cms_squarespace', 'cms_webflow', 'cms_ghost', 'cms_duda', 
    'cms_craft', 'ecom_woocommerce', 'ecom_magento', 'pay_stripe', 'pay_paypal', 
    'pay_klarna', 'analytics_ga4', 'analytics_gtm', 'analytics_ua', 
    'analytics_fb_pixel', 'analytics_linkedin', 'analytics_hotjar', 
    'analytics_hubspot', 'js_react', 'js_vue', 'js_angular', 'js_nextjs', 
    'js_nuxt', 'js_svelte', 'has_email_text', 'has_phone_text', 'html_kb', 
    'html_kb_over_500', 'header_server', 'header_x_powered_by', 'security_hsts', 
    'security_csp', 'cookies_present', 'cdn_hint', 'server_hint', 'risk_flags', 
    'errors', 'cms_wordpress_html', 'risk_placeholder_kw', 'risk_parked_kw', 
    'risk_suspended_kw'
]

def save_domain_analysis(analysis, filename="results/domain_analysis.csv"):
    file_exists = os.path.exists(filename)
    
    with open(filename, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=DOMAIN_FIELDS)
        if not file_exists:
            writer.writeheader()
        
        # Ensure all fields are present
        row = {field: analysis.get(field, '') for field in DOMAIN_FIELDS}
        writer.writerow(row)

def load_analyzed_domains(filename="results/domain_analysis.csv"):
    analyzed = set()
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('domain'):
                        analyzed.add(row['domain'])
        except Exception as e:
            print(f"Warning: Could not read domain analysis file: {e}")
    return analyzed


def needs_js_crawler(url: str) -> bool:
    """
    Detect if a website likely requires JavaScript to render content.
    Returns True if JS crawler should be used, False if traditional crawler is sufficient.
    """
    try:
        # Fake a browser user agent
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        
        # 1. Check for specific "Enable JS" messages
        text_lower = response.text.lower()
        if "enable javascript" in text_lower or "javascript is required" in text_lower:
            return True

        # 2. Check content length (if < 50 words, it's suspicious)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove scripts and styles
        for script in soup(['script', 'style', 'meta', 'noscript']):
            script.decompose()
            
        text = soup.get_text()
        words = len(text.split())
        
        if words < 50: 
            return True
            
        return False # Safe to use tradcrawler
        
    except Exception as e:
        # If the fast request fails entirely, might as well try the robust browser
        print(f"Quick check failed ({e}), defaulting to JS crawler")
        return True



class WebCrawlerJSConcurrent:
    def __init__(self, base_url: str, delay: float = 0.1, headless: bool = True, 
                 fast_mode: bool = True, max_workers: int = 5):
        """
        Initialize the concurrent web crawler with JavaScript support.
        
        Args:
            base_url: The starting URL to crawl
            delay: Delay between requests in seconds (default: 0.1)
            headless: Run browser in headless mode (default: True)
            fast_mode: Use faster page loading strategy (default: True)
            max_workers: Number of concurrent browser contexts (default: 5)
        """
        self.base_url = base_url
        self.delay = delay
        self.headless = headless
        self.fast_mode = fast_mode
        self.max_workers = max_workers
        self.visited_urls: Set[str] = set()
        self.word_count_by_page: Dict[str, int] = {}
        self.page_contents: Dict[str, str] = {}
        self.page_titles: Dict[str, str] = {}
        self.page_timestamps: Dict[str, str] = {}
        self.page_categories: Dict[str, str] = {}
        self.page_languages: Dict[str, str] = {}
        self.technologies: Set[str] = set()
        self.total_words = 0
        self.lock = None  # Will be initialized in crawl()
        
        # Language code to name mapping
        self.language_names = {
            'en': 'English', 'no': 'Norwegian', 'nb': 'Norwegian Bokmål',
            'nn': 'Norwegian Nynorsk', 'sv': 'Swedish', 'da': 'Danish',
            'fi': 'Finnish', 'de': 'German', 'fr': 'French', 'es': 'Spanish',
            'it': 'Italian', 'pt': 'Portuguese', 'nl': 'Dutch', 'zh': 'Chinese',
            'ja': 'Japanese', 'ko': 'Korean', 'ru': 'Russian', 'ar': 'Arabic',
            'pl': 'Polish', 'cs': 'Czech',
        }
        
        parsed_base = urlparse(base_url)
        self.base_domain = parsed_base.netloc
        self.base_language = self._detect_base_language_from_domain(self.base_domain)
    
    def _detect_base_language_from_domain(self, domain: str) -> str:
        """Detect base language from domain extension."""
        domain_lang_map = {
            '.no': 'no', '.se': 'sv', '.dk': 'da', '.fi': 'fi', '.de': 'de',
            '.fr': 'fr', '.es': 'es', '.it': 'it', '.pt': 'pt', '.nl': 'nl',
            '.be': 'nl', '.jp': 'ja', '.cn': 'zh', '.kr': 'ko', '.ru': 'ru',
            '.com': 'en', '.org': 'en', '.net': 'en', '.edu': 'en', '.gov': 'en',
        }
        
        domain_lower = domain.lower()
        for ext, lang in domain_lang_map.items():
            if domain_lower.endswith(ext):
                return lang
        return 'en'
    
    def _detect_language(self, url: str) -> str:
        """Detect language from URL path or domain."""
        path = urlparse(url).path.lower()
        lang_codes = ['en', 'no', 'nb', 'nn', 'fr', 'de', 'es', 'it', 'pt', 'zh', 
                      'ja', 'ru', 'ar', 'ko', 'sv', 'da', 'fi', 'nl', 'pl', 'cs']
        
        for code in lang_codes:
            if f'/{code}/' in path or f'/{code}-' in path or path.endswith(f'/{code}') or path.startswith(f'{code}/'):
                return self.language_names.get(code, code.capitalize())
        
        return self.language_names.get(self.base_language, self.base_language.capitalize())
    
    def _categorize_page(self, url: str) -> str:
        """Extract the first subdirectory from URL path as category."""
        path = urlparse(url).path.strip('/')
        if not path:
            return 'home'
        
        parts = path.split('/')
        lang_codes = ['en', 'no', 'nb', 'nn', 'fr', 'de', 'es', 'it', 'pt', 'zh', 'ja', 'ru', 'ar', 'ko']
        
        for part in parts:
            if part and part.lower() not in lang_codes:
                return part.lower()
        
        if parts and parts[0]:
            return parts[0].lower()
        return 'home'
    
    def _detect_technologies(self, soup: BeautifulSoup, html_content: str) -> Set[str]:
        """Detect technologies used on the page."""
        techs = set()
        
        # Check meta generator
        meta_generator = soup.find('meta', attrs={'name': 'generator'})
        if meta_generator and meta_generator.get('content'):
            techs.add(meta_generator['content'])
            
        # Check for common platforms in HTML content or scripts
        html_lower = html_content.lower()
        
        # CMS / E-commerce
        if 'wp-content' in html_lower: techs.add('WordPress')
        if 'shopify' in html_lower: techs.add('Shopify')
        if 'wix.com' in html_lower: techs.add('Wix')
        if 'squarespace' in html_lower: techs.add('Squarespace')
        if 'joomla' in html_lower: techs.add('Joomla')
        if 'drupal' in html_lower: techs.add('Drupal')
        if 'magento' in html_lower: techs.add('Magento')
        if 'prestashop' in html_lower: techs.add('PrestaShop')
        if 'bigcommerce' in html_lower: techs.add('BigCommerce')
        if 'hubspot' in html_lower: techs.add('HubSpot')
        if 'webflow' in html_lower: techs.add('Webflow')
        if 'craft cms' in html_lower: techs.add('Craft CMS')
        if 'bitrix' in html_lower: techs.add('Bitrix')

        # JavaScript Frameworks/Libraries (checking specific indicators)
        if 'react' in html_lower and ('react-dom' in html_lower or 'data-reactroot' in html_lower): techs.add('React')
        if 'vue' in html_lower and ('vue.js' in html_lower or 'data-v-' in html_lower): techs.add('Vue.js')
        if 'angular' in html_lower and ('ng-version' in html_lower or 'angular.js' in html_lower): techs.add('Angular')
        if 'jquery' in html_lower: techs.add('jQuery')
        if 'bootstrap' in html_lower: techs.add('Bootstrap')
        if 'tailwind' in html_lower: techs.add('Tailwind CSS')
        if 'next.js' in html_lower or '/_next/' in html_lower: techs.add('Next.js')
        if 'nuxt' in html_lower or '/_nuxt/' in html_lower: techs.add('Nuxt.js')
        if 'gatsby' in html_lower: techs.add('Gatsby')
        if 'alpine.js' in html_lower or 'x-data' in html_lower: techs.add('Alpine.js')
        
        # Analytics/Marketing
        if 'google-analytics' in html_lower or 'ga.js' in html_lower or 'gtag' in html_lower: techs.add('Google Analytics')
        if 'googletagmanager' in html_lower: techs.add('Google Tag Manager')
        if 'facebook-pixel' in html_lower or 'fbevents.js' in html_lower: techs.add('Facebook Pixel')
        if 'hotjar' in html_lower: techs.add('Hotjar')
        if 'intercom' in html_lower: techs.add('Intercom')
        if 'drift' in html_lower: techs.add('Drift')
        if 'klaviyo' in html_lower: techs.add('Klaviyo')
            
        return techs

    def is_valid_url(self, url: str) -> bool:
        """Check if URL should be crawled."""
        parsed = urlparse(url)
        
        if parsed.scheme not in ['http', 'https']:
            return False
        if parsed.netloc != self.base_domain:
            return False
        
        skip_extensions = [
            '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico',
            '.zip', '.tar', '.gz', '.mp4', '.mp3', '.avi', '.mov',
            '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.css', '.js', '.xml', '.json'
        ]
        
        if any(url.lower().endswith(ext) for ext in skip_extensions):
            return False
        
        return True
    
    def normalize_url(self, url: str) -> str:
        """Normalize URL by removing fragments and trailing slashes."""
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        if normalized.endswith('/') and len(parsed.path) > 1:
            normalized = normalized[:-1]
        
        if parsed.query:
            normalized += f"?{parsed.query}"
        
        return normalized
    
    def extract_text(self, soup: BeautifulSoup) -> str:
        """Extract visible text from HTML."""
        for script in soup(['script', 'style', 'meta', 'noscript']):
            script.decompose()
        
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return ' '.join(chunk for chunk in chunks if chunk)
    
    def count_words(self, text: str) -> int:
        """Count words in text."""
        words = re.findall(r'\b[a-zA-Z0-9]+\b', text)
        return len(words)
    
    async def crawl_page(self, page, url: str) -> Set[str]:
        """Crawl a single page and return found links."""
        found_urls = set()
        
        try:
            print(f"Crawling: {url}")
            
            wait_strategy = 'domcontentloaded' if self.fast_mode else 'networkidle'
            response = await page.goto(url, wait_until=wait_strategy, timeout=30000)
            
            if not response or not response.ok:
                print(f"  Error: Failed to load page")
                return found_urls
            
            if not self.fast_mode:
                await page.wait_for_timeout(500)
            
            html_content = await page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            text = self.extract_text(soup)
            word_count = self.count_words(text)
            category = self._categorize_page(url)
            language = self._detect_language(url)
            technologies = self._detect_technologies(soup, html_content)
            
            # Extract page title
            page_title = soup.title.string.strip() if soup.title and soup.title.string else ""
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            async with self.lock:
                self.word_count_by_page[url] = word_count
                self.page_contents[url] = text
                self.page_titles[url] = page_title
                self.page_timestamps[url] = timestamp
                self.page_categories[url] = category
                self.page_languages[url] = language
                self.technologies.update(technologies)
                self.total_words += word_count
            
            print(f"  Words: {word_count:,} [{language}] - Total: {self.total_words:,}")
            
            for link in soup.find_all('a', href=True):
                absolute_url = urljoin(url, link['href'])
                normalized_url = self.normalize_url(absolute_url)
                
                if self.is_valid_url(normalized_url):
                    async with self.lock:
                        if normalized_url not in self.visited_urls:
                            found_urls.add(normalized_url)
        
        except PlaywrightTimeout as e:
            print(f"  Timeout: {e}")
        except Exception as e:
            print(f"  Error: {e}")
        
        return found_urls
    
    async def worker(self, browser, queue, max_pages):
        """Worker coroutine that processes URLs from the queue."""
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        try:
            while True:
                try:
                    url = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    break
                
                # Only stop if we have processed enough pages, but here we are checking visited_urls
                # which includes queued pages. If we strictly control adding to queue, we should process
                # what is in the queue.
                # if max_pages and len(self.visited_urls) >= max_pages:
                #     queue.task_done()
                #     break
                
                found_urls = await self.crawl_page(page, url)
                
                async with self.lock:
                    for new_url in found_urls:
                        if new_url not in self.visited_urls:
                            if not max_pages or len(self.visited_urls) < max_pages:
                                self.visited_urls.add(new_url)
                                await queue.put(new_url)
                
                if self.delay > 0:
                    await asyncio.sleep(self.delay)
                
                queue.task_done()
        
        finally:
            await context.close()
    
    async def crawl(self, max_pages: int = None):
        """Start crawling from the base URL using concurrent workers."""
        start_time = time.time()
        self.lock = asyncio.Lock()
        print(f"Starting concurrent crawl of {self.base_url}")
        print(f"Domain: {self.base_domain}")
        print(f"JavaScript rendering: ENABLED")
        print(f"Fast mode: {'ENABLED' if self.fast_mode else 'DISABLED'}")
        print(f"Concurrent workers: {self.max_workers}")
        print(f"Request delay: {self.delay}s")
        print(f"Max pages: {'Unlimited' if max_pages is None else max_pages}")
        print("-" * 60)
        
        queue = asyncio.Queue()
        await queue.put(self.base_url)
        self.visited_urls.add(self.base_url)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            
            try:
                workers = [
                    asyncio.create_task(self.worker(browser, queue, max_pages))
                    for _ in range(self.max_workers)
                ]
                
                await queue.join()
                
                # Cancel workers
                for w in workers:
                    w.cancel()
                
                await asyncio.gather(*workers, return_exceptions=True)
            
            finally:
                await browser.close()
        
        print("-" * 60)
        print("\nCrawl Complete!")
        elapsed_time = time.time() - start_time
        print(f"Time taken: {elapsed_time:.2f} seconds")
        self.print_statistics()
    
    def print_statistics(self):
        """Print crawl statistics."""
        print(f"\n{'='*60}")
        print("CRAWL STATISTICS")
        print(f"{'='*60}")
        print(f"Total pages crawled: {len(self.visited_urls):,}")
        print(f"Total words found: {self.total_words:,}")
        print(f"Average words per page: {self.total_words / len(self.visited_urls):.1f}" if self.visited_urls else "N/A")
        
        # Language breakdown
        if self.page_languages:
            print(f"\n{'='*60}")
            print("BREAKDOWN BY LANGUAGE")
            print(f"{'='*60}")
            
            language_stats = {}
            for url, language in self.page_languages.items():
                if language not in language_stats:
                    language_stats[language] = {'count': 0, 'words': 0}
                language_stats[language]['count'] += 1
                language_stats[language]['words'] += self.word_count_by_page.get(url, 0)
            
            sorted_languages = sorted(language_stats.items(), key=lambda x: x[1]['count'], reverse=True)
            
            print(f"\n{'Language':<15} {'Pages':<10} {'Total Words':<15} {'Avg Words/Page':<15}")
            print("-" * 60)
            for language, stats in sorted_languages:
                avg_words = stats['words'] / stats['count'] if stats['count'] > 0 else 0
                print(f"{language:<15} {stats['count']:<10,} {stats['words']:<15,} {avg_words:<15.1f}")
    
    def save_results(self, output_dir: str = "results"):
        """Save results to a CSV file."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Clean domain name for filename (remove www. and TLD like .no)
        # Example: www.plussark.no -> plussark
        domain_parts = self.base_domain.replace('www.', '').split('.')
        # Take the first part as the name (e.g. 'plussark' from 'plussark.no')
        safe_name = domain_parts[0] if domain_parts else 'unknown'
        
        filename = os.path.join(output_dir, f"{safe_name}.csv")
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Row 1: Domain URL, Date Updated, Technologies
                tech_str = ", ".join(sorted(self.technologies))
                date_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([self.base_url, date_updated, tech_str])
                
                # Row 2: Headers matching format.csv
                writer.writerow(['url', 'html2text', 'page_title', 'timestamp'])
                
                # Row 3+: Data
                sorted_pages = sorted(self.word_count_by_page.items(), key=lambda x: x[1], reverse=True)
                for url, count in sorted_pages:
                    content = self.page_contents.get(url, "")
                    title = self.page_titles.get(url, "")
                    timestamp = self.page_timestamps.get(url, "")
                    writer.writerow([url, content, title, timestamp])
            
            print(f"\nResults saved to {filename}")
        except Exception as e:
            print(f"Error saving results: {e}")


class ProgressTracker:
    def __init__(self, progress_file="results/progress.csv"):
        self.progress_file = progress_file
        self.ensure_file_exists()
        self.history = self.load_history()

    def ensure_file_exists(self):
        directory = os.path.dirname(self.progress_file)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        
        if not os.path.exists(self.progress_file):
            with open(self.progress_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['url', 'status', 'timestamp'])

    def load_history(self):
        history = {}
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('url'):
                            history[row['url']] = row['status']
            except Exception as e:
                print(f"Warning: Could not read progress file: {e}")
        return history

    def update_status(self, url, status):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.progress_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([url, status, timestamp])
            self.history[url] = status
        except Exception as e:
            print(f"Warning: Could not update progress file: {e}")

    def is_completed(self, url):
        return self.history.get(url) == 'completed'


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Concurrent Web Crawler with JavaScript Support")
    parser.add_argument("url", nargs='?', help="The starting URL to crawl")
    parser.add_argument("--input-csv", help="Path to CSV file containing URLs to crawl")
    parser.add_argument("--limit-sites", type=int, default=None, help="Limit number of websites to crawl from CSV")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum number of pages to crawl (default: unlimited)")
    parser.add_argument("--delay", type=float, default=0.1, help="Delay between requests in seconds (default: 0.1)")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent workers (default: 5)")
    parser.add_argument("--no-headless", action="store_true", help="Run browser in visible mode")
    parser.add_argument("--no-fast", action="store_true", help="Disable fast mode (resource blocking)")
    
    args = parser.parse_args()
    
    if args.input_csv:
        if not os.path.exists(args.input_csv):
            print(f"Error: Input CSV file '{args.input_csv}' not found.")
            return

        print(f"Reading URLs from {args.input_csv}...")
        
        try:
            with open(args.input_csv, 'r', encoding='utf-8') as f:
                # Check if file has header
                sample = f.read(1024)
                f.seek(0)
                has_header = csv.Sniffer().has_header(sample)
                
                if has_header:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                else:
                    # Assume no header, use column indices if needed, but user said "urls.csv" has headers
                    # "orgNumber,name,website"
                    reader = csv.DictReader(f)
                    rows = list(reader)

            if args.limit_sites:
                rows = rows[:args.limit_sites]

            total_sites = len(rows)
            print(f"Found {total_sites} websites to crawl.")
            
            # Initialize progress tracker
            tracker = ProgressTracker()
            
            # Initialize domain analyzer
            analyzer = DomainAnalyzer()
            analyzed_domains = load_analyzed_domains()
            
            for i, row in enumerate(rows, 1):
                website = row.get('website')
                if not website:
                    continue
                
                # Clean website URL
                website = website.strip()
                if not website.startswith('http'):
                    website = 'https://' + website
                
                # Check progress
                if tracker.is_completed(website):
                    print(f"\n[{i}/{total_sites}] Skipping {website} - Already completed.")
                    continue
                
                # Domain Analysis
                if website not in analyzed_domains:
                    print(f"\n[{i}/{total_sites}] Analyzing domain: {website}")
                    try:
                        analysis = analyzer.analyze(website)
                        save_domain_analysis(analysis)
                        analyzed_domains.add(website)
                        print(f"  -> Analysis saved. IP: {analysis.get('ip')}, CMS: {analysis.get('primary_cms')}")
                    except Exception as e:
                        print(f"  -> Analysis failed: {e}")
                
                print(f"\n[{i}/{total_sites}] Checking technology for: {website}")
                
                # Mark as started
                tracker.update_status(website, 'started')
                
                crawl_success = False
                try:
                    use_js_crawler = needs_js_crawler(website)
                    
                    if use_js_crawler:
                        print(f"  -> Detected JavaScript dependency. Using Playwright crawler.")
                        crawler = WebCrawlerJSConcurrent(
                            website, 
                            delay=args.delay, 
                            headless=not args.no_headless, 
                            fast_mode=not args.no_fast, 
                            max_workers=args.workers
                        )
                        
                        try:
                            asyncio.run(crawler.crawl(max_pages=args.max_pages))
                            crawl_success = True
                        except Exception as e:
                            print(f"Error crawling {website}: {e}")
                            tracker.update_status(website, 'failed')
                        finally:
                            crawler.save_results()
                    else:
                        print(f"  -> Static content detected. Using fast traditional crawler.")
                        # Use the traditional crawler
                        crawler = WebCrawler(
                            website,
                            delay=args.delay,
                            max_workers=args.workers
                        )
                        
                        try:
                            crawler.crawl(max_pages=args.max_pages)
                            crawl_success = True
                        except Exception as e:
                            print(f"Error crawling {website}: {e}")
                            tracker.update_status(website, 'failed')
                        finally:
                            # Use the new CSV save method we added
                            crawler.save_results_csv()
                    
                    if crawl_success:
                        tracker.update_status(website, 'completed')
                        
                except KeyboardInterrupt:
                    print("\nCrawl interrupted by user.")
                    tracker.update_status(website, 'interrupted')
                    break
                except Exception as e:
                    print(f"Unexpected error processing {website}: {e}")
                    tracker.update_status(website, 'failed')
                    
        except Exception as e:
            print(f"Error processing CSV: {e}")
            
    elif args.url:
        # Domain Analysis
        print(f"Analyzing domain: {args.url}")
        analyzer = DomainAnalyzer()
        try:
            analysis = analyzer.analyze(args.url)
            save_domain_analysis(analysis)
            print(f"  -> Analysis saved. IP: {analysis.get('ip')}, CMS: {analysis.get('primary_cms')}")
        except Exception as e:
            print(f"  -> Analysis failed: {e}")

        print(f"Checking technology for: {args.url}")
        use_js_crawler = needs_js_crawler(args.url)
        
        if use_js_crawler:
            print(f"  -> Detected JavaScript dependency. Using Playwright crawler.")
            crawler = WebCrawlerJSConcurrent(
                args.url, 
                delay=args.delay, 
                headless=not args.no_headless, 
                fast_mode=not args.no_fast, 
                max_workers=args.workers
            )
            
            try:
                asyncio.run(crawler.crawl(max_pages=args.max_pages))
            except KeyboardInterrupt:
                print("\nCrawl interrupted by user.")
            finally:
                crawler.save_results()
        else:
            print(f"  -> Static content detected. Using fast traditional crawler.")
            crawler = WebCrawler(
                args.url,
                delay=args.delay,
                max_workers=args.workers
            )
            
            try:
                crawler.crawl(max_pages=args.max_pages)
            except KeyboardInterrupt:
                print("\nCrawl interrupted by user.")
            finally:
                crawler.save_results_csv()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

