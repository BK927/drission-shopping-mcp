# Raspberry Pi + systemd + Cloudflare Tunnel 배포 가이드

이 문서는 **라즈베리파이에서 Drission Shopping MCP를 systemd로 상시 구동**하고, **Cloudflare Tunnel로 HTTPS 공개 주소를 붙이는 방법**을 정리합니다.

권장 방식은 두 갈래입니다.

- **빠른 테스트**: Quick Tunnel (도메인 불필요, 주소 임시)
- **실사용**: Named Tunnel / remote-managed tunnel (도메인 필요, 주소 고정)

## 0. 전제

- Raspberry Pi OS 64-bit / Debian 계열
- Python 3.10+
- Chromium 설치 가능
- Cloudflare 계정
- 실사용이라면 Cloudflare에 연결된 도메인 1개

Cloudflare는 Tunnel이 공인 IP 없이도 동작하며, `cloudflared`가 **outbound-only** 연결을 만든다고 설명합니다. Raspberry Pi 같은 소형 장치에도 배포 가능하다고 공식 문서에 적혀 있습니다. citeturn118281search3turn118281search5

## 1. 앱 설치

```bash
cd ~
unzip drission-shopping-mcp-pi.zip
cd drission-shopping-mcp-pi

bash scripts/install_pi.sh
cp .env.example .env
nano .env
```

`.env` 예시:

```env
NAVER_CLIENT_ID=YOUR_NAVER_CLIENT_ID
NAVER_CLIENT_SECRET=YOUR_NAVER_CLIENT_SECRET
FASTMCP_HOST=127.0.0.1
FASTMCP_PORT=8000
MCP_TRANSPORT=streamable-http
DP_HEADLESS=true
DP_NO_SANDBOX=true
DP_BROWSER_PATH=/usr/bin/chromium
DP_USER_DATA_DIR=/home/pi/.cache/drission-shopping-mcp
DP_PAGE_TIMEOUT=20
DEBUG_CAPTURE_DIR=/home/pi/drission-shopping-mcp-pi/debug_captures

# Bearer token required on /mcp (strongly recommended).
MCP_AUTH_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

반드시 `.env`의 권한을 600으로 제한하세요:

```bash
chmod 600 .env
```

## 2. 로컬 실행 확인

```bash
source .venv/bin/activate
python -m shopping_mcp.asgi
```

별도 터미널에서:

```bash
curl http://127.0.0.1:8000/healthz
```

정상이면 `{"status":"ok"}` 가 나옵니다.

MCP 엔드포인트는 `http://127.0.0.1:8000/mcp` 입니다. OpenAI의 ChatGPT 연결 문서도 원격 커넥터 URL을 **공개 HTTPS `/mcp` 엔드포인트**로 넣으라고 안내합니다. citeturn118281search0

## 3. systemd 등록

앱이 문제없이 뜨면 서비스로 등록합니다.

```bash
bash scripts/install_systemd_pi.sh ~/drission-shopping-mcp-pi
```

확인:

```bash
systemctl status shopping-mcp --no-pager
curl http://127.0.0.1:8000/healthz
```

## 4. Cloudflare Tunnel 설치

Cloudflare 공식 설치 절차대로 apt 저장소를 등록하고 `cloudflared`를 설치합니다. 이 저장소 등록 절차는 Debian/Ubuntu용 공식 문서와 같습니다. citeturn118281search4

```bash
bash scripts/install_cloudflared_pi.sh
```

## 5-A. 가장 쉬운 테스트: Quick Tunnel

도메인이 아직 없거나, 먼저 외부 접속만 시험하고 싶을 때:

```bash
bash scripts/run_quick_tunnel.sh 8000
```

Quick Tunnel은 **설정 파일이 필요 없고**, 임시 공개 URL을 바로 줍니다. 다만 주소가 영구적이지 않으므로 ChatGPT 실사용용 커넥터 주소로는 적합하지 않습니다. Cloudflare 문서도 Quick tunnels는 configuration file이 필요 없다고 밝힙니다. citeturn118281search2

이때 나온 `https://xxxx.trycloudflare.com` 주소의 MCP 엔드포인트는:

```text
https://xxxx.trycloudflare.com/mcp
```

## 5-B. 실사용 권장: Named Tunnel (remote-managed)

가장 손쉬운 실사용형은 **Cloudflare 대시보드에서 tunnel을 만들고 token으로 Pi에 연결**하는 방식입니다.

1. Cloudflare 대시보드에서 **Networks → Connectors → Cloudflare Tunnels** 로 이동
2. **Create a tunnel** 선택
3. Connector type으로 **Cloudflared** 선택
4. 터널 이름 입력 후 생성
5. **Published application route** 추가
   - hostname: 예) `mcp.example.com`
   - service: `http://127.0.0.1:8000`
6. 대시보드가 보여주는 설치 명령에서 **token** 값을 복사
7. Pi에서 아래 실행

```bash
sudo cloudflared service install <TUNNEL_TOKEN>
sudo systemctl status cloudflared --no-pager
```

Cloudflare 공식 문서도 remote-managed tunnel 생성 뒤, 서버에서는 `sudo cloudflared service install <TUNNEL_TOKEN>` 로 서비스 설치를 안내합니다. citeturn914708search8turn914708search10

연결 확인:

```bash
curl https://mcp.example.com/healthz
```

ChatGPT에는 이 URL을 넣습니다:

```text
https://mcp.example.com/mcp
```

## 5-C. CLI 선호 시: locally-managed tunnel

대시보드보다 CLI를 선호하면 locally-managed tunnel도 가능합니다. 공식 절차는 로그인 → tunnel 생성 → config.yml 작성 → 서비스 설치 순서입니다. citeturn118281search4turn914708search0

```bash
cloudflared tunnel login
cloudflared tunnel create shopping-mcp
sudo mkdir -p /etc/cloudflared
sudo cp deploy/cloudflared/config.example.yml /etc/cloudflared/config.yml
sudo nano /etc/cloudflared/config.yml
sudo cloudflared service install
sudo systemctl restart cloudflared
sudo systemctl status cloudflared --no-pager
```

`/etc/cloudflared/config.yml` 예시는 프로젝트에 포함된 `deploy/cloudflared/config.example.yml`을 쓰면 됩니다.

## 6. ChatGPT 연결

OpenAI 문서 기준으로 ChatGPT에서 커넥터를 만들 때는 **public `/mcp` endpoint** 를 넣어야 합니다. citeturn118281search0

예시:

```text
Connector URL: https://mcp.example.com/mcp
```

## 6.5. 보안 체크리스트 (공개 엔드포인트용)

공개 HTTPS로 띄우는 순간 `/mcp`는 누구나 호출을 시도할 수 있다고 가정하세요. 아래 세 가지는 **반드시** 적용하는 것을 권장합니다.

1. **`MCP_AUTH_TOKEN` 설정.** 빈 값이면 앱이 경고 로그를 내고 `/mcp`를 무인증으로 엽니다. 토큰이 있으면 `Authorization: Bearer <token>` 없는 요청은 401. ChatGPT 커넥터에도 동일 토큰을 등록하세요.
2. **Cloudflare Access (Zero Trust) 정책.** Named Tunnel의 hostname에 Access 애플리케이션을 붙여 "특정 이메일 / 서비스 토큰만 허용" 규칙을 걸면, Bearer 토큰 누출 시에도 한 겹 더 막힙니다. Cloudflare 대시보드 → Zero Trust → Access → Applications.
3. **허용 호스트 제한.** 기본값은 네이버 쇼핑 도메인만. 다른 쇼핑몰을 추가해야 하면 `ALLOWED_PRODUCT_HOSTS`에 명시적으로 넣으세요. 값이 있으면 **기본값을 전부 대체**합니다 (실수로 전체 열기 방지).

추가로 권장:

- `DP_NO_SANDBOX=true` 는 **기본 활성** 상태. Chromium 렌더러 샌드박스를 끄므로 악성 페이지가 Pi를 장악할 수 있는 벡터입니다. MCP_AUTH_TOKEN과 URL allowlist가 그 앞을 막고 있지만, 장기적으로는 사용자를 분리하거나 `DP_NO_SANDBOX=false` 로 돌릴 수 있는 환경을 고민해 주세요.
- `deploy/systemd/shopping-mcp.service`에는 `NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`, `ProtectHome=read-only` 등 하드닝이 걸려 있습니다. 커스텀 경로를 쓴다면 `ReadWritePaths=`를 맞춰 수정하세요.

## 7. 운영 팁

- `shopping-mcp` 는 `127.0.0.1:8000` 에만 바인딩하고, 외부 공개는 cloudflared에 맡기는 편이 안전합니다.
- DrissionPage는 라즈베리파이에서 무화면/headless로 돌리는 편이 안정적입니다.
- 상세 추출은 무겁기 때문에 검색 단계에서는 상세 페이지를 열지 말고, **필요한 상품만 상세 추출**하도록 쓰는 편이 좋습니다.
- 로그 확인:

```bash
journalctl -u shopping-mcp -f
journalctl -u cloudflared -f
```

Cloudflare는 cloudflared를 **서비스로 실행하는 것을 권장**하며, Linux에서는 기본적으로 `cloudflared.service`를 사용한다고 안내합니다. citeturn914708search1turn914708search2

## 8. 자주 막히는 지점

### 1) 로컬은 되는데 외부 접속이 안 됨
- `shopping-mcp` 서비스가 127.0.0.1:8000 에서 뜨는지 확인
- `curl http://127.0.0.1:8000/healthz` 먼저 확인
- `cloudflared` 서비스 상태 확인

### 2) ChatGPT에서 connector 생성이 실패함
- URL이 `https://.../mcp` 인지 확인
- `/healthz` 는 열리는데 `/mcp` 는 안 되면 앱 마운트 경로를 다시 확인
- Quick Tunnel 주소는 자주 바뀌므로 실사용에는 named tunnel을 권장

### 3) 상세 추출이 약함
- `wait_seconds` 값을 3~5초로 올림
- `save_debug=true` 로 HTML/스크린샷 저장 후 파서 보강

## 9. 최소 점검 순서

1. `curl http://127.0.0.1:8000/healthz`
2. `systemctl status shopping-mcp`
3. `systemctl status cloudflared`
4. `curl https://mcp.example.com/healthz`
5. ChatGPT에 `https://mcp.example.com/mcp` 연결

여기까지 통과하면 라즈베리파이 홈 서버 MCP로는 꽤 안정적인 축에 들어간다.
