# Web Crawler - Word Counter

A Python web crawler that counts words across all pages of a website using Playwright for JavaScript support.

## 🚀 Quick Start

### Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

### crawler.py

**Best for:** JavaScript sites, Single Page Applications (React, Vue, Angular), and static sites.

```bash
# Basic usage
python crawler.py https://example.com/

# Customize concurrency and limits
python crawler.py https://example.com/ --workers 10 --max-pages 100
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `url` | The starting URL to crawl | (Required) |
| `--workers` | Number of concurrent workers | 5 |
| `--max-pages` | Maximum number of pages to crawl | Unlimited |
| `--delay` | Delay between requests in seconds | 0.1 |
| `--no-headless` | Run browser in visible mode | False (Headless) |
| `--no-fast` | Disable fast mode (resource blocking) | False (Fast mode enabled) |

### 2. crawler_js.py - JavaScript-Enabled Crawler

**Best for:** Modern websites, accurate per-page word counts

```bash
# Basic usage
python crawler_js.py https://conta.no/

# Limit to 200 pages
python crawler_js.py https://conta.no/ 200

# Custom delay between requests
python crawler_js.py https://conta.no/ 200 0.5

# Disable fast mode for more complete loading (slower but more thorough)
python crawler_js.py https://conta.no/ 200 0.1 true false

# Show browser window (debug mode)
python crawler_js.py https://conta.no/ 50 0.5 false
```

**Features:**
- ✅ Executes JavaScript (sees actual page content)
- ✅ Waits for dynamic content to load
- ✅ Accurate word count per page
- ⚠️ Slower than crawler.py (sequential crawling)
- ⚠️ Counts boilerplate on every page (normal behavior)

**Output:**
```
crawl_results_js.txt
- Per-page word counts
- Language detection
- Category breakdown
```

---

### 3. crawler_unique.py - Advanced with Boilerplate Detection

**Best for:** Content audits, identifying unique vs repeated content

```bash
# Basic usage
python crawler_unique.py https://conta.no/

# Limit to 100 pages
python crawler_unique.py https://conta.no/ 100

# Disable category-differential detection (if you only want global boilerplate)
python crawler_unique.py https://conta.no/ 100 0.1 true true false
```

**Features:**
- ✅ Everything from crawler_js.py
- ✅ Detects common boilerplate (headers, footers, navigation)
- ✅ Detects category-specific duplicates (NEW! 🎯)
- ✅ Shows total / unique / category-unique word counts
- ✅ Reports boilerplate percentage
- ⚡ Fast mode enabled by default

**Output:**
```
Page 1: 2,387 total / 387 unique words
Page 2: 2,156 total / 256 unique words
Page 3: 2,498 total / 498 unique words

Summary:
  Total words (with boilerplate): 7,041
  Unique words (excluding boilerplate): 3,141
  Boilerplate: 3,900 words (55.4%)
```

Saves to `crawl_results_unique.txt`

---

### 4. crawler_js_concurrent.py - Fastest JavaScript Crawler 🔥

**Best for:** When you need speed AND JavaScript support

```bash
# Basic usage (5 concurrent workers by default)
python crawler_js_concurrent.py https://conta.no/

# Limit to 200 pages
python crawler_js_concurrent.py https://conta.no/ 200

# Use 10 concurrent workers for even faster crawling
python crawler_js_concurrent.py https://conta.no/ 200 0.1 true true 10
#                                                    │   │    │    └── workers
#                                                    │   │    └─────── fast_mode
#                                                    │   └──────────── headless
#                                                    └──────────────── delay
```

**Features:**
- ✅ Everything from crawler_js.py
- ✅ **3-5x faster** with concurrent workers
- ✅ Multiple browser contexts running in parallel
- ⚡ Default 5 workers (adjustable)

**Output:** `crawl_results_js_concurrent.txt`

---

### 5. crawler_unique_concurrent.py - Fastest Unique Content Analysis 🔥

**Best for:** Content audits when you need results fast

```bash
# Basic usage (5 concurrent workers by default)
python crawler_unique_concurrent.py https://conta.no/

# Limit to 100 pages
python crawler_unique_concurrent.py https://conta.no/ 100

# Use 8 concurrent workers
python crawler_unique_concurrent.py https://conta.no/ 100 0.1 true true true 8
#                                                       │   │    │    │    └── workers
#                                                       │   │    │    └─────── category_diff
#                                                       │   │    └──────────── fast_mode
#                                                       │   └───────────────── headless
#                                                       └───────────────────── delay
```

**Features:**
- ✅ Everything from crawler_unique.py
- ✅ **3-5x faster** with concurrent workers
- ✅ Boilerplate & category-differential detection
- ⚡ Default 5 workers (adjustable)

**Output:** `crawl_results_unique_concurrent.txt`

---

## 🎯 Category-Differential Detection (NEW!)

The unique crawler now includes **category-differential detection** which identifies common content **within each subdirectory**. 

### The Problem

When crawling pages in the same section (like `/kontohjelp/konto/...`), each page often shares:
- Category-specific sidebars ("Other accounts in this category...")
- Related articles lists
- Category navigation
- Template boilerplate

**Result:** Every kontohjelp page might show 17K words, but only 500 words are actually unique to that page!

### The Solution

Category-differential mode:
1. **Groups pages by subdirectory** (kontohjelp, blog, products, etc.)
2. **Detects common words within each category** (80% threshold)
3. **Counts only truly unique content** per page

### Output Metrics

You now get **three different word counts**:

| Metric | What It Counts | Use Case |
|--------|---------------|----------|
| **Total words** | Everything including all duplicates | Raw page size |
| **Unique words** | Content after removing headers/footers | Global unique content |
| **Category-unique** | Only differences within category | True unique value per page 🎯 |

### Example Output

```
KONTOHJELP PAGES ANALYSIS (45 pages)
====================================
Total words (with duplicates): 787,500
Average per page: 17,500

Total unique words: 234,000
Average unique per page: 5,200

🎯 CATEGORY-UNIQUE ANALYSIS (only counting differences):
Total category-unique words: 22,500
Average category-unique per page: 500

Sample pages (total / unique / category-unique):
  17,443 / 5,234 / 487 - https://conta.no/kontohjelp/konto/1234
  17,450 / 5,189 / 523 - https://conta.no/kontohjelp/konto/5678
```

This shows that while pages appear to have 17K words, only ~500 words per page are actually unique within the kontohjelp category!

## Understanding Boilerplate/Double-Counting

### The Issue

Traditional crawlers count shared content (headers, footers, navigation) on every page:

```
Page 1: 2,000 boilerplate + 300 unique = 2,300 total
Page 2: 2,000 boilerplate + 250 unique = 2,250 total
Page 3: 2,000 boilerplate + 400 unique = 2,400 total

Traditional total: 6,950 words (counts boilerplate 3x!)
Actual unique: 2,950 words
```

### Which Metric Do You Need?

**Per-page word count** (use `crawler_js.py`):
- "How many words are on this page?" → 2,300 words
- Good for: SEO analysis, readability metrics
- Boilerplate counted on every page (this is correct for per-page metrics)

**Total unique content** (use `crawler_unique.py`):
- "How much unique content across the site?" → 2,950 words
- Good for: Content audits, avoiding inflated numbers
- Boilerplate counted only once

## Real-World Example: conta.no

### Problem Encountered

Using `crawler.py` on conta.no showed:
```
❌ 17,387 words - /kontohjelp/konto/6800-kontorrekvisita
❌ 17,387 words - /kontohjelp/konto/7020-vedlikehold-biler
❌ 17,387 words - /kontohjelp/konto/1920-bankkonto
(All 136 pages identical - WRONG!)
```

**Why?** conta.no uses JavaScript to load content. `crawler.py` doesn't execute JavaScript, so it only sees the initial template (same for all pages).

### Solution 1: Accurate Per-Page Counts

```bash
python crawler_js.py https://conta.no/ 200
```

Result:
```
✅ 2,387 words - /kontohjelp/konto/6800-kontorrekvisita
✅ 2,156 words - /kontohjelp/konto/7020-vedlikehold-biler
✅ 2,498 words - /kontohjelp/konto/1920-bankkonto
(Each page different - CORRECT!)
```

### Solution 2: Unique Content Analysis

```bash
python crawler_unique.py https://conta.no/ 100
```

Result:
```
✅ 2,387 total / 387 unique - /kontohjelp/konto/6800-kontorrekvisita
✅ 2,156 total / 256 unique - /kontohjelp/konto/7020-vedlikehold-biler
✅ 2,498 total / 498 unique - /kontohjelp/konto/1920-bankkonto

Analysis:
  ~2,000 words of boilerplate per page
  ~350 words of unique content per page
  Boilerplate: 83%
```

## Features

- 🕷️ Crawls all pages within a domain
- 🌐 Language detection and filtering
- 📊 Category-based breakdown
- 💾 Saves detailed results to file
- 🔍 Statistics and top pages report
- 🤝 Respects rate limiting
- ⚡ Concurrent crawling with Playwright

## Requirements

```
beautifulsoup4==4.12.3
requests==2.31.0
lxml==5.3.0
playwright==1.48.0
```

## Output Files

- `crawl_results.txt` - Results from crawler.py

## License

See LICENSE file
