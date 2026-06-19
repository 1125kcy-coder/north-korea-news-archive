import os
import json
import re
import requests
import gspread
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from openai import OpenAI
from google.oauth2.service_account import Credentials

SHEET_ID = os.environ["SHEET_ID"]
SHEET_NAME = "신문기사"
WEEKLY_SHEET_NAME = "주간동향"

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

EXCLUDE_KEYWORDS = [
    "이슈브리프",
    "전문가 분석",
    "전문가",
    "칼럼",
    "사설",
    "기고",
    "연재",
    "역사 속으로",
    "걷다가 역사 속으로",
    "서평",
    "논평",
    "오피니언",
    "인터뷰",
    "해설",
]

def is_excluded_article(title):
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in title:
            return True
    return False
        
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
            
def get_target_date():
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if source == "데일리NK":
        match = re.search(r"dailynk\.com/(\d{8})", url)
        if match:
            d = match.group(1)
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    if source == "RFA":
        match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        html = requests.get(url, headers=headers, timeout=20).text
        soup = BeautifulSoup(html, "html.parser")

        meta_date = soup.find("meta", property="article:published_time")
        if meta_date and meta_date.get("content"):
            return meta_date["content"][:10]

        time_tag = soup.find("time")
        if time_tag:
            if time_tag.get("datetime"):
                return time_tag["datetime"][:10]

            text = time_tag.get_text(" ", strip=True)
            match = re.search(r"(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})", text)
            if match:
                return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

        text = soup.get_text(" ", strip=True)
        match = re.search(r"(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})", text)
        if match:
            return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    except Exception as e:
        print(f"Date extraction failed: {source} / {url} / {e}")

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

def connect_weekly_sheet():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(credentials)
    return gc.open_by_key(SHEET_ID).worksheet(WEEKLY_SHEET_NAME)

def get_existing_urls(ws):
    values = ws.col_values(5)
    return set(v.strip() for v in values if v.startswith("http"))

def get_recent_articles(ws, days=7):
    rows = ws.get_all_values()

    if len(rows) <= 1:
        return []

    data = rows[1:]
    today = datetime.now().date()
    recent_articles = []

    for row in data:
        if len(row) < 5:
            continue

        date_text = row[0].strip()
        title = row[1].strip()
        source = row[2].strip()
        category = row[3].strip()
        url = row[4].strip()

        try:
            article_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue

        diff = (today - article_date).days

        if 0 <= diff <= days:
            recent_articles.append({
                "date": date_text,
                "title": title,
                "source": source,
                "category": category,
                "url": url,
            })

    return recent_articles

def sort_news_sheet(ws):
    rows = ws.get_all_values()

    if len(rows) <= 1:
        return

    header = rows[0]
    data = rows[1:]

    data.sort(
        key=lambda x: datetime.strptime(x[0], "%Y-%m-%d")
        if len(x) > 0 and x[0]
        else datetime.min
    )

    ws.clear()

    ws.append_row(header)

    if data:
        ws.append_rows(data)

    print("신문기사 시트 날짜 오름차순 정렬 완료")

def generate_weekly_summary(articles):
    if not articles:
        return "최근 7일간 수집된 기사가 없습니다."

    grouped = {}

    for article in articles:
        category = article["category"]
        grouped.setdefault(category, [])
        grouped[category].append(article)

    article_text = ""

    for category, items in grouped.items():
        article_text += f"\n[{category}]\n"
        for item in items:
            article_text += f"- {item['date']} / {item['source']} / {item['title']} / {item['url']}\n"

    prompt = f"""
다음은 최근 7일간 수집된 북한 관련 언론 기사 목록이다.

{article_text}

위 기사 제목, 출처, 분류를 바탕으로 최근 1주일간의 주요 북한 동향을 작성하라.

작성 방식:
- 카테고리명을 소제목으로 쓰지 말 것.
- 한 주간 반복적으로 나타난 핵심 이슈를 3~5개 선정하고, 그 이슈를 소제목으로 삼을 것.
- 소제목은 구체적인 사건·흐름 중심으로 작성할 것.
  예:
  - 북러 협력 확대와 파병 관련 보도 지속
  - 북한 내부 식량·물가 불안 부각
  - 시진핑 방북 가능성과 북중관계 변화

- 각 소제목 아래에는 4~6문장으로 동향을 설명할 것.
- 기사 제목에 근거해 작성하고, 확인되지 않은 사실은 단정하지 말 것.
- 여러 기사에서 공통적으로 드러나는 흐름을 정리할 것.
- 단순 기사 나열 금지.
- 마지막에는 "종합 평가" 항목을 두고 이번 주 보도의 전체적 특징을 정리할 것.
- KIEP 또는 통일부 주간동향 보고서 문체를 사용할 것.
- 전체 분량은 1000~1500자 내외로 할 것.
"""
    
    response = client.responses.create(
        model="gpt-5.4-mini",
        input=prompt,
        max_output_tokens=1500,
    )

    return response.output_text

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
    print("MAIN STARTED")

    ws = connect_sheet()
    existing_urls = get_existing_urls(ws)

    articles = (
        fetch_yna_links()
        + fetch_voa_links()
        + fetch_spn_links()
        + fetch_rfa_links()
        + fetch_dailynk_links()
    )

    print(f"총 수집 후보 기사 수: {len(articles)}")

    target_date = get_target_date()

    filtered_articles = []

    for article in articles:
        article_date = extract_article_date(
            article["url"],
            article["source"]
        )

        if article_date == target_date:
            article["date"] = article_date
            filtered_articles.append(article)

    articles = filtered_articles

    print(f"수집 대상 날짜: {target_date}")
    print(f"어제 작성 기사 수: {len(articles)}")

    added = 0

for article in articles:
    if is_excluded_article(article["title"]):
        print(f"제외 기사: {article['title']}")
        continue

    if article["url"] in existing_urls:
        continue

        category = classify_article(article["title"], article["source"])
        article_date = article["date"]
       
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
    # sort_news_sheet(ws)
    print("WEEKLY SUMMARY STARTED")

    weekly_ws = connect_weekly_sheet()
    recent_articles = get_recent_articles(ws, days=7)
    weekly_summary = generate_weekly_summary(recent_articles)

    today_text = datetime.now().strftime("%Y-%m-%d")
    period_text = f"최근 7일 기준 ~ {today_text}"

    weekly_rows = weekly_ws.get_all_values()
    updated = False

    for idx, row in enumerate(weekly_rows[1:], start=2):
        if len(row) >= 1 and row[0] == today_text:
            weekly_ws.update(
                f"A{idx}:C{idx}",
                [[today_text, period_text, weekly_summary]],
                value_input_option="RAW",
            )
            updated = True
            break

    if not updated:
        weekly_ws.append_row(
            [
                today_text,
                period_text,
                weekly_summary,
            ],
            value_input_option="RAW",
        )

    print("주간동향 요약 저장 완료")


if __name__ == "__main__":
    main()
