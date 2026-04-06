# home-iot-agent

Home Assistant + Ollama + MQTT 기반 하이브리드 자동화 에이전트.

## 구조

```
src/home_iot/
├── config.py   환경변수 설정
├── ha.py       HA REST + WebSocket 클라이언트
├── tools.py    LLM 도구 정의 + 구현 (MCP 서버에서도 재사용)
├── rules.py    결정론적 규칙 엔진 (빠른 경로)
├── llm.py      Ollama tool-calling 어댑터
├── agent.py    이벤트 구독 + rule → LLM 파이프라인
└── main.py     엔트리포인트
```

## 흐름

```
HA 이벤트 → RuleEngine ─┬─ consume → 끝 (빠름)
                        └─ notable → LLM.chat(tools=...) → 도구 호출 → 최종 답변
```

## 설치

```bash
cd agent
cp .env.example .env  # HA_TOKEN 입력
uv sync
uv run home-iot-agent
```

## 확장 포인트

- `rules.py` — `DEFAULT_RULES`에 규칙 추가 (결정론적 자동화)
- `tools.py` — 새 도구 추가 시 `TOOL_SCHEMAS` + `Tools` 메서드 둘 다 수정
- `agent.py::_is_notable` — LLM이 깨어날 이벤트 조건 조정
- `agent.py::SYSTEM_PROMPT` — 에이전트 페르소나/원칙 수정
