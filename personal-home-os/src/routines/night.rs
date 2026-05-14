use crate::context::{ActionSafety, HaServiceCall, NowContext, RecommendedAction};

pub fn plan_night_routine(context: &NowContext) -> Vec<RecommendedAction> {
    if context.routines.night_briefing_done || context.computer.in_meeting || is_deep_focus(context)
    {
        return Vec::new();
    }

    let mut actions = Vec::new();

    if context.supplements.magnesium == "missing" {
        actions.push(RecommendedAction {
            id: "take_magnesium".to_string(),
            title: "마그네슘 챙기기".to_string(),
            priority: "medium".to_string(),
            message: "마그네슘은 아직 안 챙기셨어요.".to_string(),
            reason: vec!["오늘 magnesium taken 이벤트 없음".to_string()],
            safety: ActionSafety {
                auto_executable: false,
                requires_approval: false,
            },
            ha_service: None,
        });
    }

    if context.environment.bedroom_co2 >= 1000 {
        actions.push(RecommendedAction {
            id: "ventilate_bedroom".to_string(),
            title: "침실 10분 환기".to_string(),
            priority: "medium".to_string(),
            message: "침실 CO2가 높아서 10분 환기를 추천해요.".to_string(),
            reason: vec![
                format!("bedroom_co2={}ppm", context.environment.bedroom_co2),
                "취침 시간대".to_string(),
                "회의 중 아님".to_string(),
            ],
            safety: ActionSafety {
                auto_executable: false,
                requires_approval: true,
            },
            ha_service: None,
        });
    }

    if context.environment.bedroom_light_brightness > 30 {
        actions.push(RecommendedAction {
            id: "dim_lights_for_bedtime".to_string(),
            title: "침실 조명 낮추기".to_string(),
            priority: "low".to_string(),
            message: "취침 준비를 위해 침실 조명을 낮춰둘 수 있어요.".to_string(),
            reason: vec![
                format!(
                    "bedroom_light_brightness={}pct",
                    context.environment.bedroom_light_brightness
                ),
                "취침 루틴".to_string(),
            ],
            safety: ActionSafety {
                auto_executable: true,
                requires_approval: false,
            },
            ha_service: Some(HaServiceCall {
                domain: "light".to_string(),
                service: "turn_on".to_string(),
                entity_id: "light.bedroom".to_string(),
                brightness_pct: Some(30),
            }),
        });
    }

    actions
}

fn is_deep_focus(context: &NowContext) -> bool {
    context.computer.current_mode == "coding" && context.computer.focus_block_minutes >= 45
}
