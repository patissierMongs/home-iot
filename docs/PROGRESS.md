# 진행 기록

[English](PROGRESS.en.md) | **한국어**

## 최종 목표

집 안 기기(HA(Home Assistant) 연동 기기, 센서, PC)와 개인 생활 데이터(수면, 건강, 위치, PC 사용 기록)를 모두 로컬 서버에 모으고, 다음 세 가지를 하는 스마트홈 허브를 만드는 것입니다.

1. 정해진 상황은 결정론적 규칙으로 바로 처리합니다.
2. 애매한 상황은 로컬 LLM(Large Language Model, 대규모 언어 모델) 에이전트가 도구를 호출해 판단하고, 민감한 동작은 사용자 승인을 받습니다.
3. 에이전트가 집과 사용자에 대해 배운 내용을 YAML(YAML Ain't Markup Language) 지식 베이스에 쌓고, 모인 데이터를 대화형 분석과 대시보드로 보여 줍니다.

## 현재 구현 상태

2026-09-27에 코드를 직접 읽고 확인한 결과입니다. 상태는 구현됨, 부분 구현, 미구현 세 가지로 적습니다. 이 저장소에는 자동 테스트가 없습니다.

| 기능 | 상태 | 확인한 코드 위치 | 비고 |
|---|---|---|---|
| Docker Compose 스택 (HA, Mosquitto, InfluxDB, Grafana, Ollama, Telegraf) | 구현됨 | `stack/docker-compose.yml`, `stack/telegraf/telegraf.conf`, `stack/mosquitto/config/mosquitto.conf` | Mosquitto는 익명 접속을 허용하는 개발용 설정입니다. |
| HA REST(Representational State Transfer)와 WebSocket 클라이언트 | 구현됨 | `agent/src/home_iot/ha.py` | 상태 조회, 서비스 호출, 이벤트 스트림, 재접속 |
| 에이전트 이벤트 루프 (규칙 → LLM) | 구현됨 | `agent/src/home_iot/agent.py` | LLM으로 보내는 대상은 `binary_sensor.`, `person.`, `device_tracker.` 상태 변화입니다. |
| 결정론적 규칙 엔진 | 부분 구현 | `agent/src/home_iot/rules.py` | 엔진은 있지만 `DEFAULT_RULES`가 비어 있고, `Agent`도 규칙을 등록하지 않습니다. |
| Ollama 도구 호출 어댑터 | 구현됨 | `agent/src/home_iot/llm.py` | |
| 에이전트 도구 17개 | 구현됨 | `agent/src/home_iot/tools.py` (`TOOL_SCHEMAS`, `Tools`) | HA, InfluxDB, 수면, 활동, 장소, 지식 기록 7개, 승인 요청 |
| 장소 역지오코딩 (Nominatim) | 구현됨 | `agent/src/home_iot/tools.py` `_reverse_geocode` | |
| 사용자 승인 요청 | 부분 구현 | `agent/src/home_iot/tools.py` `request_approval` | 로그만 남기고 항상 자동 승인하는 스텁입니다. |
| YAML 지식 베이스 (집 구조, 누적 지식, 질문 대기열) | 구현됨 | `agent/config/*.example.yaml`, `tools.py`의 `get_home_context`, `record_*`, `answer_question` | 실제 파일은 `.gitignore` 대상입니다. |
| MCP(Model Context Protocol) 서버로 도구 공개 | 미구현 | `tools.py` 주석에만 계획이 있습니다. | |
| ActivityWatch 브리지 | 구현됨 | `agent/src/home_iot/bridges/activitywatch.py` | 에이전트 실행 시 함께 돕니다. |
| Qingping 공기질 브리지 | 부분 구현 | `agent/src/home_iot/bridges/qingping.py` | 반복 폴링 메서드(`run`)는 있지만 단독 실행(`main`)은 한 번만 폴링하고 끝납니다. 에이전트에는 연결되어 있지 않습니다. |
| Samsung Health 임포터 | 구현됨 | `agent/src/home_iot/importers/samsung_health.py`, `agent/scripts/import_samsung_health.py` | |
| Sleep as Android 임포터 | 구현됨 | `agent/src/home_iot/importers/sleep_as_android.py`, `agent/scripts/import_sleep_as_android.py` | |
| Google Takeout 임포터 (Fit, Chrome, 캘린더, 저장한 장소) | 구현됨 | `agent/scripts/import_google_takeout.py` | |
| Google 타임라인(`timeline_visit`, `timeline_gps`) 임포터 | 미구현 | 도구와 분석 코드는 이 측정값을 읽지만, 넣는 코드는 저장소에 없습니다. | |
| 통합 분석 엔진 | 구현됨 | `agent/src/home_iot/analytics.py`, `agent/scripts/refresh_analytics.py` | 결과를 `analytics_*` 측정값으로 기록합니다. |
| Grafana 대시보드 7종과 프로비저닝 | 구현됨 | `stack/grafana/dashboards/*.json`, `stack/grafana/provisioning/` | 실제 Grafana에서 띄워 보지는 못했습니다. |
| 주간 리뷰 (Anthropic API) | 구현됨 | `agent/scripts/weekly_review.py` | `--dry-run` 지원 |
| 분석 채팅 웹 UI(User Interface) | 구현됨 | `analyst-chat/app.py`, `analyst-chat/static/index.html` | 시각화 도구 7개. 스텁 LLM으로 실행해 화면을 확인했습니다. |
| Life Explorer HTML(HyperText Markup Language) 생성기 | 부분 구현 | `dashboards/life-explorer.py`, `dashboards/build_explorer_v3.py`, `dashboards/explorer_template.html` | 입력 JSON(JavaScript Object Notation)을 만드는 수집 스크립트가 없고, `explorer_template.html`을 채우는 코드도 없습니다. |
| 데스크톱 오디오 플레이어 (MQTT(Message Queuing Telemetry Transport) → TTS(Text-to-Speech)) | 구현됨 | `desktop-audio-player/audio_player.py`, `desktop-audio-player/start.ps1` | Windows 전용 |
| 초기 커스텀 MQTT 브리지 (Hue) | 구현됨 | `reference/` | 현재 쓰지 않는 참고용 코드입니다. |

## 작업 이력

`git log`에서 정리했습니다. 커밋에 저장된 시간대가 이미 +09:00이라 KST(Korea Standard Time, 한국 표준시)로 그대로 적습니다.

| 날짜 (KST) | 커밋 | 내용 |
|---|---|---|
| 2026-04-06 13:27 | 92843c0 | 첫 공개: Docker 스택, 에이전트, 분석 채팅 |
| 2026-04-06 13:42 | 3c6b41c | 분석 채팅이 LLM이 만든 JSON 대신 `create_chart` 도구를 쓰도록 수정 |
| 2026-04-06 16:37 | 2c73169 | 주간 리뷰 스크립트 추가 |
| 2026-04-06 21:06 | 7178dce | Google Takeout 임포터 추가 |
| 2026-04-06 21:22 | 8cc012f | 분석 채팅에 지도와 타임라인 시각화 추가 |
| 2026-04-06 21:50 ~ 22:31 | 263e9aa, 2dee77c, 8831d52, 2fe8fc1, c339b85 | 분석 채팅 프롬프트 개편, 시각화 6종, 시간대 수정 |
| 2026-04-06 22:36 | 3812bf8 | 위치 분석 도구 추가 (도구 17개) |
| 2026-04-06 22:41 | 2a6f0fb | 장소에 Nominatim 역지오코딩 추가 |
| 2026-04-07 19:33 | ca0241f | `CLAUDE.md`에 프로젝트 규칙 정리 |
| 2026-04-07 19:37 | 7b956b7 | 코드 리뷰에서 나온 5건 수정 |
| 2026-04-07 19:50 | 3f19539 | 간트 차트 시각화 추가 |
| 2026-04-07 20:31 ~ 21:09 | f8bed10, 62450c2, edede67 | Life Explorer 대시보드 1차, v3, ORBITAL 템플릿 |
| 2026-04-07 21:48 | abbcf9e | Qingping 클라우드 API(Application Programming Interface) → MQTT 브리지 추가 |
| 2026-04-07 21:57 | fb6ec62 | 통합 분석 엔진 추가 |
| 2026-04-07 22:01 | d5d7a27 | Grafana 통합 분석 대시보드와 자동 갱신 스크립트 추가 |
| 2026-05-13 16:10 | 66b0d6d | 로컬 가상환경 폴더를 `.gitignore`에 추가 |
| 2026-09-27 | 이번 작업 | 개인 정보 제거, README 한국어와 영어 분리, 스크린샷 추가, 진행 기록 작성 |
