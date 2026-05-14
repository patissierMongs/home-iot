use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
pub struct SemanticEvent {
    pub ts: DateTime<Utc>,
    pub domain: String,
    #[serde(rename = "type")]
    pub event_type: String,
    pub entity: String,
    pub source: String,
    pub source_entity: String,
    pub old_state: Option<String>,
    pub new_state: String,
    pub trusted: bool,
}
