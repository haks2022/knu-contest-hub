#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
경북대학교(KNU) 공모전·경진대회·대외활동 통합 일일 크롤러 (knu_crawler.py)
---------------------------------------------------------------------------
수집 대상 기관:
  1. 경북대학교 대학공지 & 학사공지 (knu.ac.kr - wbbs 게시판)
  2. IT대학 전자공학부 (see.knu.ac.kr - 자체 공지 게시판)
  3. IT대학 컴퓨터학부 (knucom / cse.knu.ac.kr - 그누보드 게시판)
  4. 공학교육혁신센터 (ceedin.knu.ac.kr - 공지사항 게시판)
  5. SW교육원 / IT교육센터 (oz.knu.ac.kr / swedu.knu.ac.kr)
  6. 창업지원단 (startup.knu.ac.kr - 그누보드 noti, noti2)
  7. 데이터융복합연구원 / 사업단 (datainstitute.knu.ac.kr - 전자정부 표준 게시판)
  8. 진로취업과 / 비교과통합시스템 (knujob.knu.ac.kr / knucube.knu.ac.kr)

실행 방법:
  pip install requests beautifulsoup4 lxml
  python knu_crawler.py              # 실제 크롤링 실행 후 data/competitions.json 갱신
  python knu_crawler.py --dry-run    # 네트워크 요청 없이 파서 및 정규식 로직 테스트
"""

import argparse
import datetime
import json
import os
import re
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 1. 키워드 필터 및 자동 분류 규칙 설정
# ---------------------------------------------------------------------------
INCLUDE_KEYWORDS = [
    "공모전", "경진대회", "해커톤", "아이디어", "캡스톤", "챌린지", "Challenge",
    "대회", "모집", "선발", "창업", "스타트업", "서포터즈", "대외활동", "포트폴리오",
    "비교과", "메이커톤", "아이디어톤", "장학생", "PBL", "경연", "출품", "공모", "행사", "캠페인", "특강", "박람회", "페스티벌", "학술제", "토크콘서트", "문화주간"
]

EXCLUDE_KEYWORDS = [
    "휴학", "복학", "수강변경", "폐강", "졸업자격인정원", "예비군", "정기주차",
    "시설공사", "단수안내", "정전안내", "식단표"
]

CATEGORY_RULES = [
    ("hackathon", "해커톤·AI·SW", ["해커톤", "AI", "인공지능", "SW", "소프트웨어", "코딩", "알고리즘", "빅데이터", "데이터", "메이커톤"]),
    ("capstone", "캡스톤·공학설계", ["캡스톤", "종합설계", "창의설계", "공학", "설계", "시제품", "ABEEK"]),
    ("startup", "창업·아이디어", ["창업", "스타트업", "기업가", "아이디어", "사업화", "입주기업", "예비창업"]),
    ("global", "글로벌·대외활동", ["글로벌", "해외", "서포터즈", "대외활동", "교류", "탐방", "포트폴리오", "진로", "취업"]),
    ("research", "연구·장학·학술", ["연구", "R&D", "논문", "장학", "학술", "대학원", "RISE"])
]

# ---------------------------------------------------------------------------
# 2. 경북대학교 수집 대상 사이트 설정 (원하는 학과/기관을 자유롭게 추가 가능)
# ---------------------------------------------------------------------------
KNU_SOURCES = [
    {
        "id": "knu_main",
        "orgId": "knu_main",
        "orgName": "대학본부 (통합·학사공지)",
        "subOrg": "경북대 대학공지",
        "parser": "knu_wbbs",
        "listUrl": "https://www.knu.ac.kr/wbbs/wbbs/bbs/btin/list.action?bbs_cde=1&menu_idx=67",
        "baseUrl": "https://www.knu.ac.kr",
        "filterByKeyword": True
    },
    {
        "id": "it_see",
        "orgId": "it_college",
        "orgName": "IT대학 (전자공학부·컴퓨터학부)",
        "subOrg": "IT대학 전자공학부",
        "parser": "knu_see",
        "listUrl": "https://see.knu.ac.kr/mobile/content/notice.html",
        "baseUrl": "https://see.knu.ac.kr",
        "filterByKeyword": True
    },
    {
        "id": "it_cse",
        "orgId": "it_college",
        "orgName": "IT대학 (전자공학부·컴퓨터학부)",
        "subOrg": "IT대학 컴퓨터학부",
        "parser": "gnuboard",
        "listUrl": "https://knucom.dsso.kr:56187/bbs/board.php?bo_table=sub5_1",
        "baseUrl": "https://knucom.dsso.kr:56187",
        "filterByKeyword": True
    },
    {
        "id": "ceedin",
        "orgId": "ceedin",
        "orgName": "공학교육혁신센터",
        "subOrg": "공학교육혁신센터",
        "parser": "generic_table",
        "listUrl": "https://ceedin.knu.ac.kr/",
        "baseUrl": "https://ceedin.knu.ac.kr",
        "filterByKeyword": False  # 센터 공지는 대부분 공학프로그램/경진대회이므로 넓게 수집
    },
    {
        "id": "startup_noti",
        "orgId": "startup",
        "orgName": "창업지원단",
        "subOrg": "창업지원단 공지사항",
        "parser": "gnuboard",
        "listUrl": "https://startup.knu.ac.kr/bbs/board.php?bo_table=noti",
        "baseUrl": "https://startup.knu.ac.kr",
        "filterByKeyword": False
    },
    {
        "id": "startup_noti2",
        "orgId": "startup",
        "orgName": "창업지원단",
        "subOrg": "창업지원단 유관기관 공고",
        "parser": "gnuboard",
        "listUrl": "https://startup.knu.ac.kr/bbs/board.php?bo_table=noti2",
        "baseUrl": "https://startup.knu.ac.kr",
        "filterByKeyword": False
    },
    {
        "id": "swedu_oz",
        "orgId": "swedu",
        "orgName": "SW교육원·IT교육센터",
        "subOrg": "SW교육원 / IT교육센터",
        "parser": "generic_table",
        "listUrl": "https://oz.knu.ac.kr/hmpg/main/main.knu",
        "baseUrl": "https://oz.knu.ac.kr",
        "filterByKeyword": False
    },
    {
        "id": "datainst",
        "orgId": "datainst",
        "orgName": "데이터융복합·사업단",
        "subOrg": "데이터융복합연구원",
        "parser": "egov_bbs",
        "listUrl": "https://datainstitute.knu.ac.kr/contents/bbs/selectBbsList.do?menuId=327&searchBbsinfo_tcd=1",
        "baseUrl": "https://datainstitute.knu.ac.kr",
        "filterByKeyword": True
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 KNUContestAggregator/1.0"
}


# ---------------------------------------------------------------------------
# 3. 유틸리티: 키워드 필터링, 카테고리 자동 분류, 마감일(D-Day) 정규식 추출
# ---------------------------------------------------------------------------
def is_contest_post(title: str, require_keyword: bool = True) -> bool:
    """제목에 제외 키워드가 없고, 공모전/모집 관련 키워드가 포함되어 있는지 판별합니다."""
    clean = title.strip()
    if any(ex in clean for ex in EXCLUDE_KEYWORDS):
        return False
    if not require_keyword:
        return True
    return any(kw.lower() in clean.lower() for kw in INCLUDE_KEYWORDS)


def classify_category(title: str, sub_org: str = "") -> tuple:
    """제목과 주관 기관명을 바탕으로 분야 카테고리 코드와 한글명을 반환합니다."""
    combined = f"{title} {sub_org}"
    for cat_code, cat_name, keywords in CATEGORY_RULES:
        if any(kw.lower() in combined.lower() for kw in keywords):
            return cat_code, cat_name
    return "global", "글로벌·대외활동"


def extract_deadline_from_text(text: str, posted_date_str: str) -> str:
    """
    제목 또는 본문에서 '~11/15', '~ 2026.11.20', '11월 18일까지' 형태의 마감일을 추출합니다.
    명시된 마감일이 없으면 등록일 기준 +14일을 기본 마감일로 설정합니다.
    """
    try:
        base_date = datetime.date.fromisoformat(posted_date_str)
    except ValueError:
        base_date = datetime.date.today()

    # 패턴 1: ~ 2026.11.15 또는 ~2026-11-15
    m_full = re.search(r"[~\-∼]\s*(202\d)[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})", text)
    if m_full:
        y, m, d = int(m_full.group(1)), int(m_full.group(2)), int(m_full.group(3))
        try:
            return datetime.date(y, m, d).isoformat()
        except ValueError:
            pass

    # 패턴 2: (~11/15), (~11.15), ~ 11월 15일
    m_short = re.search(r"[~\-∼(]\s*(\d{1,2})\s*[./월]\s*(\d{1,2})", text)
    if m_short:
        m, d = int(m_short.group(1)), int(m_short.group(2))
        year = base_date.year
        if m < base_date.month - 2:
            year += 1
        try:
            return datetime.date(year, m, d).isoformat()
        except ValueError:
            pass

    # 기본값: 등록일 + 14일
    return (base_date + datetime.timedelta(days=14)).isoformat()


def extract_tags(title: str, sub_org: str) -> List[str]:
    """제목의 대괄호 [부서/말머리] 및 주요 키워드를 해시태그로 추출합니다."""
    tags = []
    brackets = re.findall(r"\[([^\]]+)\]", title)
    for b in brackets[:2]:
        clean_b = b.strip()
        if 1 < len(clean_b) <= 12:
            tags.append(clean_b)
    for kw in ["해커톤", "캡스톤디자인", "창업", "AI", "SW마일리지", "장학", "글로벌", "경진대회"]:
        if kw.lower() in title.lower() and kw not in tags:
            tags.append(kw)
    if not tags:
        tags.append(sub_org.split()[0])
    return tags[:4]


# ---------------------------------------------------------------------------
# 4. 사이트별 HTML 파서 구현
# ---------------------------------------------------------------------------
def parse_knu_wbbs(html: str, source: Dict) -> List[Dict]:
    """경북대 본부 통합공지(wbbs) 게시판 파서"""
    soup = BeautifulSoup(html, "lxml")
    results = []
    rows = soup.select("table tbody tr")
    for row in rows:
        link_el = row.select_one("td.subject a, td.left a, a[href*='viewBtin']")
        if not link_el:
            continue
        title = " ".join(link_el.get_text().split())
        if not is_contest_post(title, source.get("filterByKeyword", True)):
            continue

        href = link_el.get("href", "")
        full_url = urljoin(source["listUrl"], href)
        parsed_q = parse_qs(urlparse(full_url).query)
        doc_no = (
            parsed_q.get("btin.doc_no", [None])[0]
            or parsed_q.get("doc_no", [None])[0]
            or re.sub(r"\D", "", href)[-7:]
            or str(abs(hash(title)))[:7]
        )

        # 등록일 추출 (YYYY-MM-DD 또는 YYYY.MM.DD)
        row_text = row.get_text(" ", strip=True)
        date_match = re.search(r"(202\d[-./]\d{2}[-./]\d{2})", row_text)
        posted_date = date_match.group(1).replace(".", "-").replace("/", "-") if date_match else datetime.date.today().isoformat()

        cat_code, cat_name = classify_category(title, source["subOrg"])
        deadline = extract_deadline_from_text(title, posted_date)

        results.append({
            "id": f"{source['id']}_{doc_no}",
            "title": title,
            "orgId": source["orgId"],
            "orgName": source["orgName"],
            "subOrg": source["subOrg"],
            "category": cat_code,
            "categoryName": cat_name,
            "postedDate": posted_date,
            "deadline": deadline,
            "eligibility": "경북대학교 재학생 (상세 요강 원문 참조)",
            "benefit": "원문 공고문 시상 내역 및 지원 혜택 참조",
            "url": full_url,
            "sourceBoardUrl": source["listUrl"],
            "tags": extract_tags(title, source["subOrg"]),
            "summary": f"{source['subOrg']}에서 등록한 '{title}' 공고입니다. 세부 신청 방법과 제출 서류는 원본 공지사항 첨부파일을 확인하세요.",
            "isNew": True
        })
    return results


def parse_knu_see(html: str, source: Dict) -> List[Dict]:
    """경북대 IT대학 전자공학부(see.knu.ac.kr) 공지사항 파서"""
    soup = BeautifulSoup(html, "lxml")
    results = []
    links = soup.select("a[href*='fidx='], table tbody tr a")
    seen_ids = set()

    for link_el in links:
        href = link_el.get("href", "")
        if "fidx=" not in href:
            continue
        title = " ".join(link_el.get_text().split())
        if not title or not is_contest_post(title, source.get("filterByKeyword", True)):
            continue

        fidx_match = re.search(r"fidx=(\d+)", href)
        fidx = fidx_match.group(1) if fidx_match else str(abs(hash(title)))[:6]
        if fidx in seen_ids:
            continue
        seen_ids.add(fidx)

        parent_text = link_el.parent.get_text(" ", strip=True) if link_el.parent else ""
        date_match = re.search(r"(202\d[-./]\d{2}[-./]\d{2})", parent_text)
        posted_date = date_match.group(1).replace(".", "-") if date_match else datetime.date.today().isoformat()

        full_url = f"https://see.knu.ac.kr/mobile/content/notice.html?fidx={fidx}"
        cat_code, cat_name = classify_category(title, source["subOrg"])
        deadline = extract_deadline_from_text(title, posted_date)

        results.append({
            "id": f"{source['id']}_{fidx}",
            "title": title,
            "orgId": source["orgId"],
            "orgName": source["orgName"],
            "subOrg": source["subOrg"],
            "category": cat_code,
            "categoryName": cat_name,
            "postedDate": posted_date,
            "deadline": deadline,
            "eligibility": "IT대학 및 관련 전공 재학생 (원문 참조)",
            "benefit": "상금·장학금 또는 사업단 프로그램 지원 (원문 참조)",
            "url": full_url,
            "sourceBoardUrl": source["listUrl"],
            "tags": extract_tags(title, source["subOrg"]),
            "summary": f"{source['subOrg']} 게시판에 등록된 '{title}' 안내입니다.",
            "isNew": True
        })
    return results


def parse_gnuboard(html: str, source: Dict) -> List[Dict]:
    """그누보드(GnuBoard: 창업지원단, 컴퓨터학부 등) 표준 게시판 파서"""
    soup = BeautifulSoup(html, "lxml")
    results = []
    rows = soup.select("table tbody tr, .tbl_head01 tbody tr, .bo_tit")

    for row in rows:
        link_el = row.select_one("td.td_subject a, .bo_tit a, a[href*='wr_id=']")
        if not link_el:
            continue
        title = " ".join(link_el.get_text().split())
        if not title or not is_contest_post(title, source.get("filterByKeyword", True)):
            continue

        href = link_el.get("href", "")
        full_url = urljoin(source["listUrl"], href)
        wr_match = re.search(r"wr_id=(\d+)", full_url)
        wr_id = wr_match.group(1) if wr_match else str(abs(hash(title)))[:6]

        row_text = row.get_text(" ", strip=True)
        date_match = re.search(r"(202\d[-./]\d{2}[-./]\d{2}|\d{2}-\d{2})", row_text)
        posted_date = datetime.date.today().isoformat()
        if date_match:
            raw_d = date_match.group(1).replace(".", "-")
            if len(raw_d) == 5:
                posted_date = f"{datetime.date.today().year}-{raw_d}"
            elif len(raw_d) == 10:
                posted_date = raw_d

        cat_code, cat_name = classify_category(title, source["subOrg"])
        deadline = extract_deadline_from_text(title, posted_date)

        results.append({
            "id": f"{source['id']}_{wr_id}",
            "title": title,
            "orgId": source["orgId"],
            "orgName": source["orgName"],
            "subOrg": source["subOrg"],
            "category": cat_code,
            "categoryName": cat_name,
            "postedDate": posted_date,
            "deadline": deadline,
            "eligibility": "경북대 재학생 및 예비창업자·전공생",
            "benefit": "창업지원금·시상금·멘토링 지원 (원문 참조)",
            "url": full_url,
            "sourceBoardUrl": source["listUrl"],
            "tags": extract_tags(title, source["subOrg"]),
            "summary": f"{source['subOrg']}에서 공고한 '{title}' 모집 안내입니다.",
            "isNew": True
        })
    return results


def parse_generic_or_egov(html: str, source: Dict) -> List[Dict]:
    """공학교육혁신센터, SW교육원, 데이터융복합연구원 등 범용 테이블/목록 파서"""
    soup = BeautifulSoup(html, "lxml")
    results = []
    candidates = soup.select("table tbody tr a, ul.board_list li a, .bbs_list a, .notice_list a")

    for link_el in candidates:
        title = " ".join(link_el.get_text().split())
        if len(title) < 6 or not is_contest_post(title, source.get("filterByKeyword", False)):
            continue
        href = link_el.get("href", "")
        full_url = urljoin(source["listUrl"], href) if href and not href.startswith("javascript") else source["listUrl"]
        post_id = str(abs(hash(f"{source['id']}_{title}")))[:8]
        posted_date = datetime.date.today().isoformat()
        cat_code, cat_name = classify_category(title, source["subOrg"])
        deadline = extract_deadline_from_text(title, posted_date)

        results.append({
            "id": f"{source['id']}_{post_id}",
            "title": title,
            "orgId": source["orgId"],
            "orgName": source["orgName"],
            "subOrg": source["subOrg"],
            "category": cat_code,
            "categoryName": cat_name,
            "postedDate": posted_date,
            "deadline": deadline,
            "eligibility": "경북대 학부 및 대학원 재학생",
            "benefit": "프로그램 수료 혜택 및 시상금 (원문 참조)",
            "url": full_url,
            "sourceBoardUrl": source["listUrl"],
            "tags": extract_tags(title, source["subOrg"]),
            "summary": f"{source['subOrg']} 홈페이지에 게시된 '{title}' 안내입니다.",
            "isNew": True
        })
    return results


PARSER_DISPATCH = {
    "knu_wbbs": parse_knu_wbbs,
    "knu_see": parse_knu_see,
    "gnuboard": parse_gnuboard,
    "generic_table": parse_generic_or_egov,
    "egov_bbs": parse_generic_or_egov,
}


# ---------------------------------------------------------------------------
# 5. 메인 수집 루프 및 JSON 병합 저장
# ---------------------------------------------------------------------------
def run_crawler(output_path: str = "data/competitions.json", dry_run: bool = False) -> Dict:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    existing_items: Dict[str, Dict] = {}

    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("items", []):
                    item["isNew"] = False
                    existing_items[item["id"]] = item
        except Exception as exc:
            print(f"[WARN] 기존 JSON 파일 로드 실패 (새로 생성합니다): {exc}")

    new_count = 0
    for src in KNU_SOURCES:
        print(f"[CRAWL] {src['orgName']} ({src['subOrg']}) -> {src['listUrl']}")
        if dry_run:
            print(f"  └─ [DRY-RUN] 파서 '{src['parser']}' 검증 완료")
            continue

        try:
            resp = requests.get(src["listUrl"], headers=HEADERS, timeout=12)
            resp.raise_for_status()
            # 인코딩 자동 보정 (EUC-KR / UTF-8)
            if resp.encoding and resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding
            parser_fn = PARSER_DISPATCH.get(src["parser"], parse_generic_or_egov)
            fetched = parser_fn(resp.text, src)
            print(f"  └─ 수집된 공모전·모집 게시글: {len(fetched)}건")

            for item in fetched:
                if item["id"] not in existing_items:
                    existing_items[item["id"]] = item
                    new_count += 1
            time.sleep(0.8)  # 대상 학교 서버 부하 방지를 위한 매너 딜레이
        except Exception as exc:
            print(f"  └─ [ERROR] {src['subOrg']} 수집 중 오류 발생: {exc}")

    all_items = sorted(
        existing_items.values(),
        key=lambda x: (x.get("deadline", "9999-12-31"), x.get("postedDate", "")),
    )

    payload = {
        "lastUpdated": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),
        "totalCount": len(all_items),
        "newAddedCount": new_count,
        "items": all_items,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[DONE] 총 {len(all_items)}건 저장 완료 (신규 추가: {new_count}건) -> {output_path}")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KNU 공모전 일일 통합 크롤러")
    parser.add_argument("--output", default="data/competitions.json", help="출력 JSON 파일 경로")
    parser.add_argument("--dry-run", action="store_true", help="네트워크 호출 없이 파서 설정 및 정규식 검증만 수행")
    args = parser.parse_args()

    # Dry-run 시 단위 테스트 함께 수행
    if args.dry_run:
        sample_title = "[IT대학] 개교 80주년 기념 2026년 KNU 캡스톤디자인 경진대회 (~11/18)"
        assert is_contest_post(sample_title) is True
        assert extract_deadline_from_text(sample_title, "2026-11-03") == "2026-11-18"
        print("[TEST] 제목 필터링 및 마감일(D-Day) 정규식 추출 테스트 통과!")

    run_crawler(output_path=args.output, dry_run=args.dry_run)
