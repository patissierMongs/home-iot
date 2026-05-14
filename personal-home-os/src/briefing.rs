use crate::context::{Briefing, NowContext, RecommendedAction};

pub fn compose_night_briefing(context: &NowContext, actions: &[RecommendedAction]) -> Briefing {
    if actions.is_empty() {
        return Briefing {
            text: "지금은 바로 챙길 루틴이 없어요.".to_string(),
            source_facts: Vec::new(),
            actions_included: Vec::new(),
            spoken: false,
            last_briefing_time: None,
        };
    }

    let has_co2 = actions.iter().any(|a| a.id == "ventilate_bedroom");
    let has_magnesium = actions.iter().any(|a| a.id == "take_magnesium");
    let has_light = actions.iter().any(|a| a.id == "dim_lights_for_bedtime");

    let mut sentences = Vec::new();
    if has_co2 && has_magnesium {
        sentences.push("침실 CO2가 조금 높고, 마그네슘은 아직 안 챙기셨어요.".to_string());
    } else if has_co2 {
        sentences.push("침실 CO2가 조금 높아서 10분 환기를 추천해요.".to_string());
    } else if has_magnesium {
        sentences.push("마그네슘은 아직 안 챙기셨어요.".to_string());
    }
    if has_light {
        sentences.push("자기 전 조명은 낮춰두는 게 좋아요.".to_string());
    }

    let mut source_facts = Vec::new();
    source_facts.push(format!(
        "bedroom_co2={}ppm",
        context.environment.bedroom_co2
    ));
    source_facts.push(format!("magnesium={}", context.supplements.magnesium));
    source_facts.push(format!("body_battery={}", context.health.body_battery));

    Briefing {
        text: sentences.join(" "),
        source_facts,
        actions_included: actions.iter().map(|a| a.id.clone()).collect(),
        spoken: false,
        last_briefing_time: None,
    }
}
