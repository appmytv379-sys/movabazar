import requests
import json
import re
import time
import os

# ==========================================
# ADD AS MANY CATEGORY LINKS HERE AS YOU WANT
# ==========================================
TARGET_CATEGORIES = [
    {"url": "https://www.moviesbazar.tv/browse/recently-added", "name": "recently_added_movies"},
    {"url": "https://www.moviesbazar.tv/browse/latest/hollywood", "name": "hollywood_latest_movies"},
    {"url": "https://www.moviesbazar.tv/browse/category/bengali", "name": "bengali_all_movies"}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "application/json",
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
    """Extracts exact API path like 'recently-added' or 'latest/hollywood'"""
    if '/browse/' in url:
        return url.split('/browse/')[1].strip('/')
    return url.replace('https://www.moviesbazar.tv/', '').strip('/')

def find_movies_aggressively(data, movies_list=None):
    """Recursively deeply searches JSON and extracts absolutely EVERY movie object."""
    if movies_list is None:
        movies_list = []
        
    if isinstance(data, dict):
        # If the dict looks like a movie object (has id/imdbId and title/type)
        if ('imdbId' in data or '_id' in data) and ('title' in data or 'type' in data):
            movies_list.append(data)
        # Continue searching inside children
        for key, value in data.items():
            find_movies_aggressively(value, movies_list)
    elif isinstance(data, list):
        for item in data:
            find_movies_aggressively(item, movies_list)
            
    return movies_list

def main():
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
            
            # Extract links from Base HTML
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
            
            # The EXACT Payload Structure discovered from the Network Tab
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
                # Aggressively fetch all movie objects from deeply nested JSON
                movies_array = find_movies_aggressively(data)
                
                if not movies_array:
                    log(f"⚠️ API returned empty data. Reached true end at page {current_page}.", COLOR_WARNING)
                    break
                    
                added = 0
                for movie in movies_array:
                    imdb_id = movie.get('imdbId', '')
                    m_id = str(imdb_id).replace('tt', '')
                    
                    if not m_id:
                        m_id = str(movie.get('_id', movie.get('id', '')))
                        
                    title = movie.get('title', 'movie')
                    title_slug = re.sub(r'[^a-z0-9]+', '-', title.lower().strip()).strip('-')
                    m_type = movie.get('type', 'movie')
                    
                    if m_id and title_slug:
                        link = f"https://www.moviesbazar.tv/watch/{m_type}/{title_slug}/{m_id}"
                        if link not in unique_movie_links:
                            unique_movie_links.add(link)
                            added += 1
                
                log(f"✅ API Page {current_page} fetched. Found {added} new links. Total: {len(unique_movie_links)}", COLOR_SUCCESS)
                
                # If no new links were added, the API might be repeating data, break to avoid infinite loop
                if added == 0:
                    log(f"⚠️ No new links found on page {current_page}. Stopping pagination.", COLOR_WARNING)
                    break
                
                current_page += 1
                fails = 0
                
            except Exception as e:
                log(f"❌ Failed API page {current_page}. Error: {e}", COLOR_ERROR)
                fails += 1
                if fails >= 3:
                    log("Too many failures. Moving to Extraction Phase.", COLOR_ERROR)
                    break
            
            # Anti-ban sleep
            time.sleep(1.5)

        movie_links_list = list(unique_movie_links)
        log(f"\n✅ Phase 1 Complete. Final URL count for {file_name}: {len(movie_links_list)}", COLOR_TITLE)

        if not movie_links_list:
            log("Skipping extraction, no links found.", COLOR_WARNING)
            continue

        log(f"\nPhase 2: Extracting deep details and strict M3U8 streams for {len(movie_links_list)} movies...", COLOR_INFO)
        
        for j, movie_url in enumerate(movie_links_list):
            try:
                detail_res = session.get(movie_url, timeout=30)
                html = detail_res.text
                unescaped_html = html.replace('\\"', '"').replace('\\/', '/')
                
                # =====================================
                # 1. STRICT M3U8 LINK EXTRACTION
                # =====================================
                stream_url = ""
                
                # Try finding valid .m3u8 links from JSON watchLink payload first
                wl_match = re.search(r'"watchLink"\s*:\s*(\[\{.*?\}\])', unescaped_html, re.DOTALL)
                if wl_match:
                    try:
                        watch_links = json.loads(wl_match.group(1))
                        for wl in watch_links:
                            source = wl.get('source', '')
                            # ONLY accept it if it contains .m3u8 (ignores iframe links like mbstream.p2pplay)
                            if '.m3u8' in source.lower():
                                stream_url = source
                                break
                    except json.JSONDecodeError:
                        pass
                
                # Regex Fallback: Aggressively scour the entire HTML for raw .m3u8 URLs
                if not stream_url:
                    m3u8_matches = re.findall(r'(https?://[^"\'\s<>]+?\.m3u8[^"\'\s<>\\]*)', unescaped_html, re.IGNORECASE)
                    if m3u8_matches:
                        stream_url = m3u8_matches[0]
                
                # If STILL no valid .m3u8 link is found, SKIP THIS MOVIE entirely
                if not stream_url or ".m3u8" not in stream_url.lower():
                    log(f"⚠️ Skipped [{j+1}/{len(movie_links_list)}]: No valid .m3u8 found.", COLOR_WARNING)
                    time.sleep(1.0)
                    continue
                
                # =====================================
                # 2. METADATA EXTRACTION
                # =====================================
                
                # Title Extract and clean
                title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                raw_title = "Unknown Title"
                if title_match:
                    raw_title = title_match.group(1).replace('Watch ', '').replace(' Movie Online Free! | Movies Bazar', '').replace(' Series Online Free! | Movies Bazar', '').strip()
                    # Remove existing year from title if present (e.g., "Haiwaan (2026)")
                    raw_title = re.sub(r'\s*\(\d{4}\)\s*', '', raw_title)

                # Thumbnail
                thumb_match = re.search(r'property="og:image"\s+content="([^"]+)"', html, re.IGNORECASE)
                thumbnail = thumb_match.group(1) if thumb_match else ""
                
                # Movie ID
                movie_id = movie_url.split('/')[-1]
                
                # Release Date & Year
                release_date = "Unknown"
                rd_match = re.search(r'"fullReleaseDate"\s*:\s*"([^"]+)"', unescaped_html)
                if rd_match:
                    parts = rd_match.group(1).split('T')[0].split('-') 
                    if len(parts) == 3:
                        release_date = f"{parts[2]}-{parts[1]}-{parts[0]}" # DD-MM-YYYY
                if release_date == "Unknown":
                    ry_match = re.search(r'"releaseYear"\s*:\s*([0-9]{4})', unescaped_html)
                    if ry_match:
                        release_date = ry_match.group(1)
                
                # Extract 4-digit Year for Title
                year = "Unknown"
                y_match = re.search(r'\b((?:19|20)\d{2})\b', release_date)
                if y_match:
                    year = y_match.group(1)
                
                # Final Title format: "Movie Name (Year)"
                final_title = f"{raw_title} ({year})"
                
                # IMDB Rating
                imdb_rating = "0"
                rating_match = re.search(r'"imdbRating"\s*:\s*([0-9.]+)', unescaped_html)
                if rating_match:
                    imdb_rating = rating_match.group(1)

                # Genre Array
                genre = ["Unknown"]
                genre_match = re.search(r'"genre"\s*:\s*\[(.*?)\]', unescaped_html)
                if genre_match:
                    parsed_genres = re.findall(r'"(.*?)"', genre_match.group(1))
                    if parsed_genres:
                        genre = parsed_genres

                # Language
                language = "Unknown"
                lang_match = re.search(r'"language"\s*:\s*"([^"]+)"', unescaped_html)
                if lang_match:
                    language = lang_match.group(1).title()
                
                # Storyline
                storyline = "No storyline available."
                desc_match = re.search(r'<meta name="description"\s+content="([^"]+)"', html, re.IGNORECASE)
                if desc_match:
                    storyline = desc_match.group(1).strip()
                
                # Category Name
                cat_name = file_name.replace("_", " ").title()
                
                # =====================================
                # 3. BUILD FINAL OBJECT
                # =====================================
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
                    "title": final_title,
                    "headers": {
                        "referer": "https://www.moviesbazar.tv//",
                        "origin": "",
                        "user_agent": ""
                    }
                }
                
                category_extracted_data.append(final_obj)
                log(f"✅ Scraped [{j+1}/{len(movie_links_list)}]: {final_title}", COLOR_SUCCESS)
                
            except Exception as e:
                log(f"❌ Network error skipping {movie_url}: {e}", COLOR_ERROR)

            # Anti-ban sleep per movie (CRITICAL to avoid block)
            time.sleep(1.0)

        log(f"\nPhase 3: Saving {len(category_extracted_data)} valid records to JSON...", COLOR_INFO)
        filename = f"{file_name}.json"
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(category_extracted_data, f, indent=4, ensure_ascii=False)
            log(f"💾 SUCCESS: File created -> {filename} (Skipped movies without m3u8)", COLOR_SUCCESS)
        except Exception as e:
            log(f"💾 ERROR saving file: {e}", COLOR_ERROR)

        log("Waiting 3 seconds before moving to next category...", COLOR_WARNING)
        time.sleep(3)

    log("\n🎉 BOOM! ALL CATEGORIES SCRAPED SUCCESSFULLY!", COLOR_TITLE)

if __name__ == "__main__":
    main()
