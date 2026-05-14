use chrono::NaiveDate;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};

use crate::semantic::event::SemanticEvent;

#[derive(Clone, Debug)]
pub struct EventLedger {
    dir: PathBuf,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LedgerReadResult {
    pub events: Vec<SemanticEvent>,
    pub malformed_lines: usize,
}

impl EventLedger {
    pub fn new(dir: impl AsRef<Path>) -> Self {
        Self {
            dir: dir.as_ref().to_path_buf(),
        }
    }

    pub fn append(&self, event: &SemanticEvent) -> anyhow::Result<()> {
        fs::create_dir_all(&self.dir)?;
        let path = self.path_for_date(event.ts.date_naive());
        let mut file = OpenOptions::new().create(true).append(true).open(path)?;
        writeln!(file, "{}", serde_json::to_string(event)?)?;
        Ok(())
    }

    pub fn read_date(&self, date: NaiveDate) -> anyhow::Result<LedgerReadResult> {
        let path = self.path_for_date(date);
        if !path.exists() {
            return Ok(LedgerReadResult {
                events: Vec::new(),
                malformed_lines: 0,
            });
        }

        let file = fs::File::open(path)?;
        let reader = BufReader::new(file);
        let mut events = Vec::new();
        let mut malformed_lines = 0;

        for line in reader.lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }
            match serde_json::from_str::<SemanticEvent>(&line) {
                Ok(event) => events.push(event),
                Err(_) => malformed_lines += 1,
            }
        }

        Ok(LedgerReadResult {
            events,
            malformed_lines,
        })
    }

    fn path_for_date(&self, date: NaiveDate) -> PathBuf {
        self.dir.join(format!("{date}.jsonl"))
    }
}
