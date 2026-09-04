import yt_dlp
from config import YTDL_FORMAT_OPTIONS

ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)

def test_extract(query):
    print(f"Testing query: {query}")
    try:
        data = ytdl.extract_info(query, download=False)
        if 'entries' in data:
            data = data['entries'][0]
        stream_url = data.get('url')
        title = data.get('title')
        print(f"Success! Title: {title}")
        print(f"Stream URL: {stream_url[:80]}...")
        return stream_url
    except Exception as e:
        print(f"Extract error: {e}")
        return None

if __name__ == "__main__":
    test_extract("ytsearch1:Mitta Ror Sheesha song")
