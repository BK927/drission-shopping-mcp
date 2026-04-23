# DrissionPage Shopping MCP

라즈베리파이에서 돌리기 쉽게 만든 **네이버 쇼핑 검색 + 상세 페이지 추출**용 MCP 서버입니다.

핵심 흐름:
1. 네이버 쇼핑 검색 API로 후보 상품 검색
2. 후보의 `link`를 열어 DrissionPage로 렌더링
3. JSON-LD / meta / DOM에서 상품 상세를 구조화 추출
4. ChatGPT 같은 MCP 클라이언트가 `/mcp` 로 호출

## 포함된 MCP tools

- `search_naver_products`
  - 네이버 쇼핑 검색 API의 주요 파라미터(`query`, `display`, `start`, `sort`, `filter`, `exclude`)를 거의 그대로 노출
- `search_naver_products_raw`
  - 네이버 원본 응답에 가까운 JSON 반환
- `get_product_detail`
  - 상세 페이지 렌더링 후 제목, 가격, 이미지, 설명, 옵션, 스펙, 리뷰/평점 등을 추출
- `search_then_fetch_detail`
  - 검색 후 특정 순번 결과의 상세까지 한 번에 반환
- `capture_product_page`
  - 디버깅용 HTML/스크린샷 저장

## 빠른 시작

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
# .env 편집 — 반드시 MCP_AUTH_TOKEN을 설정하세요 (아래 보안 섹션 참고)
python -m shopping_mcp.asgi
```

기본 엔드포인트:
- MCP: `http://127.0.0.1:8000/mcp`
- Health: `http://127.0.0.1:8000/healthz`

## 보안 (반드시 읽어주세요)

이 서버는 Chromium을 `--no-sandbox`로 구동하고 네이버 쇼핑 URL을 임의로 열 수 있습니다. **공개 HTTPS 엔드포인트로 띄울 때는 인증 없이 노출하면 안 됩니다.**

**최소 필수 3단계** — 배포 전에 반드시 확인:

1. **`MCP_AUTH_TOKEN` 을 생성해서 `.env` 에 넣고 `chmod 600 .env`**
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   토큰이 없으면 앱이 자동으로 `127.0.0.1` 에만 바인딩하도록 fail-closed 됩니다 (공개로 실수 노출 방지).

2. **Cloudflare Tunnel + Cloudflare Access 정책.** Quick Tunnel 은 테스트 전용. 실사용은 Named Tunnel 에 Access 정책(이메일/서비스 토큰) 을 걸어야 합니다.

3. **Pi 를 주기적으로 업데이트.** `sudo apt update && sudo apt upgrade -y` — 특히 `chromium` 패키지. 샌드박스 꺼진 상태라 Chromium 버전이 마지막 방어선.

전체 위협 모델, 방어 구조, 운영 체크리스트, 토큰 회전 절차, 사고 대응 가이드는 **[docs/SECURITY.md](docs/SECURITY.md)** 에 정리되어 있습니다. 몇 개월 뒤 본인이나 다른 사람이 이 서버를 다시 만질 때는 그 문서를 기준으로 점검하세요.

기본으로 들어가 있는 방어층 요약:

- Bearer 토큰 미들웨어 (`hmac.compare_digest`, 빈 토큰이면 `127.0.0.1` 강제)
- URL allowlist (네이버 쇼핑 5개 도메인) + 파서 차이 공격 방어 (`\`, `\t`, `\n`, `\0` 등 차단)
- 최종 URL 재검증 (리다이렉트 따라간 뒤 allowlist 벗어나면 결과 폐기)
- Chromium `--host-resolver-rules` 로 DNS 레벨에서도 allowlist 강제
- Chromium 공격 표면 축소 플래그 (`--disable-extensions`, `--disable-sync`, `--no-first-run` 등)
- 파라미터 clamp (`wait_seconds ≤ 15s`, `max_description_chars ≤ 20000`)
- 디버그 캡처 rotation (최근 50개) + HTML 2MB cap
- systemd 샌드박싱 (`NoNewPrivileges`, `ProtectSystem=strict`, `ProtectProc=invisible`, `CapabilityBoundingSet=` 빈값 등)

## 라즈베리파이 실배포

실배포용으로 아래 파일을 추가했습니다.

- `deploy/systemd/shopping-mcp.service`
- `deploy/cloudflared/config.example.yml`
- `scripts/install_cloudflared_pi.sh`
- `scripts/install_systemd_pi.sh`
- `scripts/run_quick_tunnel.sh`
- `docs/RASPBERRY_PI_CLOUDFLARE_DEPLOY.md`
- `docs/SECURITY.md` ← 운영 보안 가이드

실배포 순서는 대략 이렇습니다.

1. 앱 로컬 실행 확인 (`MCP_AUTH_TOKEN` 설정 + 로그에 `/mcp is OPEN` 경고 없는지)
2. `shopping-mcp.service` 등록
3. Cloudflare Tunnel (Named) 설치
4. **Cloudflare Access 정책 설정** (이메일 또는 서비스 토큰)
5. ChatGPT 커넥터에 `https://.../mcp` + `Authorization: Bearer <MCP_AUTH_TOKEN>` 등록

자세한 단계별 설명:

- [docs/RASPBERRY_PI_CLOUDFLARE_DEPLOY.md](docs/RASPBERRY_PI_CLOUDFLARE_DEPLOY.md)
- [docs/SECURITY.md](docs/SECURITY.md)

## 주의사항

- 이 프로젝트는 **범용 추출기 + 네이버 스마트스토어 어댑터** 구조입니다.
- 사이트마다 DOM 구조가 달라서 100% 만능은 아닙니다.
- `capture_product_page` 결과의 HTML/스크린샷을 보고 셀렉터를 보강하는 식으로 정확도를 올리는 것이 가장 빠릅니다.
- 로그인 필요 페이지, 강한 봇 차단, 캡차는 별도 대응이 필요합니다.
- `ALLOWED_PRODUCT_HOSTS` 환경변수로 허용 도메인을 확장할 수 있지만, **기본값을 전부 대체** 합니다. 네이버 + 추가 도메인을 원하면 네이버 도메인도 명시적으로 포함해야 합니다.

## 개발

```bash
# 테스트 실행
./.venv/Scripts/python.exe -m pytest tests/ -v     # Windows
.venv/bin/python -m pytest tests/ -v               # Linux / macOS
```

현재 테스트 52개 (보안 회귀 테스트 포함).
