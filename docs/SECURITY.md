# Security Guide

이 문서는 drission-shopping-mcp를 **공개 HTTPS 엔드포인트로 띄울 때** 의 위협 모델, 기본 방어 구조, 필수 운영 체크리스트를 정리합니다.

- 대상 배포 시나리오: Raspberry Pi + 홈 공유기 + Cloudflare Tunnel + ChatGPT MCP 커넥터
- 기본 전제: `/mcp` 는 인터넷에서 누구나 호출을 "시도" 할 수 있다고 가정

> **한 줄 요약**: 아래 [필수 운영 체크리스트](#필수-운영-체크리스트) 만 지키면, 개인 홈서버 수준에서는 실질적으로 안전합니다. 체크리스트를 어긴 상태는 "공격자가 뚫는 게 귀찮지 않은" 상태라고 봐야 합니다.

---

## 1. 위협 모델

### 1.1. 누가 공격하나

- **대량 자동 스캐너 (가장 흔함)**. CT 로그에 올라온 서브도메인을 수집해 무작위로 HTTP 요청을 뿌립니다. LLM으로 합성한 페이로드를 섞기도 합니다. 이들은 "쉽게 뚫리는 대상"을 찾는 구조라, 두 겹 이상만 막혀 있으면 다음 타겟으로 넘어갑니다.
- **타깃형 공격자**. 이 MCP에 특정 이익이 있어서 시간을 쓰는 공격자. 본 문서 범위 밖입니다 (국가/조직 단위 방어는 홈 Pi로는 불가능).

### 1.2. 노리는 것

| 노림 | 어떻게 | 이득 |
|---|---|---|
| 임의 URL 접근 (SSRF) | `get_product_detail(url=...)` 악용 | 내부망 정찰 / 공유기 관리페이지 / 클라우드 메타데이터 |
| 호스트 RCE | `--no-sandbox` Chromium 렌더러 취약점 + 공격자 제어 페이지 | Pi 계정 장악 |
| 네이버 API 쿼터 소진 | 무인증 `search_naver_products` 반복 호출 | 계정 제재 유발 / DoS |
| 디스크 소진 | `capture_product_page` 반복 호출 | SD 카드 fill → 서비스 다운 |
| 토큰/시크릿 유출 | `/proc/<pid>/environ` 등 | 재사용 공격 |

### 1.3. 현재 설정에서 실질적인 공격 경로

1. **최전선 뚫기**: `/mcp` 에 도달 → **Cloudflare Access + Bearer 토큰** 을 먼저 넘어야 함
2. **도달 후 SSRF 시도**: URL allowlist + parser-differential 차단으로 외부 URL 거부
3. **허용된 사이트가 침해되어 내부 IP로 리다이렉트**: 최종 URL 재검증 + Chromium DNS 규칙으로 차단
4. **Chromium 0-day 익스플로잇**: `--no-sandbox` 상태라 가능. `apt upgrade`로 최신 버전 유지하는 것이 마지막 방어선
5. **RCE 성공 시 블라스트 반경**: systemd 하드닝으로 파일/네임스페이스/capability 축소

---

## 2. 방어 구조 (defense in depth)

```
┌─────────────────────────────────────────────────────────────┐
│ 인터넷                                                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ [1] Cloudflare Tunnel  — 공유기에 포트 안 엶 (outbound-only) │
│ [2] Cloudflare Access  — 토큰/이메일 zero-trust 정책          │
│ [3] Bearer Token       — hmac.compare_digest, isascii 가드   │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ [4] URL allowlist + canonicalization                        │
│     - 스킴 http(s), 사설/루프백/링크로컬 IP 차단             │
│     - \  \t  \n  \r  \0  (space) 포함 URL 거부 (파서 차이)    │
│     - urlparse 결과로 URL 재조립 → Chromium에도 동일 전달    │
│ [5] 파라미터 clamp (wait_seconds ≤ 15, description ≤ 20KB)   │
│ [6] 최종 URL 재검증 (page.url이 allowlist 밖이면 결과 폐기)   │
│ [7] Chromium --host-resolver-rules (allowlist 외 DNS 차단)   │
│ [8] Chromium 공격표면 축소 플래그 (extensions/sync/background) │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ [9] systemd hardening                                       │
│     NoNewPrivileges / ProtectSystem=strict / ProtectHome    │
│     PrivateTmp / PrivateDevices / ProtectProc=invisible     │
│     RestrictNamespaces / RestrictAddressFamilies            │
│     CapabilityBoundingSet= (빈값) / LimitNOFILE / TasksMax   │
│ [10] 디버그 캡처 rotation (50개) + HTML 2MB cap              │
└─────────────────────────────────────────────────────────────┘
```

이 중 **어느 한 겹이라도 실수로 빠지면** 그 겹이 담당하던 공격 벡터가 열립니다. 예: `MCP_AUTH_TOKEN` 을 깜빡하면 [3]이 사라지지만 앱은 자동으로 `127.0.0.1`에만 바인딩하도록 fail-closed. Cloudflare Access [2]는 설정하지 않으면 아예 없어짐 → 반드시 대시보드에서 명시적으로 걸어야 합니다.

---

## 3. 필수 운영 체크리스트

**배포 당일 반드시 점검.** 10분이면 끝납니다.

### 3.1. 토큰 생성 및 권한 잠금

```bash
# Pi에서
cd ~/drission-shopping-mcp
cp .env.example .env    # 아직 안 했다면
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# 출력된 값을 .env 의 MCP_AUTH_TOKEN= 에 붙여넣기
nano .env
chmod 600 .env          # 필수 — 같은 유저의 다른 프로세스가 읽지 못하게
```

동일 토큰을 **ChatGPT MCP 커넥터의 Authorization 헤더**에도 `Bearer <토큰>` 형태로 입력.

### 3.2. Cloudflare Access 정책 걸기 (대시보드 5분 작업)

1. Cloudflare 대시보드 → **Zero Trust** → **Access** → **Applications**
2. **Add an application** → **Self-hosted** 선택
3. Application domain: `mcp.example.com` (본인 도메인)
4. Policy 추가 → 예시:
   - **Include**: Emails → 본인 이메일만
   - 또는 **Service Token** → ChatGPT에 등록할 헤더 쌍 발급
5. 저장 후 `curl https://mcp.example.com/healthz` 로 정책이 걸렸는지 확인

### 3.3. systemd 서비스 등록

```bash
bash scripts/install_systemd_pi.sh ~/drission-shopping-mcp-pi
systemctl status shopping-mcp --no-pager
```

`Active: active (running)` 확인. 실패 시 `journalctl -u shopping-mcp -e`.

### 3.4. 스타트업 로그에서 경고가 없는지 확인

```bash
journalctl -u shopping-mcp -n 40
```

정상 출력에는 다음이 있어야 합니다:
- `Chromium found at /usr/bin/chromium`
- `Shopping MCP ready — host=127.0.0.1 port=8000 browser=yes max_browser_slots=1`

아래 경고가 보이면 **배포 중단** 하고 수정:
- `MCP_AUTH_TOKEN is not set — /mcp is OPEN` → 토큰 잊음
- `NAVER_CLIENT_ID and NAVER_CLIENT_SECRET must both be set` → API 키 잊음

### 3.5. `/healthz` 는 공개, `/mcp` 는 401 확인

```bash
curl -i https://mcp.example.com/healthz        # -> 200 {"status":"ok"}
curl -i https://mcp.example.com/mcp/           # -> 401 unauthorized
curl -i -H "Authorization: Bearer $TOKEN" \
     https://mcp.example.com/mcp/              # -> 200 (or MCP-specific response)
```

Cloudflare Access 가 먼저 걸려 있으면 401 대신 Access 인증 페이지가 반환되는 것이 정상.

---

## 4. 주기적 유지보수 (월간 10분)

보안은 "설치할 때 한 번" 이 아니라 "주기적으로 확인하는 것" 입니다.

| 주기 | 작업 | 명령 |
|---|---|---|
| 주 1회 | 로그에서 이상 징후 확인 | `journalctl -u shopping-mcp --since "7 days ago" \| grep -i "warning\|error\|blocked"` |
| 월 1회 | Pi/Chromium 업데이트 | `sudo apt update && sudo apt upgrade -y` |
| 월 1회 | Python 의존성 업데이트 검토 | `uv lock --upgrade` → 변경사항 확인 후 `uv sync --frozen` |
| 월 1회 | 실제로 동작하는지 확인 | `bash scripts/run_quick_tunnel.sh 8000` 로 테스트 |
| 분기 1회 | MCP_AUTH_TOKEN 회전 | 아래 "토큰 회전" 섹션 |
| 분기 1회 | Cloudflare Access 정책 재검토 | 불필요한 이메일/서비스토큰 정리 |

### 4.1. 토큰 회전 절차

```bash
# 1) 새 토큰 생성
NEW_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# 2) ChatGPT 커넥터 설정 화면에서 새 토큰으로 교체

# 3) Pi의 .env 수정
nano ~/drission-shopping-mcp/.env   # MCP_AUTH_TOKEN=새 토큰

# 4) 서비스 재시작
sudo systemctl restart shopping-mcp

# 5) 새 토큰으로 동작 확인
curl -H "Authorization: Bearer $NEW_TOKEN" \
     https://mcp.example.com/mcp/
```

단계 2→3 사이에는 ChatGPT가 401을 받습니다. 짧은 시간이니 크게 문제 없지만 신경 쓰이면 2분 안에 끝내면 됩니다.

---

## 5. 알려진 잔존 위험 (감수하는 것)

모든 공격을 막을 수는 없습니다. 다음은 "개인 Pi 홈서버" 시나리오에서 수용하는 잔존 위험입니다.

### 5.1. `DP_NO_SANDBOX=true`

Chromium 렌더러 샌드박스를 끈 상태입니다. 완전한 방어는 "비특권 사용자로 분리 + 샌드박스 on" 인데 Pi OS 기본 환경에서 세팅 난이도가 높습니다.

**현재 완화책**:
- URL allowlist 로 방문 가능 도메인을 네이버 쇼핑으로 제한
- `--host-resolver-rules` 로 Chromium 자체가 allowlist 밖 DNS 를 resolve 하지 않음
- 최종 URL 재검증으로 redirect 우회 차단
- systemd hardening 으로 RCE 블라스트 반경 축소

**남는 위험**: Naver 페이지 자체가 Chromium 0-day 를 심어서 보낸다면 방어 어렵습니다. `apt upgrade` 로 Chromium 을 최신 상태로 유지하는 것이 유일한 대책.

### 5.2. 앱 레벨 rate limit 없음

토큰을 가진 공격자(또는 ChatGPT 인스턴스 버그)가 초당 수십 요청을 보내면 앱은 그대로 처리합니다. 네이버 API 쿼터가 소진될 수 있습니다.

**현재 완화책**: Cloudflare Rate Limiting 규칙을 Pro 플랜에서 추가 가능.

### 5.3. DNS rebinding

Allowlist 는 hostname 기반입니다. 허용된 도메인이 짧은 TTL 로 내부 IP 를 응답하면 **이론상** 우회 가능합니다.

**현재 완화책**: `--host-resolver-rules` 로 Chromium 자체가 MAP/EXCLUDE 규칙을 따르도록 강제. 그러나 완전 방어는 아니므로 Cloudflare Access 가 그 앞에 있어야 안전.

### 5.4. 의존성 취약점 (supply chain)

`uv.lock` 을 커밋해 두었고 `uv sync --frozen` 으로 설치하므로 재현성은 보장됩니다. 다만 업스트림 패키지(starlette, mcp, DrissionPage, httpx 등) 에 취약점이 발견되면 별도 조치 필요.

**현재 완화책**: 월 1회 `uv lock --upgrade` 로 검토.

---

## 6. 사고 대응

### 6.1. 로그 어디서 보나

```bash
# 앱 로그
journalctl -u shopping-mcp -f

# 최근 차단 이벤트만
journalctl -u shopping-mcp | grep -i "blocked\|skipped\|aborted"

# Cloudflared 로그
journalctl -u cloudflared -f
```

### 6.2. "뭔가 이상하다" 싶을 때

```bash
# 1) 즉시 토큰 무효화 (사실상 서비스 중단)
sudo systemctl stop shopping-mcp

# 2) 로그 확보
journalctl -u shopping-mcp --since "24 hours ago" > ~/incident.log

# 3) debug_captures/ 디렉토리에 의심스러운 게 있는지 확인
ls -lat ~/drission-shopping-mcp-pi/debug_captures/ | head

# 4) 원인 파악 후 토큰 회전 (4.1) → 서비스 재기동
sudo systemctl start shopping-mcp
```

### 6.3. Chromium 이상 징후

`Cached ChromiumPage looks dead — rebuilding` 이 로그에 여러 번 반복되면 네이버가 봇 감지로 막고 있을 수 있습니다. 이건 보안 사고가 아니라 운영 이슈입니다. `DP_USER_DATA_DIR` 를 지우고 재시작:

```bash
sudo systemctl stop shopping-mcp
rm -rf /home/pi/.cache/drission-shopping-mcp
sudo systemctl start shopping-mcp
```

---

## 7. 위협 모델을 다시 세워야 할 때

이 문서의 방어 설계는 "개인 Pi + ChatGPT 1인 사용" 을 전제로 합니다. 다음 시나리오로 바뀌면 **이 문서만으로 부족합니다**:

- 여러 사용자 / 팀 단위 사용 → 사용자별 토큰 발급 + audit log
- Naver 스마트스토어 이외의 사이트 추가 (`ALLOWED_PRODUCT_HOSTS` 확장) → 해당 사이트의 콘텐츠 보안 모델을 별도 검토
- 로그인 세션이 필요한 페이지 추출 → 쿠키/세션 저장 구조 재설계 (현재 `DP_USER_DATA_DIR` 는 네이버 봇 감지 우회 목적의 익명 profile)
- 상용/유료 서비스로 공개 → 앱 레벨 rate limit, WAF, 모니터링, incident response 체계 필요

이 경계를 넘는다고 생각되면 보안 전문가에게 재검토를 받으세요.

---

## 부록 A. 방어층과 소스 파일 매핑

| 방어 | 파일 | 핵심 함수 |
|---|---|---|
| Bearer 토큰 검증 | `shopping_mcp/asgi.py` | `_is_request_authorized`, `BearerAuthMiddleware` |
| Fail-closed bind | `shopping_mcp/asgi.py` | `_resolve_bind_host` |
| URL canonicalize / allowlist | `shopping_mcp/utils.py` | `canonicalize_product_url`, `is_allowed_product_url` |
| 파라미터 clamp | `shopping_mcp/server.py` | `_clamp_wait_seconds`, `_clamp_max_chars` |
| 최종 URL 재검증 | `shopping_mcp/detail_extractor.py` | `extract` 진입부 |
| Chromium 하드닝 | `shopping_mcp/browser.py` | `_hardening_args` |
| 디버그 경로 sanitize | `shopping_mcp/utils.py` | `safe_host_for_dirname` |
| 캡처 rotation + 2MB cap | `shopping_mcp/detail_extractor.py` | `_save_debug`, `MAX_DEBUG_CAPTURES`, `MAX_DEBUG_HTML_BYTES` |
| systemd 하드닝 | `deploy/systemd/shopping-mcp.service` | (선언적) |

## 부록 B. 환경변수 빠른 참조

| 변수 | 설명 | 미설정 시 |
|---|---|---|
| `MCP_AUTH_TOKEN` | `/mcp` Bearer 토큰 | 기동은 되지만 자동으로 `127.0.0.1` 바인딩 + 경고 로그 |
| `ALLOWED_PRODUCT_HOSTS` | 허용 호스트 콤마 구분 | 네이버 쇼핑 5개 도메인 기본값 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 네이버 쇼핑 API 크레덴셜 | 기동 실패 (`sys.exit(1)`) |
| `FASTMCP_HOST` | 바인딩 호스트 | `127.0.0.1` |
| `FASTMCP_PORT` | 바인딩 포트 | `8000` |
| `DP_HEADLESS` | Chromium headless 여부 | `true` |
| `DP_NO_SANDBOX` | 렌더러 샌드박스 off | `true` (Pi 기본) |
| `DP_BROWSER_PATH` | Chromium 실행 파일 경로 | `shutil.which` 자동 탐색 |
| `DP_USER_DATA_DIR` | Chromium 프로필 경로 | 없음 (세션 유지 안 됨) |
| `DEBUG_CAPTURE_DIR` | 디버그 캡처 저장 위치 | `./debug_captures` |
| `LOG_LEVEL` | Python logging 레벨 | `INFO` |
