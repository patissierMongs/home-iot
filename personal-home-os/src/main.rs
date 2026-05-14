use std::env;

fn main() -> std::io::Result<()> {
    let addr = env::var("PERSONAL_HOME_OS_ADDR").unwrap_or_else(|_| "0.0.0.0:8080".to_string());
    personal_home_os::server::run(&addr)
}
