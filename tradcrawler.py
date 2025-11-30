#!/usr/bin/env python3
"""
Web Crawler for Word Counting
Crawls all pages on a website and counts total words.
NOTE: Does NOT support JavaScript - use crawler_js.py for JavaScript-heavy sites.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
import time
import re
from typing import Set, Dict
import sys
import csv
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock


class WebCrawler:
    def __init__(self, base_url: str, delay: float = 0.1, max_workers: int = 5):
        """
        Initialize the web crawler.
        
        Args:
            base_url: The starting URL to crawl
            delay: Delay between requests in seconds (default: 0.1 for concurrent mode)
            max_workers: Number of concurrent threads (default: 5)
        """
        self.base_url = base_url
        self.delay = delay
        self.visited_urls: Set[str] = set()
        self.word_count_by_page: Dict[str, int] = {}
        self.page_contents: Dict[str, str] = {}  # URL -> text content
        self.page_titles: Dict[str, str] = {}  # URL -> page title
        self.page_timestamps: Dict[str, str] = {}  # URL -> crawl timestamp
        self.page_categories: Dict[str, str] = {}  # URL -> category
        self.page_languages: Dict[str, str] = {}  # URL -> language
        self.total_words = 0
        self.max_workers = max_workers
        
        # Thread-safe locks for concurrent access
        self.visited_lock = Lock()
        self.stats_lock = Lock()
        
        # Language code to name mapping
        self.language_names = {
            'en': 'English',
            'no': 'Norwegian',
            'nb': 'Norwegian Bokmål',
            'nn': 'Norwegian Nynorsk',
            'sv': 'Swedish',
            'da': 'Danish',
            'fi': 'Finnish',
            'de': 'German',
            'fr': 'French',
            'es': 'Spanish',
            'it': 'Italian',
            'pt': 'Portuguese',
            'nl': 'Dutch',
            'zh': 'Chinese',
            'ja': 'Japanese',
            'ko': 'Korean',
            'ru': 'Russian',
            'ar': 'Arabic',
            'pl': 'Polish',
            'cs': 'Czech',
        }
        
        # Parse base domain to only crawl within the same domain
        parsed_base = urlparse(base_url)
        self.base_domain = parsed_base.netloc
        
        # Detect base language from domain extension
        self.base_language = self._detect_base_language_from_domain(self.base_domain)
        
        # Reusable session for better performance
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def _detect_base_language_from_domain(self, domain: str) -> str:
        """Detect base language from domain extension."""
        # Map domain extensions to language codes
        domain_lang_map = {
            '.no': 'no',      # Norwegian
            '.se': 'sv',      # Swedish
            '.dk': 'da',      # Danish
            '.fi': 'fi',      # Finnish
            '.de': 'de',      # German
            '.fr': 'fr',      # French
            '.es': 'es',      # Spanish
            '.it': 'it',      # Italian
            '.pt': 'pt',      # Portuguese
            '.nl': 'nl',      # Dutch
            '.be': 'nl',      # Belgian (Dutch/French, default to Dutch)
            '.jp': 'ja',      # Japanese
            '.cn': 'zh',      # Chinese
            '.kr': 'ko',      # Korean
            '.ru': 'ru',      # Russian
            '.com': 'en',     # English (international)
            '.org': 'en',     # English
            '.net': 'en',     # English
            '.edu': 'en',     # English
            '.gov': 'en',     # English
        }
        
        domain_lower = domain.lower()
        for ext, lang in domain_lang_map.items():
            if domain_lower.endswith(ext):
                return lang
        
        # Default to English if unknown
        return 'en'
    
    def _detect_language(self, url: str) -> str:
        """Detect language from URL path or domain."""
        path = urlparse(url).path.lower()
        
        # Extract language code from path (e.g., /en/, /no/, /fr/, /de/)
        lang_codes = ['en', 'no', 'nb', 'nn', 'fr', 'de', 'es', 'it', 'pt', 'zh', 'ja', 'ru', 'ar', 'ko', 'sv', 'da', 'fi', 'nl', 'pl', 'cs']
        lang_code = None
        
        for code in lang_codes:
            if f'/{code}/' in path or f'/{code}-' in path or path.endswith(f'/{code}') or path.startswith(f'{code}/'):
                lang_code = code
                break
        
        # If no language in path, use base language from domain
        if not lang_code:
            lang_code = self.base_language
        
        # Return the language name (or code if name not found)
        return self.language_names.get(lang_code, lang_code.capitalize())
    
    def _categorize_page(self, url: str) -> str:
        """Extract the first subdirectory from URL path as category."""
        path = urlparse(url).path.strip('/')
        
        # If it's the root or empty path
        if not path:
            return 'home'
        
        # Get the first subdirectory (first segment of the path)
        # Skip language codes if they're the first segment
        parts = path.split('/')
        
        # Filter out common language codes
        lang_codes = ['en', 'no', 'nb', 'nn', 'fr', 'de', 'es', 'it', 'pt', 'zh', 'ja', 'ru', 'ar', 'ko']
        
        for part in parts:
            # If this part is not a language code and not empty, use it as category
            if part and part.lower() not in lang_codes:
                return part.lower()
        
        # If all parts were language codes, use the first one anyway
        if parts and parts[0]:
            return parts[0].lower()
        
        return 'home'
    
    def is_valid_url(self, url: str) -> bool:
        """Check if URL should be crawled."""
        parsed = urlparse(url)
        
        # Only crawl HTTP/HTTPS URLs from the same domain
        if parsed.scheme not in ['http', 'https']:
            return False
        
        if parsed.netloc != self.base_domain:
            return False
        
        # Skip common non-HTML files
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
        # Remove fragment and rebuild URL
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        # Remove trailing slash except for root
        if normalized.endswith('/') and len(parsed.path) > 1:
            normalized = normalized[:-1]
        
        # Add query string if present
        if parsed.query:
            normalized += f"?{parsed.query}"
        
        return normalized
    
    def extract_text(self, soup: BeautifulSoup) -> str:
        """Extract visible text from HTML."""
        # Remove script and style elements
        for script in soup(['script', 'style', 'meta', 'noscript']):
            script.decompose()
        
        # Get text
        text = soup.get_text()
        
        # Clean up text
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text
    
    def count_words(self, text: str) -> int:
        """Count words in text."""
        # Split on whitespace and count non-empty words
        words = re.findall(r'\b[a-zA-Z0-9]+\b', text)
        return len(words)
    
    def crawl_page(self, url: str) -> Set[str]:
        """
        Crawl a single page and return found links.
        
        Returns:
            Set of URLs found on the page
        """
        found_urls = set()
        
        try:
            print(f"Crawling: {url}")
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            # Only process HTML content
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type:
                print(f"  Skipping non-HTML content: {content_type}")
                return found_urls
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract page title before decomposing elements
            page_title = soup.title.string.strip() if soup.title and soup.title.string else ""
            
            # Extract and count words
            text = self.extract_text(soup)
            word_count = self.count_words(text)
            category = self._categorize_page(url)
            language = self._detect_language(url)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Thread-safe update of statistics
            with self.stats_lock:
                self.word_count_by_page[url] = word_count
                self.page_contents[url] = text  # Store the actual content
                self.page_titles[url] = page_title
                self.page_timestamps[url] = timestamp
                self.page_categories[url] = category
                self.page_languages[url] = language
                self.total_words += word_count
                total_so_far = self.total_words
            
            print(f"  Words on this page: {word_count:,} [{language}]")
            print(f"  Total words so far: {total_so_far:,}")
            
            # Find all links
            for link in soup.find_all('a', href=True):
                absolute_url = urljoin(url, link['href'])
                normalized_url = self.normalize_url(absolute_url)
                
                # Thread-safe check for visited URLs
                with self.visited_lock:
                    if self.is_valid_url(normalized_url) and normalized_url not in self.visited_urls:
                        found_urls.add(normalized_url)
        
        except requests.RequestException as e:
            print(f"  Error crawling {url}: {e}")
        except Exception as e:
            print(f"  Unexpected error on {url}: {e}")
        
        return found_urls
    
    def crawl(self, max_pages: int = None):
        """
        Start crawling from the base URL using concurrent threads.
        
        Args:
            max_pages: Maximum number of pages to crawl (None = unlimited, default: None)
        """
        print(f"Starting crawl of {self.base_url}")
        print(f"Domain: {self.base_domain}")
        print(f"Base language (from domain): {self.language_names.get(self.base_language, self.base_language.capitalize())}")
        print(f"Concurrent workers: {self.max_workers}")
        print(f"⚠️  WARNING: No JavaScript support - use crawler_js.py for JavaScript sites")
        print(f"Max pages: {'Unlimited' if max_pages is None else max_pages}")
        print("-" * 60)
        
        # Queue of URLs to visit
        to_visit = deque([self.base_url])
        self.visited_urls.add(self.base_url)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            
            while to_visit or futures:
                # Submit new tasks while we have URLs and haven't hit the limit
                reached_limit = max_pages is not None and len(self.visited_urls) >= max_pages
                while to_visit and not reached_limit and len(futures) < self.max_workers * 2:
                    url = to_visit.popleft()
                    
                    # Submit the crawl task
                    future = executor.submit(self.crawl_page, url)
                    futures[future] = url
                    
                    # Be polite - small delay between submissions
                    if self.delay > 0:
                        time.sleep(self.delay)
                    
                    # Update limit check
                    reached_limit = max_pages is not None and len(self.visited_urls) >= max_pages
                
                # Process completed tasks
                if futures:
                    done, _ = as_completed(futures, timeout=1), None
                    for future in list(futures.keys()):
                        if future.done():
                            url = futures.pop(future)
                            try:
                                found_urls = future.result()
                                
                                # Add new URLs to queue (thread-safe)
                                for new_url in found_urls:
                                    with self.visited_lock:
                                        can_add = new_url not in self.visited_urls
                                        if max_pages is not None:
                                            can_add = can_add and len(self.visited_urls) < max_pages
                                        
                                        if can_add:
                                            self.visited_urls.add(new_url)
                                            to_visit.append(new_url)
                            except Exception as e:
                                print(f"Error processing {url}: {e}")
                            
                            print()
        
        print("-" * 60)
        print("\nCrawl Complete!")
        self.print_statistics()
    
    def print_statistics(self):
        """Print crawl statistics."""
        print(f"\n{'='*60}")
        print("CRAWL STATISTICS")
        print(f"{'='*60}")
        print(f"Base language (from domain): {self.language_names.get(self.base_language, self.base_language.capitalize())}")
        print(f"Total pages crawled: {len(self.visited_urls):,}")
        print(f"Total words found: {self.total_words:,}")
        print(f"Average words per page: {self.total_words / len(self.visited_urls):.1f}" if self.visited_urls else "N/A")
        
        # Language breakdown
        if self.page_languages:
            print(f"\n{'='*60}")
            print("BREAKDOWN BY LANGUAGE")
            print(f"{'='*60}")
            
            # Calculate stats per language
            language_stats = {}
            for url, language in self.page_languages.items():
                if language not in language_stats:
                    language_stats[language] = {'count': 0, 'words': 0}
                language_stats[language]['count'] += 1
                language_stats[language]['words'] += self.word_count_by_page.get(url, 0)
            
            # Sort by count (most pages first)
            sorted_languages = sorted(language_stats.items(), key=lambda x: x[1]['count'], reverse=True)
            
            print(f"\n{'Language':<15} {'Pages':<10} {'Total Words':<15} {'Avg Words/Page':<15}")
            print("-" * 60)
            for language, stats in sorted_languages:
                avg_words = stats['words'] / stats['count'] if stats['count'] > 0 else 0
                print(f"{language:<15} {stats['count']:<10,} {stats['words']:<15,} {avg_words:<15.1f}")
            
            # Category breakdown per language
            for language, lang_stats in sorted_languages:
                print(f"\n{'='*60}")
                print(f"BREAKDOWN BY CATEGORY - {language}")
                print(f"{'='*60}")
                
                # Calculate stats per category for this language
                category_stats = {}
                for url, page_lang in self.page_languages.items():
                    if page_lang == language:
                        category = self.page_categories.get(url, 'unknown')
                        if category not in category_stats:
                            category_stats[category] = {'count': 0, 'words': 0}
                        category_stats[category]['count'] += 1
                        category_stats[category]['words'] += self.word_count_by_page.get(url, 0)
                
                # Sort by count and limit to top 10
                sorted_categories = sorted(category_stats.items(), key=lambda x: x[1]['count'], reverse=True)[:10]
                
                print(f"\n{'Category':<20} {'Pages':<10} {'Total Words':<15} {'Avg Words/Page':<15}")
                print("-" * 60)
                for category, stats in sorted_categories:
                    avg_words = stats['words'] / stats['count'] if stats['count'] > 0 else 0
                    print(f"{category.capitalize():<20} {stats['count']:<10,} {stats['words']:<15,} {avg_words:<15.1f}")
        
        # Top 10 pages by word count
        if self.word_count_by_page:
            print(f"\n{'='*60}")
            print("TOP 10 PAGES BY WORD COUNT")
            print(f"{'='*60}")
            sorted_pages = sorted(self.word_count_by_page.items(), key=lambda x: x[1], reverse=True)[:10]
            for i, (url, count) in enumerate(sorted_pages, 1):
                category = self.page_categories.get(url, 'unknown')
                language = self.page_languages.get(url, 'unknown')
                print(f"  {i}. {count:,} words [{language}] [{category}] - {url}")
    
    def save_results(self, filename: str = "crawl_results.txt"):
        """Save results to a file."""
        with open(filename, 'w') as f:
            f.write(f"Web Crawl Results for {self.base_url}\n")
            f.write(f"{'='*60}\n\n")
            f.write(f"Base language (from domain): {self.language_names.get(self.base_language, self.base_language.capitalize())}\n")
            f.write(f"Total pages crawled: {len(self.visited_urls):,}\n")
            f.write(f"Total words found: {self.total_words:,}\n")
            f.write(f"Average words per page: {self.total_words / len(self.visited_urls):.1f}\n\n" if self.visited_urls else "N/A\n\n")
            
            # Language breakdown
            if self.page_languages:
                f.write(f"\n{'='*60}\n")
                f.write("BREAKDOWN BY LANGUAGE\n")
                f.write(f"{'='*60}\n\n")
                
                # Calculate stats per language
                language_stats = {}
                for url, language in self.page_languages.items():
                    if language not in language_stats:
                        language_stats[language] = {'count': 0, 'words': 0}
                    language_stats[language]['count'] += 1
                    language_stats[language]['words'] += self.word_count_by_page.get(url, 0)
                
                # Sort by count (most pages first)
                sorted_languages = sorted(language_stats.items(), key=lambda x: x[1]['count'], reverse=True)
                
                f.write(f"{'Language':<15} {'Pages':<10} {'Total Words':<15} {'Avg Words/Page':<15}\n")
                f.write("-" * 60 + "\n")
                for language, stats in sorted_languages:
                    avg_words = stats['words'] / stats['count'] if stats['count'] > 0 else 0
                    f.write(f"{language:<15} {stats['count']:<10,} {stats['words']:<15,} {avg_words:<15.1f}\n")
                
                # Category breakdown per language
                for language, lang_stats in sorted_languages:
                    f.write(f"\n{'='*60}\n")
                    f.write(f"BREAKDOWN BY CATEGORY - {language}\n")
                    f.write(f"{'='*60}\n\n")
                    
                    # Calculate stats per category for this language
                    category_stats = {}
                    for url, page_lang in self.page_languages.items():
                        if page_lang == language:
                            category = self.page_categories.get(url, 'unknown')
                            if category not in category_stats:
                                category_stats[category] = {'count': 0, 'words': 0}
                            category_stats[category]['count'] += 1
                            category_stats[category]['words'] += self.word_count_by_page.get(url, 0)
                    
                    # Sort by count and limit to top 10
                    sorted_categories = sorted(category_stats.items(), key=lambda x: x[1]['count'], reverse=True)[:10]
                    
                    f.write(f"{'Category':<20} {'Pages':<10} {'Total Words':<15} {'Avg Words/Page':<15}\n")
                    f.write("-" * 60 + "\n")
                    for category, stats in sorted_categories:
                        avg_words = stats['words'] / stats['count'] if stats['count'] > 0 else 0
                        f.write(f"{category.capitalize():<20} {stats['count']:<10,} {stats['words']:<15,} {avg_words:<15.1f}\n")
            
            f.write(f"\n{'='*60}\n")
            f.write("Word count by page:\n")
            f.write("-" * 60 + "\n")
            
            sorted_pages = sorted(self.word_count_by_page.items(), key=lambda x: x[1], reverse=True)
            for url, count in sorted_pages:
                category = self.page_categories.get(url, 'unknown')
                language = self.page_languages.get(url, 'unknown')
                f.write(f"{count:,} words [{language}] [{category}] - {url}\n")
        
        print(f"\nResults saved to {filename}")
    
    def save_results_csv(self, output_dir: str = "results"):
        """Save results to a CSV file matching crawler.py format."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Clean domain name for filename
        domain_parts = self.base_domain.replace('www.', '').split('.')
        safe_name = domain_parts[0] if domain_parts else 'unknown'
        
        filename = os.path.join(output_dir, f"{safe_name}.csv")
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Row 1: Domain URL, Date Updated, Technologies (empty for trad crawler)
                date_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([self.base_url, date_updated, ""])
                
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


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = "https://www.equinor.com/"
    
    # Optional: max pages limit (0 or 'unlimited' = no limit, default: None/unlimited)
    if len(sys.argv) > 2:
        max_pages_arg = sys.argv[2].lower()
        if max_pages_arg in ['0', 'unlimited', 'all', 'none']:
            max_pages = None
        else:
            max_pages = int(max_pages_arg)
    else:
        max_pages = None  # Default to unlimited
    
    # Optional: delay between requests (default 0.1 seconds for concurrent mode)
    delay = float(sys.argv[3]) if len(sys.argv) > 3 else 0.1
    
    # Optional: number of concurrent workers (default 5)
    max_workers = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    
    crawler = WebCrawler(url, delay=delay, max_workers=max_workers)
    crawler.crawl(max_pages=max_pages)
    crawler.save_results()
    crawler.save_results_csv()


if __name__ == "__main__":
    main()

