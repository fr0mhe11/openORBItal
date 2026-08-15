# Orbi 글 매니저

내 orbi.kr 계정의 글을 목록으로 보고, 체크박스로 골라 백업하거나 삭제하는 데스크톱 도구.

**삭제는 되돌릴 수 없습니다.** 그래서 기본값이 안전한 쪽으로 잡혀 있습니다.

- 모의 실행(dry-run) 체크박스가 **기본 켜짐** — 실제 삭제 요청을 보내지 않고 무엇을 보낼지만 기록합니다.
- 삭제 개수를 **직접 입력해야** 확인 창이 통과됩니다.
- 백업은 자동으로 되지 않습니다 — "백업 export" 모드에서 선택한 글을 직접 백업 버튼으로 내보내야 합니다.
- 한 번 불러올 때 글 **300개**까지만 수집합니다.
- 한 번에 최대 **300개** 선택. 평소 삭제 사이에는 짧은 간격만 둡니다.
- 사이트가 429(요청 과다)를 반환하면 기본 **60초** 대기 후 **같은 글을 다시 시도**합니다
  (최대 2회). 그래도 429면 사이트가 세션 전체를 막고 있다는 뜻이므로 **배치를 중단**합니다 —
  남은 글로 넘어가 봐야 같은 답만 돌아옵니다. 429 때문에 못 지운 글은 재시도 없이
  넘어가지 않습니다.
- 사이트가 거부하는 항목(이미 지워진 글 등)은 **건너뛰고 다음 항목으로** 갑니다.
  이런 건 실패로 세지 않고 대기도 안 겁니다. 진짜 실패(인증 만료·서버 오류)가 **연속 3회**일 때만 중단.
- 본인 계정에만 사용하세요.

## 설치

```bash
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

## 실행

```bash
./.venv/bin/python -m orbi_manager          # GUI
./.venv/bin/python -m orbi_manager --cli    # 목록만 출력 (스크레이퍼 점검)
```

로그인은 아이디/비밀번호로 사이트에 직접 POST하는 방식 한 가지뿐입니다. 소셜 로그인·캡차·
2단계 인증이 걸린 계정은 지원하지 않습니다.

아이디/비밀번호도, 세션 쿠키도 디스크에 저장하지 않습니다. 로그인 정보는 프로세스가
살아 있는 동안 메모리에만 있고 창을 닫으면 사라지므로, 실행할 때마다 다시 로그인해야
합니다.

## 사이트 구조 (조사 완료)

`scripts/recon.py` 캡처와 오르비 JS 번들(`s3.orbi.kr/assets/orbi-app.pc.js`)에서 확인한 값들.
전부 [selectors.py](src/orbi_manager/selectors.py)에 들어 있습니다.

| 항목 | 값 |
|------|-----|
| 로그인 | `POST https://login.orbi.kr/login` — `url`, `username`, `password` (폼 인코딩, `X-Requested-With: XMLHttpRequest`) |
| 내 회원번호 | 로그인 상태 페이지의 `dataLayer.push({ user_id: "…" })` |
| 내 글 목록 | `GET /search?type=imin&q={uid}&page={n}` |
| 목록 행 | `ul.post-list > li` (`li.notice`는 운영자 공지 → 제외) |
| 글 삭제 | `POST /delete/{번호}` — 앞자리 0 없는 번호 (`00079187183` → `79187183`) |
| CSRF | 없음 — 세션 쿠키가 유일한 자격증명 |

**주의 — 이름과 실제 메서드가 다릅니다.** 사이트 코드의 `httpUnited.delete(url)`은
이름만 delete고 내부는 `$http.post(url)`입니다. 그래서 글 삭제는 실제로 POST이고,
진짜 DELETE로 보내면 405가 돌아옵니다.

재조사가 필요하면:

```bash
./.venv/bin/python scripts/recon.py
```

로그인 POST 본문은 기록하지 않습니다(비밀번호 유출 방지). 스크립트 자체는 아무것도 삭제하지 않습니다.

## 구조

| 파일 | 역할 |
|------|------|
| `src/orbi_manager/auth.py` | 아이디/비밀번호 로그인, httpx 클라이언트 소유 |
| `src/orbi_manager/scraper.py` | 내 글 목록 수집 (페이지네이션) |
| `src/orbi_manager/deleter.py` | 삭제 (HTTP 재현), dry-run, 배치 |
| `src/orbi_manager/exporter.py` | JSON + CSV 백업 (CSV는 BOM 포함) |
| `src/orbi_manager/ratelimit.py` | 429 대기, 중단 가능 |
| `src/orbi_manager/selectors.py` | **모든 CSS 선택자와 URL 템플릿** — 사이트가 바뀌면 여기만 고침 |
| `src/orbi_manager/modes.py` | 모드 정의 (조회 / 글 삭제 / 백업) |
| `src/orbi_manager/worker.py` | 로그인 세션을 소유한 단일 백그라운드 스레드 |
| `src/orbi_manager/ui/` | PySide6 창, 체크박스 테이블, 확인 창, 로그 |

## 테스트

```bash
QT_QPA_PLATFORM=offscreen ./.venv/bin/python -m pytest -q
```

파서 테스트(`tests/test_parsers.py`)는 `tests/fixtures/`의 HTML을 읽습니다. recon 실행 후
실제 캡처 파일로 교체하면 사이트 변경이 곧바로 테스트 실패로 드러납니다.
`tests/test_safety.py`는 dry-run이 변경 요청을 **한 건도** 보내지 않는지, 429를 맞은 글이
버려지지 않고 재시도되는지, 429가 계속되면 배치가 중단되는지, 429 대기 하한과 선택
한도가 지켜지는지 검사합니다.
