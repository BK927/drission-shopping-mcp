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
python -m shopping_mcp.asgi
```

기본 엔드포인트:
- MCP: `http://127.0.0.1:8000/mcp`
- Health: `http://127.0.0.1:8000/healthz`

## 라즈베리파이 실배포

실배포용으로 아래 파일을 추가했습니다.

- `deploy/systemd/shopping-mcp.service`
- `deploy/cloudflared/config.example.yml`
- `scripts/install_cloudflared_pi.sh`
- `scripts/install_systemd_pi.sh`
- `scripts/run_quick_tunnel.sh`
- `docs/RASPBERRY_PI_CLOUDFLARE_DEPLOY.md`

실배포 순서는 대략 이렇습니다.

1. 앱 로컬 실행 확인
2. `shopping-mcp.service` 등록
3. Cloudflare Tunnel 설치
4. Quick Tunnel 또는 Named Tunnel 연결
5. ChatGPT에 `https://.../mcp` 등록

자세한 단계별 설명은 아래 문서를 보세요.

- [docs/RASPBERRY_PI_CLOUDFLARE_DEPLOY.md](docs/RASPBERRY_PI_CLOUDFLARE_DEPLOY.md)

## 주의사항

- 이 프로젝트는 **범용 추출기 + 네이버 스마트스토어 어댑터** 구조입니다.
- 사이트마다 DOM 구조가 달라서 100% 만능은 아닙니다.
- `capture_product_page` 결과의 HTML/스크린샷을 보고 셀렉터를 보강하는 식으로 정확도를 올리는 것이 가장 빠릅니다.
- 로그인 필요 페이지, 강한 봇 차단, 캡차는 별도 대응이 필요합니다.
