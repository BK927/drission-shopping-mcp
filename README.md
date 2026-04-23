# Drission Shopping MCP

**네이버 쇼핑 검색 + 상세 페이지 추출** 을 ChatGPT 같은 MCP 클라이언트에 노출하는 HTTP 서버입니다. 리눅스 한 대만 있으면 돌아갑니다 — Raspberry Pi 든 VPS 든 동일한 명령으로 설치됩니다.

핵심 흐름:

1. 네이버 쇼핑 검색 API 로 후보 상품 검색
2. 후보의 `link` 를 DrissionPage 로 열어 렌더링
3. JSON-LD / meta / DOM 에서 상품 상세를 구조화 추출
4. MCP 클라이언트가 `/mcp` 로 호출

## 포함된 MCP tools

- `search_naver_products` — 네이버 쇼핑 검색 API 주요 파라미터(`query`, `display`, `start`, `sort`, `filter`, `exclude`) 노출
- `search_naver_products_raw` — 네이버 원본 응답에 가까운 JSON
- `get_product_detail` — 상세 페이지 렌더링 후 제목, 가격, 이미지, 설명, 옵션, 스펙, 리뷰/평점 추출
- `search_then_fetch_detail` — 검색 + 특정 순번의 상세를 한 번에
- `capture_product_page` — 디버깅용 HTML / 스크린샷 저장

## 빠른 시작 (로컬)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
# .env 편집 — NAVER_CLIENT_ID / SECRET 입력 + MCP_AUTH_TOKEN 설정 (아래 보안 섹션)
python -m shopping_mcp.asgi
```

기본 엔드포인트:

- MCP: `http://127.0.0.1:8000/mcp`
- Health: `http://127.0.0.1:8000/healthz`

## 보안 (반드시 읽어주세요)

이 서버는 Chromium 을 `--no-sandbox` 로 구동하고 외부 URL 을 렌더링합니다. **공개 HTTPS 엔드포인트로 띄울 때는 인증 없이 노출하면 안 됩니다.**

**최소 필수 3단계** — 배포 전에 반드시 확인:

1. **`MCP_AUTH_TOKEN` 을 생성해서 `.env` 에 넣고 `chmod 600 .env`**
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   토큰이 비어있으면 앱이 자동으로 `127.0.0.1` 에만 바인딩하도록 fail-closed 됩니다 (공개 실수 노출 방지).

2. **공개 노출 시 Cloudflare Tunnel + Cloudflare Access 정책** 을 함께 쓰세요. Quick Tunnel 은 테스트 전용이고, 실사용은 Named Tunnel 에 Access 정책(이메일 / 서비스 토큰) 을 거는 것을 권장합니다.

3. **Chromium 을 주기적으로 업데이트.** `sudo apt update && sudo apt upgrade -y` — 샌드박스가 꺼진 상태라 Chromium 버전이 마지막 방어선입니다.

전체 위협 모델, 방어 구조, 운영 체크리스트, 토큰 회전 절차, 사고 대응 가이드는 **[docs/SECURITY.md](docs/SECURITY.md)** 에 정리되어 있습니다. 몇 개월 뒤 본인이나 다른 사람이 이 서버를 다시 만질 때는 그 문서를 먼저 보세요.

기본으로 들어가 있는 방어층 요약:

- Bearer 토큰 미들웨어 (`hmac.compare_digest`, 빈 토큰이면 `127.0.0.1` 강제)
- URL allowlist (네이버 쇼핑 5개 도메인) + 파서 차이 공격 차단 (`\`, `\t`, `\n`, `\0` 등)
- 최종 URL 재검증 (리다이렉트 따라간 뒤 allowlist 벗어나면 결과 폐기)
- Chromium `--host-resolver-rules` 로 DNS 레벨에서도 allowlist 강제
- Chromium 공격 표면 축소 플래그 (`--disable-extensions`, `--disable-sync`, `--no-first-run` 등)
- 파라미터 clamp (`wait_seconds ≤ 15s`, `max_description_chars ≤ 20000`)
- 디버그 캡처 rotation (최근 50개) + HTML 2MB cap
- systemd 샌드박싱 (`NoNewPrivileges`, `ProtectSystem=strict`, `ProtectProc=invisible`, `CapabilityBoundingSet=` 빈값 등)

## 어디서 돌아가나

**리눅스 + systemd 가 있는 곳이면 됩니다.** 코드는 OS / 아키텍처 종속이 없고, 설치 스크립트가 현재 유저 / 경로 / 홈 디렉토리를 읽어 systemd unit 을 자동 맞춤 설치합니다. Raspberry Pi 도 이 중 한 케이스일 뿐이라, 특별히 가지고 있지 않아도 괜찮습니다.

전제 조건:

- **리눅스 + systemd** — Ubuntu / Debian / Raspberry Pi OS 는 기본 OK. RHEL 계열도 systemd 는 같지만 chromium 패키지 이름이 다를 수 있습니다.
- **Python 3.10 이상** — Ubuntu 22.04 / Debian 12 / 최근 Pi OS 모두 충족.
- **Chromium 계열 바이너리** — `apt install chromium` (Debian / Ubuntu). `.env` 의 `DP_BROWSER_PATH` 를 실제 설치 경로에 맞추세요. (`shutil.which` 가 자동 탐색하지만 명시하는 편이 안전.)
- **RAM 1 GB 이상 권장** — Chromium 요구. 512 MB 이하에서는 스왑을 잡거나 더 큰 서버를 쓰세요.
- **공인 IP 는 불필요** — Cloudflare Tunnel 이 outbound 연결로 붙습니다. 포트 포워딩 / 방화벽 인바운드 규칙 없이 인터넷에서 접근할 수 있게 됩니다.

### 실배포 시 알아두면 좋은 것

1. **IP 대역과 네이버 봇 감지**: 네이버 쇼핑 API 자체는 IP 무관하게 동작합니다. 그러나 `get_product_detail` 이 여는 **실제 상품 페이지** 는 해외 IP 에서 더 자주 차단되거나 캡차가 뜹니다. 스크래핑 품질이 중요하면 **국내 IP 대역의 서버** 를 고르는 쪽이 실질적으로 유리합니다.

2. **ARM vs x86**: 둘 다 문제 없이 동작합니다. `lxml` / `pydantic` 바이너리 휠과 Chromium 패키지 모두 양쪽 아키텍처로 제공됩니다.

3. **작은 인스턴스에서 장시간 구동**: Chromium 은 오래 돌면 메모리가 조금씩 늘어납니다. `BrowserManager._is_page_alive` 가 죽은 탭을 자동 재생성하지만, 1 GB 이하 서버라면 보험으로 **주 1회 `systemctl restart shopping-mcp` cron** 을 걸어두세요.

4. **경로 자동화**: `.env` 의 `DP_USER_DATA_DIR=~/.cache/drission-shopping-mcp` 는 런타임에 서비스 유저 홈으로 확장됩니다. `scripts/install_systemd_pi.sh` 는 `User` / `WorkingDirectory` / `ReadWritePaths` 를 실행 중인 유저 / 경로 기준으로 자동 치환하므로, 어떤 리눅스 배포든 동일한 한 줄 명령으로 설치됩니다.

5. **PaaS (스핀다운이 있는 무료 플랫폼) 는 피하세요**: 항상 떠 있어야 하는 headless Chromium 서버에는 컨테이너 제약 / 슬립이 있는 플랫폼이 잘 안 맞습니다. 쉘 접근이 있는 일반 VM 이 훨씬 편합니다.

## 실배포 (systemd + Cloudflare Tunnel)

동봉된 운영 파일:

- `deploy/systemd/shopping-mcp.service`
- `deploy/cloudflared/config.example.yml`
- `scripts/install_cloudflared_pi.sh`
- `scripts/install_systemd_pi.sh`
- `scripts/run_quick_tunnel.sh`
- `docs/RASPBERRY_PI_CLOUDFLARE_DEPLOY.md` — 단계별 예시 (Pi 기반이지만 다른 리눅스 서버에서도 그대로 적용)
- `docs/SECURITY.md` — 운영 보안 가이드

대략적 배포 순서:

1. 앱 로컬 실행 확인 — `MCP_AUTH_TOKEN` 설정 후 로그에 `/mcp is OPEN` 경고가 없는지 확인
2. systemd 유닛 등록: `bash scripts/install_systemd_pi.sh ~/drission-shopping-mcp`
3. Cloudflare Tunnel (Named) 설치
4. **Cloudflare Access 정책 설정** (이메일 또는 서비스 토큰)
5. ChatGPT 등 MCP 클라이언트에 `https://.../mcp` + `Authorization: Bearer <MCP_AUTH_TOKEN>` 등록

자세한 단계:

- [docs/RASPBERRY_PI_CLOUDFLARE_DEPLOY.md](docs/RASPBERRY_PI_CLOUDFLARE_DEPLOY.md)
- [docs/SECURITY.md](docs/SECURITY.md)

> 스크립트 파일명에 `_pi` 가 붙어 있지만 내용은 일반 Linux + systemd 환경 전반을 가정합니다. Raspberry Pi 로 시작한 프로젝트의 흔적이며 기능적 의미는 없습니다.

## 주의사항

- 이 프로젝트는 **범용 추출기 + 네이버 스마트스토어 어댑터** 구조입니다.
- 사이트마다 DOM 구조가 달라 100% 만능은 아닙니다.
- `capture_product_page` 결과의 HTML / 스크린샷을 보고 셀렉터를 보강하는 식으로 정확도를 올리는 것이 가장 빠릅니다.
- 로그인 필요 페이지, 강한 봇 차단, 캡차는 별도 대응이 필요합니다.
- `ALLOWED_PRODUCT_HOSTS` 환경변수로 허용 도메인을 확장할 수 있지만, **기본값을 전부 대체** 합니다. 네이버 + 추가 도메인을 원하면 네이버 도메인도 명시적으로 포함해야 합니다.

## 개발

```bash
# 테스트 실행
.venv/bin/python -m pytest tests/ -v             # Linux / macOS
./.venv/Scripts/python.exe -m pytest tests/ -v   # Windows
```

현재 테스트 52개 (보안 회귀 테스트 포함).
