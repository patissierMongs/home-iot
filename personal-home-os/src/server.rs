use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};

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
    match path {
        "/" => html_response(dashboard_html()),
        "/health" => json_response(r#"{"status":"ok","service":"personal-home-os"}"#.to_string()),
        "/api/status" => json_response(status_json()),
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

fn status_json() -> String {
    r#"{
  "service": "personal-home-os",
  "status": "bootstrapped",
  "runtime": "rust",
  "home_assistant": "not_connected_yet",
  "implemented_modules": [
    "ha.types",
    "semantic.event",
    "semantic.mapper",
    "server.dashboard"
  ],
  "implemented_flow": [
    "HA state_changed event model",
    "supplement presence on->off semantic mapping",
    "minimal web dashboard"
  ],
  "next_modules": [
    "event ledger JSONL writer",
    "context builder now.json",
    "night routine planner",
    "briefing composer",
    "safe action executor"
  ]
}"#
    .to_string()
}

fn dashboard_html() -> String {
    r#"<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Personal Home OS</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #090b10;
      --panel: #121722;
      --panel-2: #171f2e;
      --text: #eef4ff;
      --muted: #97a5ba;
      --accent: #7dd3fc;
      --ok: #86efac;
      --warn: #fde68a;
      --line: #263244;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top left, #132036 0, var(--bg) 38rem);
      color: var(--text);
    }
    main { max-width: 1080px; margin: 0 auto; padding: 40px 24px; }
    header { display: flex; justify-content: space-between; gap: 24px; align-items: start; margin-bottom: 28px; }
    h1 { margin: 0 0 8px; font-size: clamp(32px, 6vw, 64px); letter-spacing: -0.05em; }
    h2 { margin: 0 0 14px; font-size: 18px; }
    p { color: var(--muted); line-height: 1.6; }
    .badge { display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 999px; background: rgba(18, 23, 34, .72); color: var(--ok); font-weight: 650; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 20px var(--ok); }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
    .card { border: 1px solid var(--line); background: linear-gradient(180deg, var(--panel), var(--panel-2)); border-radius: 22px; padding: 20px; box-shadow: 0 16px 50px rgba(0,0,0,.22); }
    .wide { grid-column: span 2; }
    ul { margin: 0; padding-left: 20px; color: var(--muted); line-height: 1.8; }
    code { color: var(--accent); background: #0b1220; padding: 2px 6px; border-radius: 8px; }
    .flow { display: flex; flex-wrap: wrap; gap: 10px; }
    .pill { border: 1px solid var(--line); border-radius: 14px; padding: 10px 12px; color: var(--muted); background: #0c111b; }
    .metric { font-size: 30px; font-weight: 800; letter-spacing: -0.03em; }
    .muted { color: var(--muted); }
    a { color: var(--accent); }
    @media (max-width: 820px) { .grid { grid-template-columns: 1fr; } .wide { grid-column: span 1; } header { display: block; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Personal Home OS</h1>
        <p>Home Assistant를 source of truth로 두고, Rust core가 의미 이벤트·컨텍스트·루틴·브리핑을 담당하는 새 구현입니다.</p>
      </div>
      <div class="badge"><span class="dot"></span>Rust core running</div>
    </header>

    <section class="grid">
      <article class="card">
        <h2>Runtime</h2>
        <div class="metric">Rust</div>
        <p>새 디렉터리 <code>personal-home-os/</code>에서 기존 Python agent와 분리되어 실행 중.</p>
      </article>
      <article class="card">
        <h2>HA 연결</h2>
        <div class="metric" style="color: var(--warn)">대기</div>
        <p>아직 실제 Home Assistant REST/WebSocket 연결은 붙이지 않았음.</p>
      </article>
      <article class="card">
        <h2>Health</h2>
        <div class="metric" style="color: var(--ok)">OK</div>
        <p><a href="/health">/health</a> · <a href="/api/status">/api/status</a></p>
      </article>

      <article class="card wide">
        <h2>현재 구현된 흐름</h2>
        <div class="flow">
          <div class="pill">HA state_changed model</div>
          <div class="pill">binary_sensor on→off</div>
          <div class="pill">supplement.taken.magnesium</div>
          <div class="pill">semantic mapper tests</div>
          <div class="pill">web dashboard shell</div>
        </div>
      </article>

      <article class="card">
        <h2>다음 구현</h2>
        <ul>
          <li>JSONL event ledger</li>
          <li>now.json context builder</li>
          <li>night routine planner</li>
          <li>Korean briefing composer</li>
          <li>safe HA action executor</li>
        </ul>
      </article>

      <article class="card wide">
        <h2>설계 원칙</h2>
        <ul>
          <li>Home Assistant가 센서/하드웨어 판단의 source of truth.</li>
          <li>Rust core는 HA entity state/event를 trusted fact로 소비.</li>
          <li>LLM/voice/action은 나중에 safety policy 뒤에 붙임.</li>
        </ul>
      </article>
    </section>
  </main>
</body>
</html>
"#
    .to_string()
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
        assert!(response.body.contains("Rust core running"));
    }

    #[test]
    fn status_endpoint_returns_runtime_json() {
        let response = route("/api/status");

        assert_eq!(response.status, "200 OK");
        assert_eq!(response.content_type, "application/json; charset=utf-8");
        assert!(response.body.contains(r#""runtime": "rust""#));
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
