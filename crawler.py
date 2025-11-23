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
        self.page_categories: Dict[str, str] = {}
        self.page_languages: Dict[str, str] = {}
        self.total_words = 0
        self.lock = asyncio.Lock()
        
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
            
            async with self.lock:
                self.word_count_by_page[url] = word_count
                self.page_categories[url] = category
                self.page_languages[url] = language
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
                
                if max_pages and len(self.visited_urls) >= max_pages:
                    queue.task_done()
                    break
                
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
    
    def save_results(self, filename: str = "crawl_results.txt"):
        """Save results to a file."""
        with open(filename, 'w') as f:
            f.write(f"Web Crawl Results for {self.base_url}\n")
            f.write(f"JavaScript rendering: ENABLED (Concurrent)\n")
            f.write(f"Workers: {self.max_workers}\n")
            f.write(f"{'='*60}\n\n")
            
            f.write(f"Total pages crawled: {len(self.visited_urls):,}\n")
            f.write(f"Total words found: {self.total_words:,}\n")
            f.write(f"Average words per page: {self.total_words / len(self.visited_urls):.1f}\n\n" if self.visited_urls else "N/A\n\n")
            
            f.write(f"{'='*60}\n")
            f.write("Word count by page:\n")
            f.write("-" * 60 + "\n")
            
            sorted_pages = sorted(self.word_count_by_page.items(), key=lambda x: x[1], reverse=True)
            for url, count in sorted_pages:
                category = self.page_categories.get(url, 'unknown')
                language = self.page_languages.get(url, 'unknown')
                f.write(f"{count:,} words [{language}] [{category}] - {url}\n")
        
        print(f"\nResults saved to {filename}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Concurrent Web Crawler with JavaScript Support")
    parser.add_argument("url", help="The starting URL to crawl")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum number of pages to crawl (default: unlimited)")
    parser.add_argument("--delay", type=float, default=0.1, help="Delay between requests in seconds (default: 0.1)")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent workers (default: 5)")
    parser.add_argument("--no-headless", action="store_true", help="Run browser in visible mode")
    parser.add_argument("--no-fast", action="store_true", help="Disable fast mode (resource blocking)")
    
    args = parser.parse_args()
    
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


if __name__ == "__main__":
    main()

