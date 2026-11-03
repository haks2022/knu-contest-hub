# 경북대학교 공모전·대외활동 통합 허브 (KNU Contest Hub) 백엔드 패키지

직접 복잡한 서버 코드를 짜지 않고 **바이브 코딩(Cursor, Windsurf, Claude, GitHub Pages/Vercel)**으로 하루 1회 자동 업데이트되는 경북대 공모전 사이트를 운영할 수 있도록 구성된 패키지입니다.

## 폴더 구조

- `knu_crawler.py`: 경북대 본부, IT대학(전자·컴학), 공학교육혁신센터, SW교육원, 창업지원단, 데이터융복합연구원, 진로취업과(KNUCUBE) 게시판 맞춤 크롤러
- `data/competitions.json`: 크롤러가 매일 갱신하는 정형 공모전 데이터 (프론트엔드 연동용)
- `.github/workflows/daily_crawl.yml`: 별도 유료 서버 없이 매일 아침 9시(KST) 자동으로 `knu_crawler.py`를 실행해 `data/competitions.json`을 업데이트하는 GitHub Actions 스케줄러
- `requirements.txt`: Python 필수 라이브러리 목록

## 바이브 코딩 3분 연동 방법

1. 이 폴더의 파일들을 본인의 GitHub 저장소(Repository)에 업로드합니다.
2. GitHub 저장소의 **Settings > Actions > General > Workflow permissions**에서 `Read and write permissions`를 체크합니다.
3. 바이브 코딩 AI 에디터(Cursor, Windsurf 등)에 아래 프롬프트를 입력하면 웹사이트와 크롤러 데이터가 즉시 연결됩니다:

> "프로젝트 루트의 `data/competitions.json` 파일을 `fetch('./data/competitions.json')`으로 불러와서 화면의 초기 공모전 리스트(`INITIAL_COMPETITIONS`)에 바인딩해 줘. 그리고 `knu_crawler.py`의 `KNU_SOURCES` 리스트에 내가 원하는 학과 공지사항 URL을 추가할 수 있게 유지해 줘."
