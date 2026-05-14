use chrono::{TimeZone, Utc};
use personal_home_os::ha::types::HaStateChangedEvent;
use personal_home_os::semantic::mapper::SemanticEventMapper;

#[test]
fn semantic_mapper_maps_magnesium_presence_removed_to_taken_event() {
    let mapper = SemanticEventMapper::for_supplement_presence(
        "magnesium",
        "binary_sensor.supplement_magnesium_present",
        ("on", "off"),
    );
    let event = HaStateChangedEvent {
        entity_id: "binary_sensor.supplement_magnesium_present".to_string(),
        old_state: Some("on".to_string()),
        new_state: "off".to_string(),
        time_fired: Utc.with_ymd_and_hms(2026, 5, 13, 22, 11, 4).unwrap(),
    };

    let semantic_event = mapper
        .map_state_changed(&event)
        .expect("expected semantic event");

    assert_eq!(semantic_event.domain, "supplement");
    assert_eq!(semantic_event.event_type, "taken");
    assert_eq!(semantic_event.entity, "magnesium");
    assert_eq!(
        semantic_event.source_entity,
        "binary_sensor.supplement_magnesium_present"
    );
    assert_eq!(semantic_event.old_state.as_deref(), Some("on"));
    assert_eq!(semantic_event.new_state, "off");
    assert!(semantic_event.trusted);
    assert_eq!(semantic_event.ts, event.time_fired);
}

#[test]
fn semantic_mapper_ignores_non_matching_transition() {
    let mapper = SemanticEventMapper::for_supplement_presence(
        "magnesium",
        "binary_sensor.supplement_magnesium_present",
        ("on", "off"),
    );
    let event = HaStateChangedEvent {
        entity_id: "binary_sensor.supplement_magnesium_present".to_string(),
        old_state: Some("off".to_string()),
        new_state: "on".to_string(),
        time_fired: Utc.with_ymd_and_hms(2026, 5, 13, 22, 11, 4).unwrap(),
    };

    assert!(mapper.map_state_changed(&event).is_none());
}
