"""Streaming pipeline checks using one documented RPC per event."""
from api import Verdict


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def check_data_batch(payload, ctx):
    profile = ctx.tools.batch_profile(payload["batch_id"])
    if "error" in profile:
        return _tool_error("checks", profile)
    b = ctx.baseline
    rows = profile["row_count"]
    amount = profile["mean_amount"]
    nulls = profile["null_rate"]["customer_id"]
    stale = profile["staleness_min"]
    signals = []
    if not b["row_count_min"] <= rows <= b["row_count_max"]:
        signals.append("volume outside historical bounds")
    if not b["mean_amount_min"] <= amount <= b["mean_amount_max"]:
        signals.append("order amount distribution shifted")
    if nulls > b["null_rate_max"]:
        signals.append("customer identifier null spike")
    if stale > b["staleness_min_max"]:
        signals.append("stale order batch")

    # Scale two-sided deviations by the historical 3-sigma half-width,
    # not by sigma: a single metric at its limit contributes exactly 1.
    row_mid = (b["row_count_min"] + b["row_count_max"]) / 2
    row_radius = (b["row_count_max"] - b["row_count_min"]) / 2
    amount_mid = (b["mean_amount_min"] + b["mean_amount_max"]) / 2
    amount_radius = (b["mean_amount_max"] - b["mean_amount_min"]) / 2
    distance_squared = (
        ((rows - row_mid) / row_radius) ** 2
        + ((amount - amount_mid) / amount_radius) ** 2
        + (nulls / b["null_rate_max"]) ** 2
        + (stale / b["staleness_min_max"]) ** 2
    )
    if distance_squared > 1.30 ** 2:
        signals.append("joint quality deviation")
    return Verdict(alert=bool(signals), pillar="checks", reason="; ".join(signals))


def _tool_error(pillar, result):
    # An unavailable measurement is not proof of a data fault. Keep its
    # diagnostic visible in the report without charging for a retry.
    return Verdict(alert=False, confidence=0.0, pillar=pillar,
                   reason="measurement unavailable: " + str(result["error"]))


def check_contract_checkpoint(payload, ctx):
    diff = ctx.tools.contract_diff(payload["contract_id"], payload["checkpoint_batch_id"])
    if "error" in diff:
        return _tool_error("contracts", diff)
    signals = list(diff["violations"])
    limit = ctx.baseline["freshness_delay_max_min"]
    declared_sla = payload.get("declared_sla") or {}
    if declared_sla.get("freshness_min") is not None:
        limit = min(limit, declared_sla["freshness_min"])
    if diff["freshness_delay_min"] > limit:
        signals.append("contract freshness exceeded")
    return Verdict(alert=bool(signals), pillar="contracts", reason="; ".join(signals))


def check_lineage_run(payload, ctx):
    # TODO: ctx.tools.lineage_graph_slice(payload["run_id"])
    return Verdict(alert=False, pillar="lineage")


def check_feature_materialization(payload, ctx):
    # TODO: ctx.tools.feature_drift(payload["feature_view"], payload["batch_id"])
    return Verdict(alert=False, pillar="ai_infra")


def check_embedding_batch(payload, ctx):
    # TODO: ctx.tools.embedding_drift(payload["corpus"], payload["chunk_batch_id"])
    return Verdict(alert=False, pillar="ai_infra")
