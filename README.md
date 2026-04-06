# home-iot

로컬 스마트홈 AI 허브. 결정론적 룰 + AI 에이전트 하이브리드 아키텍처.

## 구조

```
home-iot/
├── stack/          Docker Compose 스택 (HA, Mosquitto, InfluxDB, Grafana, Ollama)
├── agent/          커스텀 AI 에이전트 레이어 (Python, 추후 구현)
└── reference/      초기 커스텀 MQTT bridge 코드 (학습용, 사용 안 함)
```

## 실행

```bash
cd stack
docker compose up -d
```

### 엔드포인트

| 서비스 | URL | 용도 |
|---|---|---|
| Home Assistant | http://localhost:8123 | 메인 UI, 자동화, 대시보드 |
| Mosquitto | localhost:1883 | MQTT 브로커 |
| InfluxDB | http://localhost:8086 | 시계열 DB (admin/homeiot-admin) |
| Grafana | http://localhost:3000 | 고급 대시보드 (admin/admin) |
| Ollama | http://localhost:11434 | 로컬 LLM API |
