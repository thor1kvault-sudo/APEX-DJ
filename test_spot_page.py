import urllib.request
import re

url = "https://open.spotify.com/track/4kV0ugCwyF70Ab3huIdThG"
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
req = urllib.request.Request(url, headers=headers)
try:
    html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
    print("Page Title Tag:", re.findall(r'<title>(.*?)</title>', html))
    print("OG Title:", re.findall(r'<meta property="og:title" content="(.*?)"', html))
    print("OG Description:", re.findall(r'<meta property="og:description" content="(.*?)"', html))
    print("OG Image:", re.findall(r'<meta property="og:image" content="(.*?)"', html))
except Exception as e:
    print("Failed:", e)
