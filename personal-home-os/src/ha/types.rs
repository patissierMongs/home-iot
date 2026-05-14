use chrono::{DateTime, Utc};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct HaStateChangedEvent {
    pub entity_id: String,
    pub old_state: Option<String>,
    pub new_state: String,
    pub time_fired: DateTime<Utc>,
}
