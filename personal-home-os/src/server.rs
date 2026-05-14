use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};

pub fn run(addr: &str) -> std::io::Result<()> {
    let listener = TcpListener::bind(addr)?;
    println!("personal-home-os listening on http://{addr}");

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => handle_connection(stream)?,
            Err(err) => eprintln!("connection error: {err}"),
        }
    }

    Ok(())
}

fn handle_connection(mut stream: TcpStream) -> std::io::Result<()> {
    let mut reader = BufReader::new(stream.try_clone()?);
    let mut request_line = String::new();
    reader.read_line(&mut request_line)?;

    let path = request_line.split_whitespace().nth(1).unwrap_or("/");
    let (status, content_type, body) = match path {
        "/" => (
            "200 OK",
            "text/plain; charset=utf-8",
            "personal-home-os rust core is running\nGET /health\n",
        ),
        "/health" => (
            "200 OK",
            "application/json; charset=utf-8",
            r#"{"status":"ok","service":"personal-home-os"}
"#,
        ),
        _ => ("404 Not Found", "text/plain; charset=utf-8", "not found\n"),
    };

    write!(
        stream,
        "HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    )?;
    stream.flush()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::{TcpListener, TcpStream};
    use std::thread;

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
