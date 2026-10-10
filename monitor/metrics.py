"""Versioned metric definitions for the metrics-documentation page (P-016).

The metrics page must render without waiting for data, so every metric's
definition lives here as data, keyed by the catalog metric profile. Each
definition carries the fields the product contract requires: name, profile
version, sample object, time basis, start/end rule, terminal & observed rule,
per-metric eligibility, unit, quantile algorithm, missing/approximation
strategy, aggregation rule and source evidence.

``validate_profile`` checks structural completeness only; it does not rewrite
historical statistics and it never derives one quality axis from another.
"""

from __future__ import annotations

SCHEMA_VERSION = 1

REQUIRED_FIELDS = frozenset({
    "name",
    "profile_version",
    "sample_object",
    "time_basis",
    "start_end_rule",
    "terminal_and_observed_rule",
    "eligibility",
    "unit",
    "quantile_algorithm",
    "missing_strategy",
    "aggregation",
    "evidence",
})


def _metric(**kwargs):
    missing = [field for field in REQUIRED_FIELDS if field not in kwargs]
    if missing:
        raise ValueError(f"metric {kwargs.get('name')!r} missing fields: {', '.join(missing)}")
    return kwargs


PROFILES = {
    "ubs-pr-representative-v1": {
        "display_name": "openEuler UBS · PR 代表批次",
        "metrics": [
            _metric(
                name="门禁 E2E",
                profile_version="ubs-pr-representative-v1",
                sample_object="每个 PR 的最长有效 E2E 批次（代表批次）",
                time_basis="pr_created_at",
                start_end_rule="起点为 PR 创建/推送/重跑评论时间；终点为 trigger 及全部子任务最晚结束；并行任务按墙钟不累加",
                terminal_and_observed_rule="仅批次结束、下游集合核验且全部子任务成功为成功；子任务失败或 trigger 异常为失败；执行中/缺失为数据不完整；取消记失败并计入 E2E",
                eligibility="最长有效 E2E 批次；并列按 trigger 编号降序、URL 稳定次序；成功/失败/取消均可入选，执行中/不完整/缺起点排除",
                unit="分钟",
                quantile_algorithm="PERCENTILE.INC 线性插值 P90",
                missing_strategy="缺值不补零，显示 —",
                aggregation="跨仓直接汇聚每个 PR 代表值，不平均各仓均值/P90",
                evidence="snapshot.meta / batches[].trigger / children[] 关联与结果字段",
            ),
            _metric(
                name="x86 / ARM / DT 任务耗时",
                profile_version="ubs-pr-representative-v1",
                sample_object="代表批次的同类已结束任务（关联有效且唯一）",
                time_basis="pr_created_at",
                start_end_rule="同代表批次；排队=请求到开始，执行=开始到结束，总计=排队+执行",
                terminal_and_observed_rule="仅结果符合既有终态规则的已结束任务；running 不计入均值/P90",
                eligibility="必须来自同一代表批次，且关联有效、唯一、已结束；不从其他批次补值",
                unit="分钟",
                quantile_algorithm="PERCENTILE.INC 线性插值 P90",
                missing_strategy="代表批次缺某类任务或关联不唯一时留空，不补零",
                aggregation="按 PR 代表值汇聚",
                evidence="batches[].children[] 的 kind/association_valid/result/queue_ms/duration_ms/total_ms",
            ),
            _metric(
                name="PR 有效覆盖",
                profile_version="ubs-pr-representative-v1",
                sample_object="当前分析集内具有有效代表批次的 PR",
                time_basis="pr_created_at",
                start_end_rule="覆盖分子=有效代表批次 PR 数；分母=当前分析集 PR 数",
                terminal_and_observed_rule="仅计数有效代表批次 PR",
                eligibility="有有效代表批次即计入覆盖",
                unit="百分比",
                quantile_algorithm="—",
                missing_strategy="无有效样本显示 0% 并标注样本不足",
                aggregation="跨仓分母=入选 PR 总数，分子=有代表批次 PR 数",
                evidence="metrics.representative_batch_number / representative_batch_url",
            ),
        ],
    },
    "triton-commit-attempt-v1": {
        "display_name": "Triton-Ascend · 提交/手动重跑批次",
        "metrics": [
            _metric(
                name="门禁 E2E",
                profile_version="triton-commit-attempt-v1",
                sample_object="按 PR head SHA 聚合的提交批次；手动重跑按 run/attempt 独立成批",
                time_basis="batch_started_at",
                start_end_rule="E2E 从提交事件到该批次最后一项自动检查结束，含排队与依赖等待；起点缺失按 attempt 开始/最早 workflow 创建近似并标注",
                terminal_and_observed_rule="success/failure 且有限非负 duration 为终态分位数样本；running/cancelled 仅保留 observed 耗时",
                eligibility="success/failure 批次参与趋势；取消/运行中仅展示已观测耗时",
                unit="分钟",
                quantile_algorithm="PERCENTILE.INC 线性插值 P90",
                missing_strategy="无本次证据的起点留空，不进入时间窗趋势，可在数据质量查询",
                aggregation="不跨项目混入 UBS 代表样本；仅批内聚合",
                evidence="batches[].head_sha / start_at / duration / 状态与 attempt 历史",
            ),
            _metric(
                name="NPU 最长排队 / A3 / A5 重点任务",
                profile_version="triton-commit-attempt-v1",
                sample_object="批次内 NPU 任务队列与 A3/A5 重点任务耗时",
                time_basis="batch_started_at",
                start_end_rule="按任务排队起点到执行起点计算排队；执行到结束为耗时",
                terminal_and_observed_rule="已完成任务时间戳完整；失败步骤保留",
                eligibility="按项目 profile 声明的重点任务",
                unit="分钟",
                quantile_algorithm="PERCENTILE.INC 线性插值 P90",
                missing_strategy="时间戳不完整不参与趋势，计入质量报告",
                aggregation="批内/项目内聚合",
                evidence="triton payload batches[].jobs / NPU 识别覆盖",
            ),
        ],
    },
}


def profile_ids() -> list[str]:
    return list(PROFILES)


def profile_metrics(profile_id: str) -> list[dict]:
    profile = PROFILES.get(profile_id)
    if profile is None:
        raise KeyError(f"unknown metric profile {profile_id!r}")
    return profile["metrics"]


def describe_profile(profile_id: str) -> dict:
    profile = PROFILES.get(profile_id)
    if profile is None:
        raise KeyError(f"unknown metric profile {profile_id!r}")
    return {
        "schema_version": SCHEMA_VERSION,
        "profile_id": profile_id,
        "display_name": profile["display_name"],
        "metrics": profile["metrics"],
    }


def validate_profile(profile_id: str, metrics: list[dict] | None = None) -> list[str]:
    """Return structural violations (empty means complete)."""
    if profile_id not in PROFILES:
        return [f"unknown metric profile {profile_id!r}"]
    metrics = PROFILES[profile_id]["metrics"] if metrics is None else metrics
    problems: list[str] = []
    if not isinstance(metrics, list) or not metrics:
        return [f"profile {profile_id!r} defines no metrics"]
    for index, metric in enumerate(metrics):
        for field in REQUIRED_FIELDS:
            if not metric.get(field):
                problems.append(f"{profile_id} metric {index} missing {field}")
    return problems
