use serde::{Deserialize, Serialize};

use crate::briefing::compose_night_briefing;
use crate::routines::night::plan_night_routine;
use crate::semantic::event::SemanticEvent;

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct NowContext {
    pub date: String,
    pub time: String,
    pub home_assistant: String,
    pub health: HealthContext,
    pub environment: EnvironmentContext,
    pub computer: ComputerContext,
    pub supplements: SupplementContext,
    pub routines: RoutineContext,
    pub events_today: Vec<SemanticEvent>,
    pub recommended_actions: Vec<RecommendedAction>,
    pub briefing: Briefing,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct HealthContext {
    pub body_battery: i64,
    pub sleep_score: i64,
    pub stress: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct EnvironmentContext {
    pub bedroom_co2: i64,
    pub bedroom_temperature: f64,
    pub bedroom_light_brightness: i64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
pub struct ComputerContext {
    pub current_mode: String,
    pub screen_after_22_minutes: i64,
    pub in_meeting: bool,
    pub focus_block_minutes: i64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
pub struct SupplementContext {
    pub magnesium: String,
    pub omega3: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
pub struct RoutineContext {
    pub night_briefing_done: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
pub struct RecommendedAction {
    pub id: String,
    pub title: String,
    pub priority: String,
    pub message: String,
    pub reason: Vec<String>,
    pub safety: ActionSafety,
    pub ha_service: Option<HaServiceCall>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
pub struct ActionSafety {
    pub auto_executable: bool,
    pub requires_approval: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
pub struct HaServiceCall {
    pub domain: String,
    pub service: String,
    pub entity_id: String,
    pub brightness_pct: Option<i64>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
pub struct Briefing {
    pub text: String,
    pub source_facts: Vec<String>,
    pub actions_included: Vec<String>,
    pub spoken: bool,
    pub last_briefing_time: Option<String>,
}

impl NowContext {
    pub fn demo() -> Self {
        let event = SemanticEvent {
            ts: chrono::DateTime::parse_from_rfc3339("2026-05-14T22:11:04+09:00")
                .unwrap()
                .with_timezone(&chrono::Utc),
            domain: "supplement".to_string(),
            event_type: "taken".to_string(),
            entity: "magnesium".to_string(),
            source: "ha".to_string(),
            source_entity: "binary_sensor.supplement_magnesium_present".to_string(),
            old_state: Some("on".to_string()),
            new_state: "off".to_string(),
            trusted: true,
        };

        Self {
            date: "2026-05-14".to_string(),
            time: "2026-05-14T22:18:00+09:00".to_string(),
            home_assistant: "not_connected_yet".to_string(),
            health: HealthContext {
                body_battery: 31,
                sleep_score: 72,
                stress: "elevated".to_string(),
            },
            environment: EnvironmentContext {
                bedroom_co2: 1120,
                bedroom_temperature: 22.8,
                bedroom_light_brightness: 65,
            },
            computer: ComputerContext {
                current_mode: "video".to_string(),
                screen_after_22_minutes: 38,
                in_meeting: false,
                focus_block_minutes: 0,
            },
            supplements: SupplementContext {
                magnesium: "missing".to_string(),
                omega3: "taken".to_string(),
            },
            routines: RoutineContext {
                night_briefing_done: false,
            },
            events_today: vec![event],
            recommended_actions: Vec::new(),
            briefing: Briefing {
                text: String::new(),
                source_facts: Vec::new(),
                actions_included: Vec::new(),
                spoken: false,
                last_briefing_time: None,
            },
        }
    }
}

pub fn build_demo_now_context() -> NowContext {
    let mut context = NowContext::demo();
    context.recommended_actions = plan_night_routine(&context);
    context.briefing = compose_night_briefing(&context, &context.recommended_actions);
    context
}
