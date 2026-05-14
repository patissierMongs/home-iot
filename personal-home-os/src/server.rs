use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};

use crate::context::{NowContext, RecommendedAction, build_demo_now_context};

pub fn run(addr: &str) -> std::io::Result<()> {
    let listener = TcpListener::bind(addr)?;
    println!("personal-home-os listening on http://{addr}");

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                if let Err(err) = handle_connection(stream) {
                    eprintln!("connection handling error: {err}");
                }
            }
            Err(err) => eprintln!("connection error: {err}"),
        }
    }

    Ok(())
}

fn handle_connection(mut stream: TcpStream) -> std::io::Result<()> {
    let mut reader = BufReader::new(stream.try_clone()?);
    let mut request_line = Vec::new();
    reader.read_until(b'\n', &mut request_line)?;

    let request_line = String::from_utf8_lossy(&request_line);
    let path = request_line.split_whitespace().nth(1).unwrap_or("/");
    let response = route(path);

    write!(
        stream,
        "HTTP/1.1 {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        response.status,
        response.content_type,
        response.body.len(),
        response.body
    )?;
    stream.flush()
}

struct Response {
    status: &'static str,
    content_type: &'static str,
    body: String,
}

fn route(path: &str) -> Response {
    let context = build_demo_now_context();
    let clean_path = path.split('?').next().unwrap_or(path);
    match clean_path {
        "/" => html_response(dashboard_html(&context)),
        "/events" => html_response(events_html(&context)),
        "/routines" => html_response(routines_html(&context)),
        "/home" => html_response(home_html(&context)),
        "/insights" => html_response(insights_html(&context)),
        "/settings" => html_response(settings_html(&context)),
        "/health" => json_response(r#"{"status":"ok","service":"personal-home-os"}"#.to_string()),
        "/api/status" => json_response(status_json(&context)),
        "/api/now" => json_response(serde_json::to_string_pretty(&context).unwrap()),
        "/api/events" => {
            json_response(serde_json::to_string_pretty(&context.events_today).unwrap())
        }
        _ => Response {
            status: "404 Not Found",
            content_type: "text/plain; charset=utf-8",
            body: "not found\n".to_string(),
        },
    }
}

fn html_response(body: String) -> Response {
    Response {
        status: "200 OK",
        content_type: "text/html; charset=utf-8",
        body,
    }
}

fn json_response(body: String) -> Response {
    Response {
        status: "200 OK",
        content_type: "application/json; charset=utf-8",
        body: format!("{body}\n"),
    }
}

fn status_json(context: &NowContext) -> String {
    serde_json::json!({
        "service": "personal-home-os",
        "status": "running",
        "runtime": "rust",
        "home_assistant": context.home_assistant,
        "version": env!("CARGO_PKG_VERSION"),
        "implemented_modules": [
            "ha.types",
            "semantic.event",
            "semantic.mapper",
            "semantic.ledger",
            "context",
            "routines.night",
            "briefing",
            "action.policy",
            "server.dashboard"
        ]
    })
    .to_string()
}

fn page(title: &str, active: &str, body: String) -> String {
    format!(
        r#"<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Personal Home OS</title>
<style>
:root {{ color-scheme: dark; --bg:#070a10; --panel:#111827; --panel2:#172033; --text:#eef4ff; --muted:#98a7bd; --accent:#7dd3fc; --ok:#86efac; --warn:#fde68a; --line:#283548; --bad:#fca5a5; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: radial-gradient(circle at top left, #172747 0, var(--bg) 42rem); color:var(--text); }}
main {{ max-width:1180px; margin:0 auto; padding:32px 20px 56px; }}
header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:20px; }}
h1 {{ margin:0 0 8px; font-size:clamp(34px, 5vw, 66px); letter-spacing:-.055em; }}
h2 {{ margin:0 0 14px; font-size:18px; }}
p {{ color:var(--muted); line-height:1.62; }}
a {{ color:var(--accent); text-decoration:none; }}
nav {{ display:flex; gap:8px; flex-wrap:wrap; margin:18px 0 24px; }}
nav a {{ padding:9px 12px; border:1px solid var(--line); border-radius:999px; color:var(--muted); background:#0d1320; }}
nav a.active {{ color:var(--text); border-color:var(--accent); background:#0c2030; }}
.grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }}
.card {{ border:1px solid var(--line); border-radius:24px; background:linear-gradient(180deg,var(--panel),var(--panel2)); padding:20px; box-shadow:0 16px 52px rgba(0,0,0,.24); }}
.wide {{ grid-column:span 2; }} .full {{ grid-column:1/-1; }}
.badge {{ display:inline-flex; gap:8px; align-items:center; border:1px solid var(--line); border-radius:999px; padding:8px 12px; color:var(--ok); background:#0d1722; font-weight:700; }}
.dot {{ width:8px; height:8px; border-radius:50%; background:var(--ok); box-shadow:0 0 18px var(--ok); }}
.metric {{ font-size:34px; font-weight:850; letter-spacing:-.04em; }}
.muted {{ color:var(--muted); }}
.action {{ display:grid; gap:10px; padding:16px; border:1px solid var(--line); background:#0b1220; border-radius:18px; margin:10px 0; }}
.action-top {{ display:flex; justify-content:space-between; gap:12px; }}
.priority {{ color:var(--warn); font-weight:800; }}
.reasons {{ display:flex; gap:8px; flex-wrap:wrap; }}
.pill {{ border:1px solid var(--line); border-radius:999px; padding:7px 10px; background:#0a101a; color:var(--muted); font-size:13px; }}
.buttons {{ display:flex; gap:8px; flex-wrap:wrap; }}
button {{ border:1px solid var(--line); border-radius:12px; padding:9px 12px; color:var(--text); background:#111b2b; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ text-align:left; border-bottom:1px solid var(--line); padding:12px 8px; color:var(--muted); }} th {{ color:var(--text); }}
@media (max-width:850px) {{ header {{ display:block; }} .grid {{ grid-template-columns:1fr; }} .wide {{ grid-column:span 1; }} }}
</style>
</head>
<body><main>
<header><div><h1>Personal Home OS</h1><p>Home Assistant를 source of truth로 두는 Rust 기반 개인 홈/건강 에이전트.</p></div><div class="badge"><span class="dot"></span>Rust core running</div></header>
<nav>{nav}</nav>
{body}
</main></body></html>"#,
        title = title,
        nav = nav(active),
        body = body
    )
}

fn nav(active: &str) -> String {
    let items = [
        ("/", "Now"),
        ("/routines", "Routines"),
        ("/events", "Events"),
        ("/home", "Home"),
        ("/insights", "Insights"),
        ("/settings", "Settings"),
    ];
    items
        .iter()
        .map(|(href, label)| {
            let class = if *label == active {
                " class=\"active\""
            } else {
                ""
            };
            format!("<a href=\"{href}\"{class}>{label}</a>")
        })
        .collect::<Vec<_>>()
        .join("")
}

fn dashboard_html(context: &NowContext) -> String {
    page(
        "Now",
        "Now",
        format!(
            r#"<section class="grid">
<article class="card full"><h2>Current Briefing</h2><div class="metric">오늘 밤 브리핑</div><p>{briefing}</p><div class="reasons">{facts}</div></article>
<article class="card wide"><h2>Recommended Actions</h2>{actions}</article>
<article class="card"><h2>Health / Energy</h2><div class="metric">{body_battery}</div><p>Body Battery · Sleep Score {sleep_score} · stress {stress}</p></article>
<article class="card"><h2>Home Environment</h2><div class="metric">{co2} ppm</div><p>침실 CO2 · {temp}℃ · 조명 {light}%</p></article>
<article class="card"><h2>Supplements</h2><div class="metric">Mg {mg}</div><p>Omega3 {omega3}</p></article>
<article class="card full"><h2>Recent Semantic Events</h2>{events}</article>
</section>"#,
            briefing = context.briefing.text,
            facts = context
                .briefing
                .source_facts
                .iter()
                .map(|f| format!("<span class=\"pill\">{f}</span>"))
                .collect::<Vec<_>>()
                .join(""),
            actions = actions_html(&context.recommended_actions),
            body_battery = context.health.body_battery,
            sleep_score = context.health.sleep_score,
            stress = context.health.stress,
            co2 = context.environment.bedroom_co2,
            temp = context.environment.bedroom_temperature,
            light = context.environment.bedroom_light_brightness,
            mg = context.supplements.magnesium,
            omega3 = context.supplements.omega3,
            events = events_table(context),
        ),
    )
}

fn actions_html(actions: &[RecommendedAction]) -> String {
    if actions.is_empty() {
        return "<p>지금은 추천할 action이 없어요.</p>".to_string();
    }
    actions.iter().map(|action| {
        format!(
            r#"<div class="action"><div class="action-top"><strong>{title}</strong><span class="priority">{priority}</span></div><p>{message}</p><div class="reasons">{reasons}</div><div class="buttons"><button>실행</button><button>10분 뒤</button><button>오늘 숨김</button><button>왜?</button></div></div>"#,
            title = action.title,
            priority = action.priority,
            message = action.message,
            reasons = action.reason.iter().map(|r| format!("<span class=\"pill\">{r}</span>")).collect::<Vec<_>>().join(""),
        )
    }).collect::<Vec<_>>().join("")
}

fn events_table(context: &NowContext) -> String {
    let rows = context
        .events_today
        .iter()
        .map(|event| {
            format!(
                "<tr><td>{}</td><td>{}.{}.{}</td><td>{}</td><td>{}</td></tr>",
                event.ts.format("%H:%M"),
                event.domain,
                event.event_type,
                event.entity,
                if event.trusted {
                    "trusted"
                } else {
                    "untrusted"
                },
                event.source_entity
            )
        })
        .collect::<Vec<_>>()
        .join("");
    format!(
        "<table><thead><tr><th>Time</th><th>Event</th><th>Trust</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>"
    )
}

fn events_html(context: &NowContext) -> String {
    page(
        "Events",
        "Events",
        format!(
            "<section class=\"grid\"><article class=\"card full\"><h2>Semantic Events</h2><p>JSONL ledger 기반으로 표시될 이벤트 히스토리입니다.</p>{}</article></section>",
            events_table(context)
        ),
    )
}

fn routines_html(context: &NowContext) -> String {
    page(
        "Routines",
        "Routines",
        format!(
            r#"<section class="grid"><article class="card wide"><h2>Night Routine</h2><ul><li>Magnesium: {mg}</li><li>Bedroom CO2: {co2} ppm</li><li>Lights: {light}%</li><li>Computer mode: {mode}</li><li>Briefing done: {done}</li></ul></article><article class="card"><h2>Actions</h2>{actions}</article></section>"#,
            mg = context.supplements.magnesium,
            co2 = context.environment.bedroom_co2,
            light = context.environment.bedroom_light_brightness,
            mode = context.computer.current_mode,
            done = context.routines.night_briefing_done,
            actions = actions_html(&context.recommended_actions)
        ),
    )
}

fn home_html(context: &NowContext) -> String {
    page(
        "Home",
        "Home",
        format!(
            r#"<section class="grid"><article class="card"><h2>Environment</h2><div class="metric">{co2} ppm</div><p>침실 CO2</p></article><article class="card"><h2>Temperature</h2><div class="metric">{temp}℃</div><p>침실 온도</p></article><article class="card"><h2>Computer</h2><div class="metric">{mode}</div><p>after 22:00 screen {screen} min</p></article></section>"#,
            co2 = context.environment.bedroom_co2,
            temp = context.environment.bedroom_temperature,
            mode = context.computer.current_mode,
            screen = context.computer.screen_after_22_minutes
        ),
    )
}

fn insights_html(context: &NowContext) -> String {
    page(
        "Insights",
        "Insights",
        format!(
            r#"<section class="grid"><article class="card full"><h2>Insights</h2><p>장기 패턴 화면은 ledger/context가 누적되면 실제 분석으로 바뀝니다.</p><div class="reasons"><span class="pill">Magnesium: {mg}</span><span class="pill">CO2 before sleep: {co2}ppm</span><span class="pill">Body Battery: {bb}</span></div></article></section>"#,
            mg = context.supplements.magnesium,
            co2 = context.environment.bedroom_co2,
            bb = context.health.body_battery
        ),
    )
}

fn settings_html(context: &NowContext) -> String {
    page(
        "Settings",
        "Settings",
        format!(
            r#"<section class="grid"><article class="card"><h2>HA Connection</h2><div class="metric">{ha}</div><p>HA_BASE_URL / HA_TOKEN 연결 전입니다.</p></article><article class="card"><h2>Runtime Paths</h2><p><code>data/events/YYYY-MM-DD.jsonl</code></p><p><code>data/context/now.json</code></p></article><article class="card"><h2>Safety</h2><p>Low-risk allowlist policy enabled. Hidden automation disabled.</p></article></section>"#,
            ha = context.home_assistant
        ),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::{TcpListener, TcpStream};
    use std::thread;

    #[test]
    fn root_endpoint_returns_dashboard_html() {
        let response = route("/");

        assert_eq!(response.status, "200 OK");
        assert_eq!(response.content_type, "text/html; charset=utf-8");
        assert!(response.body.contains("Personal Home OS"));
        assert!(response.body.contains("Current Briefing"));
        assert!(response.body.contains("Recommended Actions"));
        assert!(response.body.contains("침실 CO2"));
    }

    #[test]
    fn now_api_returns_context_json() {
        let response = route("/api/now");

        assert_eq!(response.status, "200 OK");
        assert!(response.body.contains(r#""recommended_actions""#));
        assert!(response.body.contains(r#""briefing""#));
    }

    #[test]
    fn events_page_returns_semantic_event_table() {
        let response = route("/events");

        assert_eq!(response.status, "200 OK");
        assert!(response.body.contains("Semantic Events"));
        assert!(response.body.contains("supplement.taken.magnesium"));
    }

    #[test]
    fn status_endpoint_returns_runtime_json() {
        let response = route("/api/status");

        assert_eq!(response.status, "200 OK");
        assert_eq!(response.content_type, "application/json; charset=utf-8");
        assert!(response.body.contains(r#""runtime":"rust""#));
        assert!(response.body.contains("semantic.mapper"));
    }

    #[test]
    fn invalid_utf8_request_does_not_crash_server() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();

        thread::spawn(move || {
            let (stream, _) = listener.accept().unwrap();
            handle_connection(stream).unwrap();
        });

        let mut stream = TcpStream::connect(addr).unwrap();
        stream
            .write_all(b"GET /\xff HTTP/1.1\r\nHost: localhost\r\n\r\n")
            .unwrap();

        let mut response = Vec::new();
        stream.read_to_end(&mut response).unwrap();

        assert!(String::from_utf8_lossy(&response).starts_with("HTTP/1.1"));
    }

    #[test]
    fn health_endpoint_returns_ok_json() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();

        thread::spawn(move || {
            let (stream, _) = listener.accept().unwrap();
            handle_connection(stream).unwrap();
        });

        let mut stream = TcpStream::connect(addr).unwrap();
        stream
            .write_all(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
            .unwrap();

        let mut response = String::new();
        stream.read_to_string(&mut response).unwrap();

        assert!(response.starts_with("HTTP/1.1 200 OK"));
        assert!(response.contains(r#"{"status":"ok","service":"personal-home-os"}"#));
    }
}
