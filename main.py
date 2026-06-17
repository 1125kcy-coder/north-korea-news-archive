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

KEYWORD_RULES = {
    "가상화폐": ["해킹", "암호화폐", "가상화폐", "가상자산", "코인", "라자루스","탈취", "암호화 자산", "블록체인"],
    "대북제재": ["제재", "유엔", "안보리", "제재위", "불법","불법 환적", "위반", "동결", "규탄", "대북","독자제재", "감시", "선박", "석탄 밀수"],
    "북러무역": ["북러 무역", "북러 교역", "러시아와 무역", "러시아", "수출", "수입", "무역", "두만강", "나진", "하산", "러시아 수출", "러시아 수입"],
    "북중무역": ["북중 무역", "북중 교역", "단둥", "중국", "수출", "수입", "교역","중국과 무역","신의주", "북중 접경", "대중 수출", "대중 수입", "교역액"],
    "북미관계": ["미국", "트럼프", "워싱턴", "북미", "백악관", "국무부","미 의회", "미 전문가", "대북정책", "비핵화", "핵협상"],
    "북중관계": ["중국", "시진핑", "북중", "중국 외교부","왕이", "리창", "주북 중국대사", "중국대사관"],
    "북러관계": ["러시아", "푸틴", "북러", "라브로프", "쇼이구", "러시아 대표단", "모스크바", "파병", "우크라이나"],
    "남북관계": ["한국", "남북", "통일부", "이재명", "서울", "개성공단","대북전단","확성기","개성공단","금강산", "군사분계선", "DMZ"],
    "북한관광": ["관광", "관광객", "여행", "원산", "갈마", "마식령", "외국인 관광", "관광지", "호텔"],
    "산업건설": ["건설", "착공", "준공", "완공", "공사", "개건", "살림집", "농촌주택", "지방발전", "현대화 공사", "복구"],
    "산업생산": ["공장", "생산", "기업소", "증산", "생산량", "제철", "기계", "화학공업", "전력", "석탄", "광산", "제련"],
    "산업기술": ["기술", "AI", "인공지능", "연구소", "자동화", "소프트웨어", "정보기술", "과학기술", "기술개발", "태블릿"],
    "인도적지원": ["지원", "식량", "보건", "아동", "유니세프", "WFP", "식량지원", "WHO", "구호", "영양", "의약품", "백신", "재해"],
    "북한경제": ["물가", "환율", "장마당", "식량", "경제", "농민", "배급", "시장", "쌀값", "옥수수", "농장", "모내기", "수확", "임금", "돈주", "생활고", "주민", "돼지고기", "휘발유"],
    "북한외교": ["외교", "대사", "회담", "방문", "외무성","축전", "대표단", "친선", "수교", "대외관계", "국제회의"],
    "북중러협력":["북중러","중러","3국","삼각 협력","북·중·러"],
    
}

def rule_based_category(title):
    for category, keywords in KEYWORD_RULES.items():
        for keyword in keywords:
            if keyword in title:
                return category
    return None

def extract_article_date(url, source):
    if source == "연합뉴스":
        match = re.search(r"AKR(\d{8})", url)
        if match:
            d = match.group(1)
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    if source == "데일리NK":
        match = re.search(r"dailynk\.com/(\d{8})", url)
        if match:
            d = match.group(1)
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    if source == "RFA":
        match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    return datetime.now().strftime("%Y-%m-%d")

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

    return dedupe_links(links)[:20]

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

    return dedupe_links(links)[:20]

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

    return dedupe_links(links)[:20]

def fetch_rfa_links():
    url = "https://www.rfa.org/korean/"
    headers = {"User-Agent": "Mozilla/5.0"}

    html = requests.get(url, headers=headers, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(" ", strip=True)

        if not title or len(title) < 8:
            continue

        if href.startswith("/"):
            href = "https://www.rfa.org" + href

        if "rfa.org/korean" not in href:
            continue

        if any(x in href for x in [
            "/multimedia/",
            "/podcast/",
            "/about/",
            "#",
            "javascript"
        ]):
            continue

        if not re.search(r"/korean/.*/\d{4}/\d{2}/\d{2}/", href):
            continue

        href = href.split("#")[0]

        links.append({
            "title": title,
            "url": href,
            "source": "RFA"
        })

    links = dedupe_links(links)
    print(f"RFA collected: {len(links)}")

    return links[:20]

def fetch_dailynk_links():
    url = "https://www.dailynk.com/all/"
    headers = {"User-Agent": "Mozilla/5.0"}

    html = requests.get(url, headers=headers, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(" ", strip=True)

        if not title or len(title) < 8:
            continue

        if href.startswith("/"):
            href = "https://www.dailynk.com" + href

        if "dailynk.com" not in href:
            continue

        if any(x in href for x in [
            "/category/",
            "/tag/",
            "/author/",
            "/page/",
            "/wp-content/",
            "javascript",
            "#"
        ]):
            continue

        if not re.search(r"dailynk\.com/\d{8}(-\d+)?/?$", href):
            continue

        href = href.split("#")[0]

        links.append({
            "title": title,
            "url": href,
            "source": "데일리NK"
        })

    links = dedupe_links(links)
    print(f"Daily NK collected: {len(links)}")

    return links[:20]

def dedupe_links(links):
    unique = []
    seen = set()

    for item in links:
        if item["url"] not in seen:
            unique.append(item)
            seen.add(item["url"])

    return unique

def classify_article(title, source):
    rule_category = rule_based_category(title)
    if rule_category:
        return rule_category

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

    articles = (
        fetch_yna_links()
        + fetch_voa_links()
        + fetch_spn_links()
        + fetch_rfa_links()
        + fetch_dailynk_links()
    )

    added = 0

    for article in articles:
        if article["url"] in existing_urls:
            continue

        category = classify_article(article["title"], article["source"])
        article_date = extract_article_date(
            article["url"],
            article["source"]
)

        
        ws.append_row(
            [
                article_date,
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
