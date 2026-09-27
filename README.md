# home-iot

집 안 기기와 생활 데이터를 로컬에서 모으고, 규칙 엔진과 로컬 LLM(Large Language Model, 대규모 언어 모델) 에이전트로 자동화와 분석을 하는 스마트홈 허브입니다.

[English](README.en.md) | **한국어**

![분석 채팅 화면](docs/images/analyst-chat-answer.png)

*분석 채팅(`analyst-chat`) 화면입니다. 이 스크린샷은 저장소의 실제 웹 서버를 실행하고, Ollama 자리에 미리 정한 응답을 돌려주는 테스트용 스텁 서버를 붙여 찍었습니다. 수치는 모두 합성 예시 데이터입니다.*

![질문부터 답변까지의 흐름](docs/images/analyst-chat-flow.gif)

## 주요 기능

- **Docker Compose 스택**: HA(Home Assistant), Mosquitto MQTT(Message Queuing Telemetry Transport) 브로커, InfluxDB 2, Grafana, Ollama, Telegraf를 한 번에 띄웁니다.
- **하이브리드 에이전트** (`agent/`): HA 이벤트를 WebSocket으로 받아 먼저 규칙 엔진에 넘기고, 규칙이 처리하지 않은 문, 재실, 위치 센서 변화만 LLM에 보냅니다. LLM은 도구 호출로 기기를 조회하고 제어합니다.
- **17개 에이전트 도구** (`agent/src/home_iot/tools.py`): HA 조회와 서비스 호출, InfluxDB Flux 쿼리, 수면과 활동 통계, 방문 장소와 이동 경로 조회, 지식 기록 도구 7개, 승인 요청 도구가 있습니다.
- **공유 지식 베이스**: `agent/config/`의 YAML(YAML Ain't Markup Language) 파일 세 개(집 구조, 누적 지식, 질문 대기열)를 에이전트와 Claude 세션이 같이 읽고 씁니다.
- **분석 채팅** (`analyst-chat/`): 브라우저에서 한국어로 질문하면 LLM이 데이터를 조회하고 차트, 지도, 타임라인, 표, 요약 카드, 막대 순위, 간트 차트로 답합니다.
- **데이터 임포터** (`agent/scripts/`): Samsung Health 내보내기, Sleep as Android CSV(Comma-Separated Values), Google Takeout(Fit, Chrome 방문 기록, 캘린더, 저장한 장소)을 InfluxDB로 넣습니다.
- **브리지**: ActivityWatch의 창, 자리 비움, 브라우저 이벤트를 InfluxDB와 MQTT로 보내고(에이전트와 함께 실행), Qingping 공기질 측정기 클라우드 값을 MQTT로 보냅니다(단독 실행).
- **통합 분석 엔진** (`agent/src/home_iot/analytics.py`): 날짜별로 데이터를 맞춰 상관관계, 예측 변수, 이상치, 날짜 군집, 주중과 주말 비교, 추세를 계산하고 결과를 InfluxDB에 기록합니다.
- **Grafana 대시보드 7종** (`stack/grafana/dashboards/`): Home Overview, System Health, Desktop & Productivity, Sleep, Health & Activity, Correlations, Integrated Analytics.
- **주간 리뷰** (`agent/scripts/weekly_review.py`): 한 주 데이터를 모아 Anthropic API(Application Programming Interface)로 보내고 마크다운 보고서를 `agent/reports/`에 저장합니다.
- **데스크톱 오디오 플레이어** (`desktop-audio-player/`): Windows PC에서 MQTT 메시지를 받아 ElevenLabs TTS(Text-to-Speech, 음성 합성) 음성이나 mp3를 재생합니다.

## 사용 방법

WSL(Windows Subsystem for Linux)이나 Linux에서 Docker와 [uv](https://docs.astral.sh/uv/)를 쓰는 환경을 가정합니다. Ollama와 Telegraf 설정은 NVIDIA GPU(Graphics Processing Unit)를 예약하므로, GPU가 없으면 `stack/docker-compose.yml`의 `deploy` 항목을 지우고 실행합니다.

### 1. 스택 실행

```bash
cd stack
docker compose up -d
```

| 서비스 | 주소 | 용도 |
|---|---|---|
| Home Assistant | http://localhost:8123 | 기기 연동, 자동화 |
| Mosquitto | localhost:1883 (WebSocket 9001) | MQTT 브로커 |
| InfluxDB | http://localhost:8086 | 시계열 데이터베이스, 초기 계정 `admin` / `homeiot-admin` |
| Grafana | http://localhost:3000 | 대시보드, 초기 계정 `admin` / `admin` |
| Ollama | http://localhost:11434 | 로컬 LLM API |

위 계정과 InfluxDB 토큰(`homeiot-super-secret-token`)은 로컬 개발용 기본값입니다. 외부에 노출하기 전에 `docker-compose.yml`에서 바꿉니다. HA 설정 예시는 `stack/homeassistant/config.example/`에 있습니다.

LLM 모델을 받아 둡니다.

```bash
docker exec -it ollama ollama pull nemotron-cascade-2
```

### 2. 에이전트 실행

```bash
cd agent
cp .env.example .env            # HA_TOKEN에 HA 장기 액세스 토큰 입력
cp config/home_layout.example.yaml config/home_layout.yaml
cp config/home_knowledge.example.yaml config/home_knowledge.yaml
cp config/open_questions.example.yaml config/open_questions.yaml
uv sync
uv run home-iot-agent
```

`home_layout.yaml`에는 구역, 기기, 생활 패턴, 안전 경계를 직접 적습니다. 에이전트는 ActivityWatch(`http://localhost:5600`)도 함께 폴링합니다.

### 3. 분석 채팅 실행

에이전트와 같은 가상환경과 `.env`를 씁니다.

```bash
cd agent
uv run python ../analyst-chat/app.py
```

브라우저에서 http://localhost:8501 을 열고 예시 버튼을 누르거나 질문을 입력합니다.

### 4. 데이터 가져오기와 분석

```bash
cd agent
uv run python scripts/import_samsung_health.py [ZIP 또는 폴더 경로]
uv run python scripts/import_sleep_as_android.py [sleep-export.csv 경로]
uv run python scripts/import_google_takeout.py [Takeout 폴더 경로]
uv run python scripts/refresh_analytics.py          # 분석 결과를 InfluxDB에 기록
ANTHROPIC_API_KEY=... uv run python scripts/weekly_review.py [--dry-run]
```

경로를 생략하면 `HOME_IOT_DOWNLOADS` 환경 변수 폴더(기본값 `~/Downloads`)에서 찾습니다.

### 5. 선택 구성 요소

- Qingping 브리지: `QINGPING_APP_KEY`, `QINGPING_APP_SECRET`을 설정하고 `uv run python -m home_iot.bridges.qingping`을 실행하면 한 번 폴링해 MQTT로 보냅니다.
- 데스크톱 오디오 플레이어: [desktop-audio-player/README.md](desktop-audio-player/README.md)를 따릅니다. `HOME_IOT_MQTT_HOST`에 WSL 쪽 IP(Internet Protocol) 주소를 넣습니다.
- Life Explorer (`dashboards/`): `/tmp/explorer_data.json`을 읽어 지도형 HTML(HyperText Markup Language) 대시보드를 만듭니다. 이 JSON(JavaScript Object Notation)을 만드는 수집 스크립트는 저장소에 없습니다. 출력 경로는 `LIFE_EXPLORER_OUT`으로 바꿀 수 있습니다.

Grafana의 Desktop & Productivity 대시보드는 HASS.Agent 기기 이름이 `lab_pc`라고 가정합니다(`sensor.lab_pc_cpuload_2` 등). 기기 이름이 다르면 대시보드 쿼리의 엔티티 이름을 바꿉니다.

## 기술 스택

| 구분 | 사용 기술 |
|---|---|
| 언어 | Python 3.12 이상 (에이전트), JavaScript (웹 화면), PowerShell (Windows 실행 스크립트) |
| 에이전트 라이브러리 (`uv.lock`) | httpx 0.28.1, websockets 16.0, aiomqtt 2.5.1, pydantic 2.12.5, pydantic-settings 2.13.1, structlog 25.5.0, influxdb-client 1.50.0, PyYAML 6.0.3 |
| 분석 | pandas 3.0.2, NumPy 2.4.4, SciPy 1.17.1, scikit-learn 1.8.0 |
| 웹 서버 | FastAPI 0.135.3, Uvicorn 0.43.0 |
| 웹 화면 | Plotly.js 2.35.2, Leaflet 1.9.4, Leaflet.heat 0.2.0 |
| 인프라 (Docker 이미지) | home-assistant `stable`, eclipse-mosquitto `2`, influxdb `2`, grafana `latest`, ollama `latest`, telegraf `latest` |
| LLM | Ollama + Nemotron Cascade 2 (기본 모델), bge-m3 (임베딩 모델 설정값), Anthropic API (주간 리뷰) |
| 오디오 플레이어 | paho-mqtt 2.0 이상, httpx, miniaudio, ElevenLabs API |
| 패키지 관리 | uv, hatchling |

## 문서

- [진행 기록](docs/PROGRESS.md): 최종 목표, 기능별 구현 상태, 작업 이력
- [에이전트 구조](agent/README.md)
- [데스크톱 오디오 플레이어](desktop-audio-player/README.md)
- `reference/`: 초기에 만든 MQTT 브리지 코드입니다. 현재는 쓰지 않고 참고용으로만 둡니다.
- `CLAUDE.md`: Claude 세션용 작업 지침입니다.
