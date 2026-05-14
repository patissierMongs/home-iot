use crate::ha::types::HaStateChangedEvent;
use crate::semantic::event::SemanticEvent;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SemanticEventMapper {
    rules: Vec<SemanticRule>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct SemanticRule {
    entity: String,
    source_entity: String,
    old_state: String,
    new_state: String,
    domain: String,
    event_type: String,
}

impl SemanticEventMapper {
    pub fn for_supplement_presence(
        entity: impl Into<String>,
        source_entity: impl Into<String>,
        taken_transition: (&str, &str),
    ) -> Self {
        let entity = entity.into();
        let source_entity = source_entity.into();
        Self {
            rules: vec![SemanticRule {
                entity,
                source_entity,
                old_state: taken_transition.0.to_string(),
                new_state: taken_transition.1.to_string(),
                domain: "supplement".to_string(),
                event_type: "taken".to_string(),
            }],
        }
    }

    pub fn map_state_changed(&self, event: &HaStateChangedEvent) -> Option<SemanticEvent> {
        let old_state = event.old_state.as_deref()?;
        let rule = self.rules.iter().find(|rule| {
            rule.source_entity == event.entity_id
                && rule.old_state == old_state
                && rule.new_state == event.new_state
        })?;

        Some(SemanticEvent {
            ts: event.time_fired,
            domain: rule.domain.clone(),
            event_type: rule.event_type.clone(),
            entity: rule.entity.clone(),
            source: "home_assistant".to_string(),
            source_entity: rule.source_entity.clone(),
            old_state: event.old_state.clone(),
            new_state: event.new_state.clone(),
            trusted: true,
        })
    }
}
