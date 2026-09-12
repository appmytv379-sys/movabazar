import requests
import json
import re
import time
import os

# ==========================================
# ADD AS MANY CATEGORY LINKS HERE AS YOU WANT
# ==========================================
TARGET_CATEGORIES = [
    {"url": "https://www.moviesbazar.tv/browse/category/new-release", "name": "recently_added_movies"},
    {"url": "https://www.moviesbazar.tv/browse/category/hollywood", "name": "hollywood_latest_movies"},
    {"url": "https://www.moviesbazar.tv/browse/category/bollywood", "name": "bollywood_all_movies"},
    {"url": "https://www.moviesbazar.tv/browse/category/south", "name": "south_all_movies"},
    {"url": "https://www.moviesbazar.tv/browse/category/hindi", "name": "Hindi_all_movies"},
    {"url": "https://www.moviesbazar.tv/browse/category/hindi-dubbed", "name": "Hindi_Dubbed_all_movies"},
    {"url": "https://www.moviesbazar.tv/browse/category/movies", "name": "Movies_all_movies"},
    {"url": "https://www.moviesbazar.tv/browse/category/bengali", "name": "bengali_all_movies"}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate", # Gzip/Deflate prevents Brotli decode errors in Python
    "Referer": "https://www.moviesbazar.tv/",
    "Origin": "https://www.moviesbazar.tv",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site"
}

COLOR_INFO = "\033[94m" # Blue
COLOR_SUCCESS = "\033[92m" # Green
COLOR_WARNING = "\033[93m" # Yellow
COLOR_ERROR = "\033[91m" # Red
COLOR_TITLE = "\033[95m" # Purple
COLOR_RESET = "\033[0m"

def log(msg, color=COLOR_RESET):
    """Prints formatted timestamped logs to the terminal."""
    current_time = time.strftime("%H:%M:%S")
    print(f"[{current_time}] {color}{msg}{COLOR_RESET}")

def extract_api_path(url):
    """Extracts 'latest/hollywood' from 'https://www.moviesbazar.tv/browse/latest/hollywood'"""
    if '/browse/' in url:
        return url.split('/browse/')[1].strip('/')
    return url.replace('https://www.moviesbazar.tv/', '').strip('/')

def extract_movies_recursive(data):
    """Deeply searches the JSON structure for arrays containing movie objects."""
    if not isinstance(data, (dict, list)):
        return []

    movies = []
    is_movie_list = True
    has_items = False

    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict) or ('imdbId' not in item and '_id' not in item):
                is_movie_list = False
                break
            has_items = True
        
        if has_items and is_movie_list:
            return data
            
        for item in data:
            result = extract_movies_recursive(item)
            if result: return result
            
    elif isinstance(data, dict):
        for key, value in data.items():
            result = extract_movies_recursive(value)
            if result: return result

    return movies

def main():
    # Session automatically handles cookies
    session = requests.Session()
    session.headers.update(HEADERS)
    
    log("\n🚀 Ultimate Scraping Process Initialized...", COLOR_TITLE)

    for idx, category in enumerate(TARGET_CATEGORIES):
        base_url = category["url"]
        file_name = category["name"]
        api_path = extract_api_path(base_url)
        
        log(f"\n==================================================", COLOR_INFO)
        log(f"[Category {idx+1}/{len(TARGET_CATEGORIES)}] STARTING: {file_name.upper()}", COLOR_TITLE)
        log(f"Detected API Path: /api/v1/movies/{api_path}", COLOR_INFO)
        
        unique_movie_links = set()
        category_extracted_data = []

        log("\nPhase 1: Fetching initial HTML page...", COLOR_INFO)
        try:
            res = session.get(base_url, timeout=30)
            res.raise_for_status()
            
            # Extracting the first 40 links directly from HTML
            matches = re.findall(r'href="(/watch/(?:movie|series)/[^"]+)"', res.text, re.IGNORECASE)
            for href in matches:
                unique_movie_links.add("https://www.moviesbazar.tv" + href)
                
            log(f"✅ Found {len(unique_movie_links)} links on base page.", COLOR_SUCCESS)
        except Exception as e:
            log(f"❌ Failed to fetch base page: {e}", COLOR_ERROR)

        log("\nPhase 1.5: Hitting Vercel POST API for Infinite Scroll...", COLOR_INFO)
        current_page = 2
        fails = 0
        
        while True:
            api_url = f"https://moviesbazar-api-v16.vercel.app/api/v1/movies/{api_path}"
            skip = (current_page - 1) * 40
            
            # The Exact Payload Structure needed for the hidden API
            payload = {
                "limit": 40,
                "page": current_page,
                "skip": skip,
                "bodyData": {
                    "filterData": {
                        "genre": "all",
                        "createdAt": -1
                    }
                }
            }
            
            try:
                api_res = session.post(api_url, json=payload, timeout=30)
                
                if api_res.status_code != 200:
                    log(f"⚠️ API returned HTTP {api_res.status_code}. Stopping pagination.", COLOR_WARNING)
                    break
                    
                data = api_res.json()
                movies_array = extract_movies_recursive(data)
                
                if not movies_array:
                    log(f"⚠️ API returned empty data. Reached true end at page {current_page}.", COLOR_WARNING)
                    break
                    
                added = 0
                for movie in movies_array:
                    # Fixing the URL ID pattern
                    imdb_id = movie.get('imdbId', '')
                    m_id = str(imdb_id).replace('tt', '')
                    
                    if not m_id:
                        m_id = str(movie.get('_id', movie.get('id', '')))
                        
                    title = movie.get('title', 'movie')
                    # Creating SEO friendly slugs like the original site
                    title_slug = re.sub(r'[^a-z0-9]+', '-', title.lower().strip()).strip('-')
                    m_type = movie.get('type', 'movie')
                    
                    if m_id and title_slug:
                        link = f"https://www.moviesbazar.tv/watch/{m_type}/{title_slug}/{m_id}"
                        if link not in unique_movie_links:
                            unique_movie_links.add(link)
                            added += 1
                
                log(f"✅ API Page {current_page} fetched. Found {added} new links. Total: {len(unique_movie_links)}", COLOR_SUCCESS)
                current_page += 1
                fails = 0
                
            except Exception as e:
                log(f"❌ Failed API page {current_page}. Error: {e}", COLOR_ERROR)
                fails += 1
                if fails >= 2:
                    log("Too many failures. Moving to Extraction Phase.", COLOR_ERROR)
                    break
            
            # Anti-ban sleep (CRITICAL)
            time.sleep(1.5)

        movie_links_list = list(unique_movie_links)
        log(f"\n✅ Phase 1 Complete. Final URL count for {file_name}: {len(movie_links_list)}", COLOR_TITLE)

        if not movie_links_list:
            log("Skipping extraction, no links found.", COLOR_WARNING)
            continue

        log(f"\nPhase 2: Extracting M3U8 streams for {len(movie_links_list)} movies...", COLOR_INFO)
        
        for j, movie_url in enumerate(movie_links_list):
            try:
                detail_res = session.get(movie_url, timeout=30)
                html = detail_res.text
                
                # Extracting Title
                title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                title = "Unknown Title"
                if title_match:
                    title = title_match.group(1).replace('Watch ', '').replace(' Movie Online Free! | Movies Bazar', '').replace(' Series Online Free! | Movies Bazar', '').strip()
                
                # Extracting Thumbnail
                thumb_match = re.search(r'property="og:image"\s+content="([^"]+)"', html, re.IGNORECASE)
                thumbnail = thumb_match.group(1) if thumb_match else ""
                
                # Unescaping JSON string payloads within HTML
                unescaped_html = html.replace('\\"', '"').replace('\\/', '/')
                
                streaming_links = []
                
                wl_match = re.search(r'"watchLink"\s*:\s*(\[\{.*?\}\])', unescaped_html, re.DOTALL)
                if not wl_match:
                    wl_match = re.search(r'"playList"\s*:\s*(\[\{.*?\}\])', unescaped_html, re.DOTALL)
                    
                if wl_match:
                    try:
                        watch_links = json.loads(wl_match.group(1))
                        for wl in watch_links:
                            if 'source' in wl:
                                streaming_links.append({
                                    "label": wl.get('label', 'Server'),
                                    "source": wl['source']
                                })
                    except json.JSONDecodeError:
                        pass
                
                # Regex Fallback just in case JSON decoding fails
                if not streaming_links:
                    m3u8s = set(re.findall(r'(https://[^"\'\s]+\.m3u8[^"\'\s\\]*)', unescaped_html, re.IGNORECASE))
                    for idx, link in enumerate(m3u8s):
                        streaming_links.append({
                            "label": f"Server {idx+1}",
                            "source": link
                        })
                        
                movie_id = movie_url.split('/')[-1]
                
                # Default values for fields
                imdb_rating = "0"
                genre = ["Unknown"]
                language = "Unknown"
                release_date = "Unknown"
                storyline = "No storyline available."
                stream_url = streaming_links[0]["source"] if streaming_links else ""
                
                # Parse imdbRating
                rating_match = re.search(r'"imdbRating"\s*:\s*([0-9.]+)', unescaped_html)
                if rating_match:
                    imdb_rating = rating_match.group(1)

                # Parse genres
                genre_match = re.search(r'"genre"\s*:\s*\[(.*?)\]', unescaped_html)
                if genre_match:
                    parsed_genres = re.findall(r'"(.*?)"', genre_match.group(1))
                    if parsed_genres:
                        genre = parsed_genres

                # Parse language
                lang_match = re.search(r'"language"\s*:\s*"([^"]+)"', unescaped_html)
                if lang_match:
                    language = lang_match.group(1).title()

                # Parse release date (converting ISO format to DD-MM-YYYY)
                rd_match = re.search(r'"fullReleaseDate"\s*:\s*"([^"]+)"', unescaped_html)
                if rd_match:
                    parts = rd_match.group(1).split('T')[0].split('-') 
                    if len(parts) == 3:
                        release_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                
                # Fallback to year if full date is missing
                if release_date == "Unknown":
                    ry_match = re.search(r'"releaseYear"\s*:\s*([0-9]{4})', unescaped_html)
                    if ry_match:
                        release_date = ry_match.group(1)

                # Parse storyline
                desc_match = re.search(r'<meta name="description"\s+content="([^"]+)"', html, re.IGNORECASE)
                if desc_match:
                    storyline = desc_match.group(1).strip()
                
                # Format category name nicely (e.g. "bollywood_all_movies" -> "Bollywood All Movies")
                cat_name = file_name.replace("_", " ").title()
                        
                # Create the final object exactly matching the requested schema
                final_obj = {
                    "id": movie_id,
                    "category": cat_name,
                    "director": "Unknown",
                    "genre": genre,
                    "imdbRating": str(imdb_rating),
                    "imdbVotes": 0,
                    "language": language,
                    "posterUrl": thumbnail,
                    "releaseDate": release_date,
                    "sliderUrl": thumbnail,
                    "status": "on",
                    "storyline": storyline,
                    "streamUrl": stream_url,
                    "title": title,
                    "headers": {
                        "referer": "https://www.moviesbazar.tv/",
                        "origin": "https://www.moviesbazar.tv",
                        "user_agent": HEADERS["User-Agent"]
                    }
                }
                
                category_extracted_data.append(final_obj)
                log(f"Scraped [{j+1}/{len(movie_links_list)}]: {title} ({len(streaming_links)} streams)", COLOR_INFO)
                
            except Exception as e:
                log(f"Network error skipping {movie_url}: {e}", COLOR_ERROR)

            # Anti-ban sleep per movie (CRITICAL)
            time.sleep(1.5)

        log(f"\nPhase 3: Saving {len(category_extracted_data)} records to JSON...", COLOR_INFO)
        filename = f"{file_name}.json"
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(category_extracted_data, f, indent=4, ensure_ascii=False)
            log(f"💾 SUCCESS: File created -> {filename}", COLOR_SUCCESS)
        except Exception as e:
            log(f"💾 ERROR saving file: {e}", COLOR_ERROR)

        log("Waiting 3 seconds before moving to next category...", COLOR_WARNING)
        time.sleep(3)

    log("\n🎉 BOOM! ALL CATEGORIES SCRAPED SUCCESSFULLY!", COLOR_TITLE)

if __name__ == "__main__":
    main()
