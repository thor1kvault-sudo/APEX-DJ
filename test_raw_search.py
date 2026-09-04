import urllib.request
import urllib.parse
import re
import json
import yt_dlp

def search_youtube_raw(query):
    """Fallback search using YouTube html scraping when yt-dlp flat search returns 0 results."""
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.youtube.com/results?search_query={encoded_query}"
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
        )
        html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
        video_ids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', html)
        if video_ids:
            # Return unique video IDs
            seen = set()
            unique_ids = []
            for vid in video_ids:
                if vid not in seen:
                    seen.add(vid)
                    unique_ids.append(vid)
            return [f"https://www.youtube.com/watch?v={vid}" for vid in unique_ids[:3]]
    except Exception as e:
        print("Raw search failed:", e)
    return []

print("Searching 'KALYANI Shreya Ghoshal':")
urls = search_youtube_raw("KALYANI Shreya Ghoshal")
print("Found YouTube URLs:", urls)
