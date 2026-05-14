use chrono::{TimeZone, Utc};
use personal_home_os::action::{ActionDecision, SafetyPolicy};
use personal_home_os::briefing::compose_night_briefing;
use personal_home_os::context::{NowContext, build_demo_now_context};
use personal_home_os::routines::night::plan_night_routine;
use personal_home_os::semantic::event::SemanticEvent;
use personal_home_os::semantic::ledger::EventLedger;
use tempfile::tempdir;

#[test]
fn ledger_appends_and_reads_daily_semantic_events() {
    let dir = tempdir().unwrap();
    let ledger = EventLedger::new(dir.path());
    let event = SemanticEvent {
        ts: Utc.with_ymd_and_hms(2026, 5, 14, 22, 11, 4).unwrap(),
        domain: "supplement".to_string(),
        event_type: "taken".to_string(),
        entity: "magnesium".to_string(),
        source: "ha".to_string(),
        source_entity: "binary_sensor.supplement_magnesium_present".to_string(),
        old_state: Some("on".to_string()),
        new_state: "off".to_string(),
        trusted: true,
    };

    ledger.append(&event).unwrap();
    std::fs::write(
        dir.path().join("2026-05-14.jsonl"),
        format!("{}\nnot json\n", serde_json::to_string(&event).unwrap()),
    )
    .unwrap();

    let read = ledger
        .read_date(
            Utc.with_ymd_and_hms(2026, 5, 14, 0, 0, 0)
                .unwrap()
                .date_naive(),
        )
        .unwrap();

    assert_eq!(read.events.len(), 1);
    assert_eq!(read.malformed_lines, 1);
    assert_eq!(read.events[0].domain, "supplement");
}

#[test]
fn demo_context_contains_briefing_actions_and_events() {
    let context = build_demo_now_context();

    assert_eq!(context.home_assistant, "not_connected_yet");
    assert!(context.briefing.text.contains("마그네슘"));
    assert!(
        context
            .recommended_actions
            .iter()
            .any(|a| a.id == "ventilate_bedroom")
    );
    assert!(context.events_today.iter().any(|e| e.entity == "magnesium"));
}

#[test]
fn night_routine_recommends_core_actions_from_context() {
    let mut context = NowContext::demo();
    context.supplements.magnesium = "missing".to_string();
    context.environment.bedroom_co2 = 1120;
    context.routines.night_briefing_done = false;
    context.computer.in_meeting = false;

    let actions = plan_night_routine(&context);
    let ids: Vec<&str> = actions.iter().map(|a| a.id.as_str()).collect();

    assert!(ids.contains(&"take_magnesium"));
    assert!(ids.contains(&"ventilate_bedroom"));
    assert!(ids.contains(&"dim_lights_for_bedtime"));
}

#[test]
fn briefing_composes_short_korean_summary_from_actions() {
    let context = build_demo_now_context();
    let briefing = compose_night_briefing(&context, &context.recommended_actions);

    assert!(briefing.text.contains("침실 CO2"));
    assert!(briefing.text.contains("마그네슘"));
    assert!(
        briefing
            .source_facts
            .iter()
            .any(|fact| fact.contains("1120ppm"))
    );
}

#[test]
fn safety_policy_allows_only_allowlisted_low_risk_actions() {
    let context = build_demo_now_context();
    let policy = SafetyPolicy::new(vec!["dim_lights_for_bedtime".to_string()]);

    let dim = context
        .recommended_actions
        .iter()
        .find(|a| a.id == "dim_lights_for_bedtime")
        .unwrap();
    let vent = context
        .recommended_actions
        .iter()
        .find(|a| a.id == "ventilate_bedroom")
        .unwrap();

    assert_eq!(policy.decide(dim), ActionDecision::Allowed);
    assert_eq!(policy.decide(vent), ActionDecision::RequiresApproval);
}
