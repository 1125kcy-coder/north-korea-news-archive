import os
import json
import re
import requests
import gspread
from bs4 import BeautifulSoup
from datetime import datetime
from openai import OpenAI
from google.oauth2.service_account import Credentials

SHEET_ID = os.environ["SHEET_ID"]
SHEET_NAME = "신문기사"

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

CATEGORIES = [
    "가상화폐", "기타", "남북관계", "대북제재", "북러관계", "북러무역",
    "북미관계", "북중관계", "북중러협력", "북중무역", "북중협력",
    "북한경제", "북한관광", "북한산업", "북한외교", "산업건설",
    "산업기술", "산업생산", "인도적지원"
]

def connect_sheet():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(credentials)
    return gc.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

def get_existing_urls(ws):
    values = ws.col_values(5)
    return set(v.strip() for v in values if v.startswith("http"))

def fetch_yna_links():
    url = "https://www.yna.co.kr/nk/news/all"
    html = requests.get(url, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(" ", strip=True)

        if "/view/AKR" not in href:
            continue

        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = "https://www.yna.co.kr" + href

        href = href.split("#")[0]

        if "section=nk/news/all" not in href:
            href += "?section=nk/news/all" if "?" not in href else "&section=nk/news/all"

        if title and len(title) >= 8:
            links.append({"title": title, "url": href, "source": "연합뉴스"})

    unique = []
    seen = set()
    for item in links:
        if item["url"] not in seen:
            unique.append(item)
            seen.add(item["url"])

    return unique[:20]

def fetch_voa_links():
    url = "https://www.voakorea.com/z/2712"
    html = requests.get(url, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(" ", strip=True)

        if not title or len(title) < 8:
            continue

        if href.startswith("/"):
            href = "https://www.voakorea.com" + href

        if "voakorea.com/a/" not in href:
            continue

        href = href.split("#")[0]

        links.append({
            "title": title,
            "url": href,
            "source": "VOA"
        })

    unique = []
    seen = set()

    for item in links:
        if item["url"] not in seen:
            unique.append(item)
            seen.add(item["url"])

    return unique[:20]

def fetch_spn_links():
    url = "https://www.spnews.co.kr/news/articleList.html?sc_section_code=S1N1&view_type=sm"
    html = requests.get(url, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(" ", strip=True)

        if not title or len(title) < 8:
            continue

        if href.startswith("/"):
            href = "https://www.spnews.co.kr" + href

        if "/news/articleView.html" not in href:
            continue

        href = href.split("#")[0]

        links.append({
            "title": title,
            "url": href,
            "source": "SPN"
        })

    unique = []
    seen = set()

    for item in links:
        if item["url"] not in seen:
            unique.append(item)
            seen.add(item["url"])

    return unique[:20]
    
def classify_article(title, source):
    prompt = f"""
다음 북한 관련 기사를 분류하라.

기사 제목: {title}
출처: {source}

카테고리는 아래 목록 중 하나만 선택하라.
{", ".join(CATEGORIES)}

반드시 JSON만 출력하라.
예:
{{"category":"북중관계"}}
"""

    response = client.responses.create(
        model="gpt-5.4-mini",
        input=prompt,
        text={"format": {"type": "json_object"}},
        max_output_tokens=100,
    )

    data = json.loads(response.output_text)
    category = data.get("category", "기타")

    if category not in CATEGORIES:
        category = "기타"

    return category

def main():
    ws = connect_sheet()
    existing_urls = get_existing_urls(ws)

    articles = fetch_yna_links() + fetch_voa_links() + fetch_spn_links()
    today = datetime.now().strftime("%Y-%m-%d")

    added = 0

    for article in articles:
        if article["url"] in existing_urls:
            continue

        category = classify_article(article["title"], article["source"])

        ws.append_row(
            [
                today,
                article["title"],
                article["source"],
                category,
                article["url"],
            ],
            value_input_option="RAW",
        )

        added += 1
        print(f"Added: {article['title']} / {category}")

    print(f"완료: 신규 기사 {added}건 추가")

if __name__ == "__main__":
    main()

