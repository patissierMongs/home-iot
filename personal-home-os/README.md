# Personal Home OS Rust Core

Clean Rust reboot of the Home Assistant-centered Personal Home OS agent.

## Principle

Home Assistant is the source of truth for physical state, sensor fusion, helpers, and low-level detection. This Rust core consumes HA states/events and produces semantic events, context, recommendations, briefings, and safe HA service-call decisions.

## Current slice

Implemented first TDD slice:

```text
HA state_changed supplement presence on→off
  → SemanticEventMapper
  → supplement.taken.magnesium
```

## Verify

```bash
cargo fmt --check
cargo test
cargo clippy --all-targets --all-features -- -D warnings
```
