import requests
from bs4 import BeautifulSoup

URL = "https://www.yna.co.kr/nk/news/all"

response = requests.get(URL)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

print("연합뉴스 북한포털 접속 성공")

for link in soup.find_all("a", href=True)[:20]:
    print(link["href"])
