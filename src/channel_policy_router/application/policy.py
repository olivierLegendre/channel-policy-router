from channel_policy_router.domain.entities import Channel, ClassPolicy, CommandClass

POLICY_MATRIX: dict[CommandClass, ClassPolicy] = {
    CommandClass.safety_critical: ClassPolicy(
        command_class=CommandClass.safety_critical,
        primary_channel=Channel.api,
        api_timeout_seconds=5,
        api_attempts_before_fallback=2,
        mqtt_retry_budget=0,
        mqtt_fallback_allowed=False,
        reconciliation_sla_seconds=60,
    ),
    CommandClass.interactive_control: ClassPolicy(
        command_class=CommandClass.interactive_control,
        primary_channel=Channel.api,
        api_timeout_seconds=3,
        api_attempts_before_fallback=1,
        mqtt_retry_budget=2,
        mqtt_fallback_allowed=True,
        reconciliation_sla_seconds=60,
    ),
    CommandClass.routine_automation: ClassPolicy(
        command_class=CommandClass.routine_automation,
        primary_channel=Channel.api,
        api_timeout_seconds=10,
        api_attempts_before_fallback=2,
        mqtt_retry_budget=3,
        mqtt_fallback_allowed=True,
        reconciliation_sla_seconds=300,
    ),
    CommandClass.bulk_non_critical: ClassPolicy(
        command_class=CommandClass.bulk_non_critical,
        primary_channel=Channel.api,
        api_timeout_seconds=30,
        api_attempts_before_fallback=3,
        mqtt_retry_budget=0,
        mqtt_fallback_allowed=False,
        reconciliation_sla_seconds=1800,
    ),
}
