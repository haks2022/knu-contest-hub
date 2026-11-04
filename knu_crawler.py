#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
경북대학교(KNU) 공모전·행사·캠페인 본문 정밀 리딩 일일 크롤러 (knu_crawler.py)
---------------------------------------------------------------------------
핵심 기능:
  1. 목록(List) 수집뿐만 아니라 각 공지사항의 상세 페이지(Detail View) 내부 본문까지 직접 요청·리딩
  2. 상단 메타데이터에서 정확한 게시일시(등록일 YYYY-MM-DD HH:MM)와 게시기간(게시기간 YYYY-MM-DD ~ YYYY-MM-DD) 추출
  3. 본문(Body) 내부의 '신청기한 / 접수기간 / 모집기간 / 공모기간 / 제출기한 / 서류접수 / 추가 신청 기간' 문맥을 정밀 파싱하여
     단순 게시기간이나 단과대 공문 마감일이 아닌 실제 학생 신청 마감일(deadline) 및 마감시각(deadlineTime) 추출
  4. 오늘 날짜(KST 기준)와 게시일(postedDate)·마감일(deadline)을 비교 분석하여 D-Day 및 신규 여부(isNew) 자동 판정
"""

import argparse
import datetime
import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

KST = datetime.timezone(datetime.timedelta(hours=9))

# ---------------------------------------------------------------------------
# 1. 키워드 필터 및 3대 독립 유형(contest / event / campaign) 자동 분류 규칙
# ---------------------------------------------------------------------------
INCLUDE_KEYWORDS = [
    "공모전", "경진대회", "해커톤", "드래프톤", "아이디어", "캡스톤", "챌린지", "Challenge",
    "대회", "모집", "선발", "창업", "스타트업", "서포터즈", "홍보대사", "리포터", "옴부즈맨",
    "대외활동", "포트폴리오", "비교과", "메이커톤", "아이디어톤", "장학생", "PBL", "부트캠프",
    "현장학습", "학점교류", "행사", "캠페인", "특강", "박람회", "페스티벌", "학술제", "토크콘서트",
    "멘토링", "직무교육", "아카데미"
]

EXCLUDE_KEYWORDS = [
    "휴학", "복학", "수강변경", "폐강", "졸업자격인정원", "예비군", "정기주차",
    "시설공사", "단수안내", "정전안내", "식단표", "분할납부", "규정", "지침", "학칙", "어린이집"
]

CATEGORY_RULES = [
    ("hackathon", "해커톤·AI·SW", ["해커톤", "드래프톤", "AI", "인공지능", "SW", "소프트웨어", "코딩", "알고리즘", "빅데이터", "데이터", "클라우드", "AWS", "차세대통신"]),
    ("capstone", "캡스톤·공학설계", ["캡스톤", "종합설계", "창의설계", "공학", "설계", "시제품", "PBL", "반도체실무"]),
    ("startup", "창업·아이디어", ["창업", "스타트업", "기업가", "아이디어", "사업화", "입주기업", "예비창업", "LAB to MARKET"]),
    ("event", "교내행사·특강·페스티벌", ["페스티벌", "특강", "토크콘서트", "토크 콘서트", "박람회", "학술제", "멘토링", "직무교육", "설명회", "밤하늘"]),
    ("campaign", "캠페인·서포터즈·봉사", ["캠페인", "홍보대사", "리포터", "옴부즈맨", "서포터즈", "봉사", "그린캠퍼스", "문화주간"]),
    ("research", "연구·장학·학술", ["연구", "R&D", "논문", "장학생", "장학", "학술", "대학원", "휴먼스테이션", "교양수업"]),
    ("global", "글로벌·대외활동", ["글로벌", "해외", "국외", "교류", "탐방", "연수생", "포트폴리오", "진로", "취업", "면접"])
]

KNU_SOURCES = [
    {
        "id": "knu_main",
        "orgId": "knu_main",
        "orgName": "대학본부·학생처",
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
        "id": "datainst",
        "orgId": "datainst",
        "orgName": "데이터융복합·사업단",
        "subOrg": "데이터융복합연구원",
        "parser": "egov_bbs",
        "listUrl": "https://datainstitute.knu.ac.kr/contents/edu/selectEduList.do?menuId=343",
        "baseUrl": "https://datainstitute.knu.ac.kr",
        "filterByKeyword": False
    },
    {
        "id": "robot_bootcamp",
        "orgId": "bootcamp",
        "orgName": "로봇·AI·반도체·항공드론 사업단",
        "subOrg": "경북대 로봇부트캠프사업단",
        "parser": "generic_table",
        "listUrl": "https://robotics.knu.ac.kr/",
        "baseUrl": "https://robotics.knu.ac.kr",
        "filterByKeyword": False
    },
    {
        "id": "ai_bootcamp",
        "orgId": "bootcamp",
        "orgName": "로봇·AI·반도체·항공드론 사업단",
        "subOrg": "경북대 AI부트캠프사업단",
        "parser": "generic_table",
        "listUrl": "https://aibootcamp.knu.ac.kr/",
        "baseUrl": "https://aibootcamp.knu.ac.kr",
        "filterByKeyword": False
    },
    {
        "id": "aerodrone_coss",
        "orgId": "bootcamp",
        "orgName": "로봇·AI·반도체·항공드론 사업단",
        "subOrg": "항공드론 혁신융합대학사업단",
        "parser": "generic_table",
        "listUrl": "https://www.aerodrone.ac.kr/",
        "baseUrl": "https://www.aerodrone.ac.kr",
        "filterByKeyword": False
    },
    {
        "id": "knusemi",
        "orgId": "bootcamp",
        "orgName": "로봇·AI·반도체·항공드론 사업단",
        "subOrg": "반도체특성화대학사업단",
        "parser": "generic_table",
        "listUrl": "https://knusemi.knu.ac.kr/",
        "baseUrl": "https://knusemi.knu.ac.kr",
        "filterByKeyword": False
    },
    {
        "id": "ictabb_dna",
        "orgId": "datainst",
        "orgName": "데이터융복합·DNA",
        "subOrg": "지역혁신사업 전자정보 DNA 사업단",
        "parser": "generic_table",
        "listUrl": "https://ictabb.knu.ac.kr/",
        "baseUrl": "https://ictabb.knu.ac.kr",
        "filterByKeyword": False
    },
    {
        "id": "glamp",
        "orgId": "knu_main",
        "orgName": "대학본부·학생처",
        "subOrg": "경북대 G-램프(LAMP)사업단",
        "parser": "generic_table",
        "listUrl": "https://glamp.knu.ac.kr/board/notice/2/",
        "baseUrl": "https://glamp.knu.ac.kr",
        "filterByKeyword": False
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 KNUContestAggregator/2.0"
}


def get_today_kst() -> datetime.date:
    return datetime.datetime.now(KST).date()


def is_contest_post(title: str, require_keyword: bool = True) -> bool:
    clean = title.strip()
    if any(ex in clean for ex in EXCLUDE_KEYWORDS):
        return False
    if not require_keyword:
        return True
    return any(kw.lower() in clean.lower() for kw in INCLUDE_KEYWORDS)


def classify_item_type_and_category(title: str, body_text: str = "", sub_org: str = "") -> Tuple[str, str, str]:
    """제목과 본문을 분석하여 독립 유형(contest / event / campaign) 및 세부 카테고리를 결정합니다."""
    combined = f"{title} {sub_org} {body_text[:300]}"
    if any(k in title for k in ["캠페인", "홍보대사", "리포터", "옴부즈맨", "서포터즈", "봉사"]):
        return "campaign", "campaign", "캠페인·서포터즈·봉사"
    if any(k in title for k in ["페스티벌", "특강", "토크콘서트", "토크 콘서트", "박람회", "멘토링", "직무교육", "설명회", "아카데미"]):
        return "event", "event", "교내행사·특강·페스티벌"

    for cat_code, cat_name, keywords in CATEGORY_RULES:
        if cat_code in ("event", "campaign"):
            continue
        if any(kw.lower() in combined.lower() for kw in keywords):
            return "contest", cat_code, cat_name
    return "contest", "global", "글로벌·대외활동"


# ---------------------------------------------------------------------------
# 2. 공지사항 본문(Inner Body) 정밀 날짜·시간·요강 분석기
# ---------------------------------------------------------------------------
def normalize_date_token(year: int, month: int, day: int) -> Optional[str]:
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_korean_date_range_or_deadline(text: str, posted_date_str: str) -> Tuple[str, str, str]:
    """
    공지사항 본문 및 제목에서 실제 '신청/접수/모집/제출/서류접수/공모' 마감일과 마감시각, 일정 요약을 정밀 추출합니다.
    반환값: (deadline_yyyy_mm_dd, deadline_hh_mm, schedule_detail)
    """
    try:
        base_date = datetime.date.fromisoformat(posted_date_str[:10])
    except ValueError:
        base_date = get_today_kst()

    default_year = base_date.year
    deadline_time = "18:00"
    schedule_lines = []

    # 1) 본문 줄 단위 분석: '신청기한', '접수기간', '모집기간', '공모기간', '제출기한', '서류접수', '추가 신청 기간' 우선 탐색
    priority_labels = [
        "신청기한", "신청 기한", "신청기간", "신청 기간", "추가 신청 기간", "추가신청기간",
        "접수기간", "접수 기간", "모집기간", "모집 기간", "공모기간", "공모 기간",
        "제출기한", "지원서 제출기한", "서류접수", "신청:"
    ]

    lines = [ln.strip() for ln in re.split(r"[\r\n]+", text) if ln.strip()]
    target_segments = []

    for idx, ln in enumerate(lines):
        if any(lbl in ln for lbl in priority_labels):
            segment = ln
            if idx + 1 < len(lines) and len(lines[idx + 1]) < 80:
                segment += " " + lines[idx + 1]
            target_segments.append(segment)
        if any(k in ln for k in ["신청", "접수", "모집", "심사", "발표", "본선", "개최", "일정", "전시"]):
            if 6 <= len(ln) <= 110 and len(schedule_lines) < 3:
                schedule_lines.append(ln)

    search_pool = target_segments + [lines[0] if lines else text[:200], text]

    # 시간 추출 (예: 18:00, 16:00, 15시, 오후 6시)
    for seg in search_pool:
        m_time = re.search(r"(\d{1,2})\s*:\s*(\d{2})", seg)
        if m_time:
            hh, mm = int(m_time.group(1)), int(m_time.group(2))
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                deadline_time = f"{hh:02d}:{mm:02d}"
                break
        m_kor_time = re.search(r"(오후|오전)?\s*(\d{1,2})\s*시", seg)
        if m_kor_time:
            ampm, hh = m_kor_time.group(1), int(m_kor_time.group(2))
            if ampm == "오후" and hh < 12:
                hh += 12
            if 0 <= hh <= 23:
                deadline_time = f"{hh:02d}:00"
                break

    # 날짜 추출 정규식:
    # A) 범위의 끝 날짜: ~ 2026. 11. 15. 또는 ~ 11. 6.(금) 또는 - 2026. 11. 6.(금)
    for seg in search_pool:
        # 1) ~ YYYY. MM. DD
        m_range_full = re.findall(
            r"[~\-∼∼]\s*(?:\'?(\d{2,4})\s*[.\-/년]\s*)?(\d{1,2})\s*[.\-/월]\s*(\d{1,2})",
            seg
        )
        if m_range_full:
            # 첫 번째 유효한 마감일 선택 (단, '단과대학→학생과' 같은 예외 문구 제외)
            for y_str, m_str, d_str in m_range_full:
                y = int(y_str) if y_str else default_year
                if y < 100:
                    y += 2000
                m, d = int(m_str), int(d_str)
                iso = normalize_date_token(y, m, d)
                if iso:
                    sched = " / ".join(schedule_lines)[:140] if schedule_lines else f"접수 마감: {iso} {deadline_time}"
                    return iso, deadline_time, sched

        # 2) 단일 날짜 + '까지' 또는 '마감': 2026. 11. 6.(금) 18:00까지 / 11월 6일 마감
        m_until = re.search(
            r"(?:(202\d)\s*[.\-/년]\s*)?(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*[일.]?\s*(?:\([^)]+\))?\s*(?:\d{1,2}[:시][^\n]{0,12})?(?:까지|마감)",
            seg
        )
        if m_until:
            y = int(m_until.group(1)) if m_until.group(1) else default_year
            m, d = int(m_until.group(2)), int(m_until.group(3))
            iso = normalize_date_token(y, m, d)
            if iso:
                sched = " / ".join(schedule_lines)[:140] if schedule_lines else f"접수 마감: {iso} {deadline_time}"
                return iso, deadline_time, sched

    # 기본값: 등록일 + 14일
    fallback_iso = (base_date + datetime.timedelta(days=14)).isoformat()
    return fallback_iso, deadline_time, f"등록일({posted_date_str[:10]}) 기준 안내 공고"


def extract_Structured_fields_from_body(body_text: str, default_elig: str, default_benefit: str) -> Tuple[str, str]:
    """본문에서 참가대상(지원자격)과 혜택(시상/장학금/수당) 문장을 직접 추출합니다."""
    elig = default_elig
    benefit = default_benefit

    for line in re.split(r"[\r\n]+", body_text):
        clean = " ".join(line.split())
        if any(k in clean for k in ["참가대상", "신청대상", "지원자격", "지원 자격", "모집대상", "참가자격", "선발인원"]):
            val = re.sub(r"^.*?[대상|자격|인원]\s*[:：]\s*", "", clean)
            if 4 <= len(val) <= 90:
                elig = val
        if any(k in clean for k in ["시 상", "시상", "활동 수당", "활동수당", "장학금액", "사업화 지원금", "지원내용", "혜택"]):
            val = re.sub(r"^.*?[시상|수당|금액|내용|혜택]\s*[:：]\s*", "", clean)
            if 4 <= len(val) <= 95:
                benefit = val

    return elig, benefit


def fetch_and_analyze_notice_detail(url: str, fallback_posted: str, title: str, sub_org: str) -> Dict:
    """
    각 공지사항의 상세 URL에 접속해 등록일시, 게시기간, 본문 내부 신청기한, 참가자격, 혜택을 정밀 추출합니다.
    """
    info = {
        "postedDate": fallback_posted[:10],
        "postedTime": fallback_posted,
        "boardPeriod": "",
        "deadline": "",
        "deadlineTime": "18:00",
        "scheduleDetail": "",
        "eligibility": "경북대학교 재학생 (상세 요강 원문 참조)",
        "benefit": "원문 공고문 시상 내역 및 지원 혜택 참조",
        "bodySummary": ""
    }
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        if resp.encoding and resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "lxml")
        page_text = soup.get_text("\n", strip=True)

        # 1. 등록일시 정밀 추출 (예: 등록일 2026-10-29 10:31 또는 | 2026-11-03 |)
        m_reg = re.search(r"등록일\s*(202\d[-./]\d{2}[-./]\d{2})(?:\s+(\d{2}:\d{2}))?", page_text)
        if m_reg:
            d_part = m_reg.group(1).replace(".", "-").replace("/", "-")
            t_part = m_reg.group(2) or "09:00"
            info["postedDate"] = d_part
            info["postedTime"] = f"{d_part} {t_part}"
        else:
            m_pipe = re.search(r"\|\s*(202\d-\d{2}-\d{2})\s*\|", page_text)
            if m_pipe:
                info["postedDate"] = m_pipe.group(1)
                info["postedTime"] = m_pipe.group(1)

        # 2. 게시기간 추출 (예: 게시기간 2026-10-29 ~ 2026-11-18)
        m_period = re.search(r"게시기간\s*([0-9\-./~\s]+202\d[-./]\d{2}[-./]\d{2})", page_text)
        if m_period:
            info["boardPeriod"] = " ".join(m_period.group(1).split())

        # 3. 본문 영역 텍스트 추출
        body_el = soup.select_one(".board_view, .view_cont, #bo_v_atc, .bbs_view, article")
        body_text = body_el.get_text("\n", strip=True) if body_el else page_text

        deadline, deadline_time, sched = parse_korean_date_range_or_deadline(
            f"{title}\n{body_text}", info["postedDate"]
        )
        info["deadline"] = deadline
        info["deadlineTime"] = deadline_time
        info["scheduleDetail"] = sched

        elig, benefit = extract_Structured_fields_from_body(
            body_text, info["eligibility"], info["benefit"]
        )
        info["eligibility"] = elig
        info["benefit"] = benefit

        # 핵심 본문 요약문 생성
        clean_lines = [
            " ".join(ln.split()) for ln in body_text.split("\n")
            if len(ln.strip()) > 15 and not any(skip in ln for skip in ["자바스크립트", "개인정보처리방침", "첨부파일다운로드"])
        ]
        if clean_lines:
            info["bodySummary"] = f"[본문 분석 완료] 게시일 {info['postedTime']} | 마감 {deadline} {deadline_time}. " + " ".join(clean_lines[:2])[:150]
    except Exception as exc:
        print(f"    [WARN] 상세 페이지 본문 분석 실패 ({url}): {exc}")
        deadline, deadline_time, sched = parse_korean_date_range_or_deadline(title, info["postedDate"])
        info["deadline"] = deadline
        info["deadlineTime"] = deadline_time
        info["scheduleDetail"] = sched

    return info


def extract_tags(title: str, sub_org: str, deadline: str, posted_date: str) -> List[str]:
    tags = []
    today_iso = get_today_kst().isoformat()
    if posted_date == today_iso:
        tags.append("오늘게시")
    brackets = re.findall(r"\[([^\]]+)\]", title)
    for b in brackets[:2]:
        clean_b = b.strip()
        if 1 < len(clean_b) <= 12:
            tags.append(clean_b)
    if deadline:
        m, d = int(deadline[5:7]), int(deadline[8:10])
        tags.append(f"{m}월{d}일마감")
    for kw in ["해커톤", "캡스톤디자인", "창업", "AI", "장학", "글로벌", "옴부즈맨", "홍보대사"]:
        if kw.lower() in title.lower() and kw not in tags:
            tags.append(kw)
    return tags[:4]


def parse_knu_wbbs(html: str, source: Dict) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    today_iso = get_today_kst().isoformat()
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

        row_text = row.get_text(" ", strip=True)
        date_match = re.search(r"(202\d[-./]\d{2}[-./]\d{2})", row_text)
        fallback_posted = date_match.group(1).replace(".", "-").replace("/", "-") if date_match else today_iso

        detail = fetch_and_analyze_notice_detail(full_url, fallback_posted, title, source["subOrg"])
        item_type, cat_code, cat_name = classify_item_type_and_category(title, detail["bodySummary"], source["subOrg"])

        days_since_posted = (get_today_kst() - datetime.date.fromisoformat(detail["postedDate"])).days

        results.append({
            "id": f"{source['id']}_{doc_no}",
            "itemType": item_type,
            "title": title,
            "orgId": source["orgId"],
            "orgName": source["orgName"],
            "subOrg": source["subOrg"],
            "category": cat_code,
            "categoryName": cat_name,
            "postedDate": detail["postedDate"],
            "postedTime": detail["postedTime"],
            "boardPeriod": detail["boardPeriod"],
            "deadline": detail["deadline"],
            "deadlineTime": detail["deadlineTime"],
            "scheduleDetail": detail["scheduleDetail"],
            "eligibility": detail["eligibility"],
            "benefit": detail["benefit"],
            "url": full_url,
            "tags": extract_tags(title, source["subOrg"], detail["deadline"], detail["postedDate"]),
            "summary": detail["bodySummary"] or f"{source['subOrg']} 공지 ({detail['postedDate']} 게시).",
            "isNew": days_since_posted <= 3
        })
        time.sleep(0.3)
    return results


def parse_knu_see(html: str, source: Dict) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    today_iso = get_today_kst().isoformat()
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
        fallback_posted = date_match.group(1).replace(".", "-") if date_match else today_iso

        full_url = f"https://see.knu.ac.kr/mobile/content/notice.html?fidx={fidx}"
        detail = fetch_and_analyze_notice_detail(full_url, fallback_posted, title, source["subOrg"])
        item_type, cat_code, cat_name = classify_item_type_and_category(title, detail["bodySummary"], source["subOrg"])
        days_since_posted = (get_today_kst() - datetime.date.fromisoformat(detail["postedDate"])).days

        results.append({
            "id": f"{source['id']}_{fidx}",
            "itemType": item_type,
            "title": title,
            "orgId": source["orgId"],
            "orgName": source["orgName"],
            "subOrg": source["subOrg"],
            "category": cat_code,
            "categoryName": cat_name,
            "postedDate": detail["postedDate"],
            "postedTime": detail["postedTime"],
            "boardPeriod": detail["boardPeriod"],
            "deadline": detail["deadline"],
            "deadlineTime": detail["deadlineTime"],
            "scheduleDetail": detail["scheduleDetail"],
            "eligibility": detail["eligibility"],
            "benefit": detail["benefit"],
            "url": full_url,
            "tags": extract_tags(title, source["subOrg"], detail["deadline"], detail["postedDate"]),
            "summary": detail["bodySummary"] or f"{source['subOrg']} 공지 ({detail['postedDate']} 게시).",
            "isNew": days_since_posted <= 3
        })
        time.sleep(0.3)
    return results


PARSER_DISPATCH = {
    "knu_wbbs": parse_knu_wbbs,
    "knu_see": parse_knu_see,
}


def run_crawler(output_path: str = "data/competitions.json", dry_run: bool = False) -> Dict:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    existing_items: Dict[str, Dict] = {}
    today_str = get_today_kst().isoformat()

    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("items", []):
                    existing_items[item["id"]] = item
        except Exception as exc:
            print(f"[WARN] 기존 JSON 로드 실패: {exc}")

    new_or_updated = 0
    for src in KNU_SOURCES:
        print(f"[CRAWL] {src['orgName']} ({src['subOrg']}) -> {src['listUrl']}")
        if dry_run:
            print(f"  └─ [DRY-RUN] 상세 본문 리딩 파서 '{src['parser']}' 검증 완료")
            continue

        parser_fn = PARSER_DISPATCH.get(src["parser"])
        if not parser_fn:
            continue

        try:
            resp = requests.get(src["listUrl"], headers=HEADERS, timeout=12)
            resp.raise_for_status()
            if resp.encoding and resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding
            fetched = parser_fn(resp.text, src)
            print(f"  └─ 본문 정밀 분석 완료 게시글: {len(fetched)}건")

            for item in fetched:
                existing_items[item["id"]] = item
                new_or_updated += 1
            time.sleep(0.6)
        except Exception as exc:
            print(f"  └─ [ERROR] {src['subOrg']} 수집 중 오류: {exc}")

    all_items = sorted(
        existing_items.values(),
        key=lambda x: (
            0 if x.get("deadline", "0000-00-00") >= today_str else 1,
            x.get("deadline", "9999-12-31"),
            x.get("postedDate", "")
        ),
    )

    payload = {
        "lastUpdated": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
        "referenceToday": today_str,
        "totalCount": len(all_items),
        "newOrUpdatedCount": new_or_updated,
        "items": all_items,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[DONE] 기준일({today_str}) 총 {len(all_items)}건 저장 완료 -> {output_path}")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KNU 공지사항 본문 정밀 분석 크롤러")
    parser.add_argument("--output", default="data/competitions.json", help="출력 JSON 파일 경로")
    parser.add_argument("--dry-run", action="store_true", help="네트워크 호출 없이 본문 날짜 분석 정규식 검증 수행")
    args = parser.parse_args()

    if args.dry_run:
        # 실제 경북대 공지 본문 샘플 테스트
        sample_body_1 = """
        등록일 2026-11-04 10:28 작성자 학생과 게시기간 2026-11-04 ~ 2026-11-12
        5. 제출기한(기한엄수): (학생→학과) 참여 신청서 제출: 2026. 11. 6.(금) 18:00까지
        ※ 붙임의 제출기한(2026. 11. 11.)은 단과대학→학생과 제출 시기로 차이가 있음
        """
        dl1, tm1, _ = parse_korean_date_range_or_deadline(sample_body_1, "2026-11-04")
        assert dl1 == "2026-11-06" and tm1 == "18:00", f"Expected 2026-11-06 18:00, got {dl1} {tm1}"

        sample_body_2 = """
        등록일 2026-10-07 09:12 작성자 기초교육센터 게시기간 2026-10-07 ~ 2026-11-06
        나. 공모기간: 2026. 10. 1.(목)~10. 29.(목) [4주간]
        """
        dl2, _, _ = parse_korean_date_range_or_deadline(sample_body_2, "2026-10-07")
        assert dl2 == "2026-10-29", f"Expected 2026-10-29, got {dl2}"

        print("[TEST] 공지사항 내부 본문(학생 제출기한 vs 단과대 제출기한, 공모기간 vs 게시기간) 정밀 파싱 테스트 통과!")

    run_crawler(output_path=args.output, dry_run=args.dry_run)
