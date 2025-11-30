import os
import csv
from datetime import datetime
from collections import defaultdict
import re

results_dir = r'c:\Users\User\Desktop\testCrawler\results'
csv_files = [f for f in os.listdir(results_dir) if f.endswith('.csv') and f != 'domain_analysis.csv']

total_words = 0
website_stats = []
daily_stats = defaultdict(int)
total_pages = 0
websites_with_content = 0
websites_without_content = 0

for csv_file in csv_files:
    filepath = os.path.join(results_dir, csv_file)
    website_name = csv_file.replace('.csv', '')
    website_words = 0
    page_count = 0
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
            # Find the html2text column index
            html2text_idx = 1  # default
            timestamp_idx = 3  # default
            
            for i, row in enumerate(rows):
                if i == 0:  # First row - might be metadata
                    continue
                if len(row) >= 2 and row[0] == 'url':  # Header row
                    for j, col in enumerate(row):
                        if col == 'html2text':
                            html2text_idx = j
                        if col == 'timestamp':
                            timestamp_idx = j
                    continue
                    
                if len(row) > html2text_idx:
                    content = row[html2text_idx]
                    if content and content.strip():
                        words = len(content.split())
                        website_words += words
                        page_count += 1
                        
                        # Get date for daily stats
                        if len(row) > timestamp_idx and row[timestamp_idx]:
                            try:
                                date_str = row[timestamp_idx].split(' ')[0]
                                if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
                                    daily_stats[date_str] += words
                            except:
                                pass
    except Exception as e:
        print(f'Error reading {csv_file}: {e}')
        continue
    
    if website_words > 0:
        websites_with_content += 1
    else:
        websites_without_content += 1
    
    website_stats.append((website_name, website_words, page_count))
    total_words += website_words
    total_pages += page_count

# Sort by word count descending
website_stats.sort(key=lambda x: x[1], reverse=True)

print('='*70)
print('WEBSITE SCRAPING STATISTICS')
print('='*70)
print()
print(f'Total websites scraped: {len(website_stats)}')
print(f'  - With scraped content: {websites_with_content}')
print(f'  - Without content (URLs only): {websites_without_content}')
print(f'Total pages with content: {total_pages}')
print(f'Total words scraped: {total_words:,}')
if websites_with_content > 0:
    print(f'Average words per website (with content): {total_words // websites_with_content:,}')
if total_pages > 0:
    print(f'Average words per page: {total_words // total_pages:,}')
print()
print('='*70)
print('TOP 15 WEBSITES BY WORD COUNT')
print('='*70)
header = "Website".ljust(25) + "Words".rjust(12) + "Pages".rjust(8) + "Avg/Page".rjust(10)
print(header)
print('-'*55)
for name, words, pages in website_stats[:15]:
    avg = words // pages if pages else 0
    line = name[:24].ljust(25) + f"{words:,}".rjust(12) + str(pages).rjust(8) + f"{avg:,}".rjust(10)
    print(line)

print()
print('='*70)
print('BOTTOM 10 WEBSITES BY WORD COUNT')
print('='*70)
header = "Website".ljust(25) + "Words".rjust(12) + "Pages".rjust(8) + "Avg/Page".rjust(10)
print(header)
print('-'*55)
for name, words, pages in website_stats[-10:]:
    avg = words // pages if pages else 0
    line = name[:24].ljust(25) + f"{words:,}".rjust(12) + str(pages).rjust(8) + f"{avg:,}".rjust(10)
    print(line)

print()
print('='*70)
print('WORDS SCRAPED PER DAY')
print('='*70)
daily_sorted = sorted(daily_stats.items())
total_daily_words = 0
for date, words in daily_sorted:
    print(f'{date}: {words:,} words')
    total_daily_words += words

if daily_sorted:
    avg_per_day = total_daily_words // len(daily_sorted)
    print()
    print(f'Average words per day: {avg_per_day:,}')
    print(f'Number of scraping days: {len(daily_sorted)}')

print()
print('='*70)
print('WEBSITES WITH CONTENT (sorted by word count)')
print('='*70)
header = "Website".ljust(25) + "Words".rjust(12) + "Pages".rjust(8) + "Avg/Page".rjust(10)
print(header)
print('-'*55)
websites_with_words = [(name, words, pages) for name, words, pages in website_stats if words > 0]
for name, words, pages in websites_with_words:
    avg = words // pages if pages else 0
    line = name[:24].ljust(25) + f"{words:,}".rjust(12) + str(pages).rjust(8) + f"{avg:,}".rjust(10)
    print(line)
