use crate::context::RecommendedAction;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ActionDecision {
    Allowed,
    RequiresApproval,
    Denied,
}

#[derive(Clone, Debug)]
pub struct SafetyPolicy {
    allowlisted_action_ids: Vec<String>,
}

impl SafetyPolicy {
    pub fn new(allowlisted_action_ids: Vec<String>) -> Self {
        Self {
            allowlisted_action_ids,
        }
    }

    pub fn decide(&self, action: &RecommendedAction) -> ActionDecision {
        if action.safety.auto_executable
            && !action.safety.requires_approval
            && self
                .allowlisted_action_ids
                .iter()
                .any(|id| id == &action.id)
        {
            ActionDecision::Allowed
        } else if action.safety.requires_approval || action.ha_service.is_none() {
            ActionDecision::RequiresApproval
        } else {
            ActionDecision::Denied
        }
    }
}
