import asyncio
import aiohttp
import json
import re
import time
import random
import os
from urllib.parse import urlparse

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def log(msg, color=Colors.ENDC, symbol="*"):
    time_str = time.strftime("%H:%M:%S")
    print(f"{Colors.BOLD}[{time_str}]{Colors.ENDC} {color}[{symbol}] {msg}{Colors.ENDC}")

# CRITICAL FIX: No 'br' (Brotli) to prevent JSON parse errors natively
GLOBAL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate", 
    "Referer": "https://www.moviesbazar.tv/",
    "Origin": "https://www.moviesbazar.tv",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "Connection": "keep-alive"
}

async def fetch_url_async(session, url, is_post=False, post_data=None, retries=3):
    """Asynchronously fetches a URL with built-in retries to prevent failures."""
    for attempt in range(retries):
        try:
            if is_post:
                async with session.post(url, json=post_data, headers={"Content-Type": "application/json"}, timeout=30) as res:
                    text = await res.text()
                    return {'error': False, 'data': text, 'code': res.status}
            else:
                async with session.get(url, timeout=30) as res:
                    text = await res.text()
                    return {'error': False, 'data': text, 'code': res.status}
        except Exception as e:
            if attempt == retries - 1:
                return {'error': True, 'data': str(e), 'code': 0}
            await asyncio.sleep(1) # Wait before retry

def get_category_name(url):
    parts = [p for p in url.split('/') if p]
    return parts[-1].replace('-', ' ').title()

def generate_slug(title):
    if not title: return 'movie'
    slug = re.sub(r'[^A-Za-z0-9]+', '-', title).strip('-').lower()
    return slug if slug else 'movie'

def format_date(raw_date):
    if not raw_date: return ""
    raw_date = str(raw_date).split('T')[0]
    parts = raw_date.split('-')
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return raw_date

def extract_movies_recursive(data, movies):
    if isinstance(data, dict):
        if 'title' in data and ('_id' in data or 'id' in data or 'imdbId' in data):
            movies.append(data)
        else:
            for key, value in data.items():
                extract_movies_recursive(value, movies)
    elif isinstance(data, list):
        for item in data:
            extract_movies_recursive(item, movies)
    return movies

def format_movie_data(merged_data, detail_html, category_name):
    movie_id = merged_data.get('_id') or merged_data.get('id') or str(merged_data.get('imdbId', '')).replace('tt', '')
    raw_title = str(merged_data.get('title') or "Unknown Title")
    year = str(merged_data.get('year') or merged_data.get('releaseYear') or "")
    
    if not year:
        year_match = re.search(r'\((\d{4})\)', raw_title)
        if year_match: year = year_match.group(1)
            
    clean_title = re.sub(r'\s*\(\d{4}\)', '', raw_title).strip()
    title = f"{clean_title} ({year})" if year else clean_title
        
    streaming_links = []
    unescaped_html = detail_html.replace('\\"', '"').replace('\\/', '/')
    
    wl_match = re.search(r'"watchLink"\s*:\s*(\[\{.*?\}\])', unescaped_html)
    pl_match = re.search(r'"playList"\s*:\s*(\[\{.*?\}\])', unescaped_html)
    
    if wl_match:
        try: streaming_links.extend(json.loads(wl_match.group(1)))
        except: pass
    if pl_match and not streaming_links:
        try: streaming_links.extend(json.loads(pl_match.group(1)))
        except: pass
        
    best_m3u8 = ""
    if streaming_links:
        for link in streaming_links:
            if isinstance(link, dict) and link.get('source') and '.m3u8' in str(link.get('source')):
                best_m3u8 = link['source']
                break 

    if not best_m3u8:
        m3u8s = re.findall(r'(https:\/\/[^"\'\s]+\.m3u8[^"\'\s]*)', unescaped_html, re.IGNORECASE)
        if m3u8s: best_m3u8 = m3u8s[0]

    director = merged_data.get('director', "Unknown")
    if isinstance(director, list):
        director = ", ".join([str(d.get('name', d)) if isinstance(d, dict) else str(d) for d in director]) if director else "Unknown"

    genre = merged_data.get('genre', ["Unknown"])
    if isinstance(genre, str): genre = [g.strip() for g in genre.split(',')]
    elif isinstance(genre, list): genre = [str(g.get('name', g)) if isinstance(g, dict) else str(g) for g in genre]

    try: imdb_votes = int(str(merged_data.get('imdbVotes', 0)).replace(',', ''))
    except: imdb_votes = 0

    language = merged_data.get('language', "Unknown")
    if isinstance(language, list): language = ", ".join(language) if language else "Unknown"

    poster_url = merged_data.get('poster') or merged_data.get('posterUrl') or merged_data.get('thumbnail') or ""
    if not poster_url:
        thm_match = re.search(r'property="og:image"\s+content="([^"]+)"', detail_html, re.IGNORECASE)
        if thm_match: poster_url = thm_match.group(1)

    slider_url = merged_data.get('backdrop') or merged_data.get('sliderUrl') or poster_url
    
    if poster_url and poster_url.startswith('/'): poster_url = "https://www.moviesbazar.tv" + poster_url
    if slider_url and slider_url.startswith('/'): slider_url = "https://www.moviesbazar.tv" + slider_url

    storyline = str(merged_data.get('storyline') or merged_data.get('overview') or merged_data.get('description', "No storyline available."))
    storyline = re.sub(r'<[^>]+>', '', storyline).strip() 

    return {
        "id": str(movie_id),
        "category": category_name,
        "director": director,
        "genre": genre,
        "imdbRating": str(merged_data.get('imdbRating') or merged_data.get('rating', "0")),
        "imdbVotes": imdb_votes,
        "language": language,
        "posterUrl": poster_url,
        "releaseDate": format_date(merged_data.get('releaseDate') or merged_data.get('released', "")),
        "sliderUrl": slider_url,
        "status": "on",
        "storyline": storyline,
        "streamUrl": best_m3u8,
        "title": title,
        "headers": {
            "referer": "https://www.moviesbazar.tv/",
            "origin": "",
            "user_agent": ""
        }
    }

async def process_single_movie(session, url, raw_movie_data, category_name, semaphore):
    """Processes detail extraction concurrently with a strict connection limit."""
    async with semaphore:
        detail_res = await fetch_url_async(session, url)
        if detail_res['error'] or detail_res['code'] != 200:
            return None
            
        detail_html = detail_res['data']
        
        next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', detail_html, re.DOTALL)
        if next_data_match:
            try:
                full_next_json = json.loads(next_data_match.group(1))
                next_movies = []
                extract_movies_recursive(full_next_json, next_movies)
                if next_movies:
                    raw_movie_data.update(next_movies[0])
            except: pass
            
        formatted_movie = format_movie_data(raw_movie_data, detail_html, category_name)
        
        if formatted_movie['streamUrl']:
             log(f"Found M3U8: {formatted_movie['title']}", Colors.GREEN, "✓")
        else:
             log(f"No M3U8 for: {formatted_movie['title']}", Colors.WARNING, "!")
             
        return formatted_movie

async def scrape_category_async(base_cat_url, session):
    category_name = get_category_name(base_cat_url)
    log(f"STARTING ASYNC SCRAPE: {category_name}", Colors.HEADER, "🚀")
    
    # 1. Fetch Initial Page
    res = await fetch_url_async(session, base_cat_url)
    html = res['data']
    
    api_match = re.search(r'"apiUrl"\s*:\s*"([^"]+)"', html)
    api_path = api_match.group(1).strip('/') if api_match else urlparse(base_cat_url).path.replace('/browse/', '').strip('/')
    
    initial_filter = {"genre": "all", "dateSort": -1}
    filter_match = re.search(r'"initialFilter"\s*:\s*(\{.*?\})', html)
    if filter_match:
        try: initial_filter = json.loads(filter_match.group(1).replace('\\"', '"'))
        except: pass

    api_url = f"https://moviesbazar-api-v16.vercel.app/{api_path}" if api_path.startswith('api/v1/movies/') else f"https://moviesbazar-api-v16.vercel.app/api/v1/movies/{api_path}"
    
    log(f"Detected API: {api_url}", Colors.CYAN, "i")
    
    unique_links = {}
    current_page = 1
    has_more = True
    fails = 0
    
    # 2. Sequential Paginated API Extraction (Fast process)
    while has_more:
        log(f"Fetching API Page {current_page} for {category_name}...", Colors.BLUE, "↻")
        skip = (current_page - 1) * 40
        payload = {
            "limit": 40,
            "page": random.randint(100, 9999), 
            "skip": skip,
            "bodyData": { "filterData": initial_filter }
        }
        
        api_res = await fetch_url_async(session, api_url, is_post=True, post_data=payload)
        
        if api_res['error'] or api_res['code'] != 200:
            fails += 1
            log(f"API HTTP {api_res['code']}. Retrying...", Colors.WARNING, "!")
            if fails >= 2: has_more = False
            await asyncio.sleep(2)
            continue
            
        try:
            api_json = json.loads(api_res['data'])
            movie_array = []
            extract_movies_recursive(api_json, movie_array)
            
            added = 0
            for movie in movie_array:
                m_id = movie.get('_id') or movie.get('id') or str(movie.get('imdbId', '')).replace('tt', '')
                if not m_id: continue
                title_slug = generate_slug(movie.get('title'))
                m_type = movie.get('type', 'movie')
                movie_url = f"https://www.moviesbazar.tv/watch/{m_type}/{title_slug}/{m_id}"
                
                if movie_url not in unique_links:
                    unique_links[movie_url] = movie
                    added += 1
                    
            if added > 0:
                log(f"Found {added} new links. Total pending: {len(unique_links)}", Colors.GREEN, "✓")
                current_page += 1
                fails = 0
            else:
                log("End of pagination reached.", Colors.WARNING, "!")
                has_more = False
        except Exception as e:
            log(f"API parse error: {e}", Colors.FAIL, "X")
            has_more = False

    if not unique_links:
        log("No links found. Skipping.", Colors.WARNING, "!")
        return

    # 3. High-Speed Concurrent Extraction Phase
    log(f"⚡ Launching High-Speed Concurrent Extraction for {len(unique_links)} movies...", Colors.HEADER, "⚡")
    output_filename = f"{category_name.replace(' ', '_').lower()}.json"
    
    # We will process 20 movies SIMULTANEOUSLY (adjust if Cloudflare blocks you, but 20 is safe)
    concurrency_limit = 20 
    semaphore = asyncio.Semaphore(concurrency_limit)
    
    tasks = []
    final_movies_list = []
    items_list = list(unique_links.items())
    
    # Batch processing so we can save incrementally without losing data!
    batch_size = 200 
    
    for i in range(0, len(items_list), batch_size):
        batch = items_list[i:i+batch_size]
        log(f"Processing batch {i//batch_size + 1} ({len(batch)} items)...", Colors.CYAN, "⚙")
        
        batch_tasks = [process_single_movie(session, url, data, category_name, semaphore) for url, data in batch]
        
        # Run the batch concurrently
        results = await asyncio.gather(*batch_tasks)
        
        # Filter out failed extractions
        valid_results = [res for res in results if res is not None]
        final_movies_list.extend(valid_results)
        
        # SAVE INCREMENTALLY! If it gets cancelled, previous batches are safe!
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(final_movies_list, f, indent=4, ensure_ascii=False)
            
        log(f"💾 BATCH AUTO-SAVED! Total secured: {len(final_movies_list)}/{len(unique_links)}", Colors.WARNING, "💾")

    log(f"✅ {category_name} COMPLETELY SCRAPED! Final count: {len(final_movies_list)}", Colors.GREEN, "🎉")
    print("\n" + "="*50 + "\n")

async def main():
    target_categories = [
        "https://www.moviesbazar.tv/browse/category/hollywood",
        "https://www.moviesbazar.tv/browse/category/new-release",
        "https://www.moviesbazar.tv/browse/category/hindi-dubbed",
        "https://www.moviesbazar.tv/browse/category/bengali"
    ]
    
    print(f"{Colors.BOLD}{Colors.HEADER}⚡ MoviesBazar ULTRA-FAST ASYNC Scraper Initialized ⚡{Colors.ENDC}")
    print("="*50 + "\n")
    
    # Use a custom TCPConnector to handle multiple concurrent connections safely
    connector = aiohttp.TCPConnector(limit=50)
    async with aiohttp.ClientSession(headers=GLOBAL_HEADERS, connector=connector) as session:
        for url in target_categories:
            await scrape_category_async(url, session)
            await asyncio.sleep(2) # Brief pause between giant categories

    log("ALL CATEGORIES CONCURRENTLY SCRAPED SUCCESSFULLY!", Colors.HEADER, "🏆")

if __name__ == "__main__":
    # Handle event loop policies for Windows compatibility
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
