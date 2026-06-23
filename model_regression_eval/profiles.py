from __future__ import annotations

from collections import defaultdict
import random
from typing import Any

from .tasks import EvalTask


# Profiles now describe coverage/task-count only. Repetition depth is configured
# separately through --depth or --repeats. The legacy "deep" profile is kept as a
# compatibility alias for "full + confirm depth".
PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "smoke": {
        "target_tasks": 40,
        "description": "Low-cost daily sanity check. Use it to catch gross failures, not to declare regression.",
    },
    "standard": {
        "target_tasks": 100,
        "description": "Default paired regression screen with stratified coverage.",
    },
    "full": {
        "target_tasks": None,
        "description": "Full task set once. Use after standard suggests a possible regression.",
    },
    "deep": {
        "target_tasks": None,
        "legacy_alias_for": "full",
        "legacy_depth": "confirm",
        "description": "Legacy alias for --profile full --depth confirm. Prefer using --depth/--repeats explicitly.",
    },
}

DEPTH_DEFAULTS: dict[str, dict[str, Any]] = {
    "quick": {
        "repeats": 1,
        "description": "One pass per task. Best for smoke screens and low-cost coverage.",
    },
    "confirm": {
        "repeats": 3,
        "description": "Three passes per task. Best for confirming suspected regressions.",
    },
    "deep": {
        "repeats": 5,
        "description": "Five passes per task. Expensive high-confidence stability check.",
    },
}

PROFILE_CHOICES = tuple(PROFILE_DEFAULTS)
DEPTH_CHOICES = tuple(DEPTH_DEFAULTS)


def resolve_profile_and_repeats(
    profile: str | None,
    depth: str | None,
    repeats: int | None,
) -> tuple[str | None, int, dict[str, Any]]:
    """Resolve the user-facing coverage/depth options.

    Resolution order:
    1. --profile deep is a legacy alias for --profile full --depth confirm.
    2. --repeats, when provided, is authoritative.
    3. --depth maps to a repeat count.
    4. default repeat count is 1.
    """
    requested_profile = profile
    requested_depth = depth
    legacy_profile_deep = False

    if profile == "deep":
        profile = "full"
        legacy_profile_deep = True
        if depth is None and repeats is None:
            depth = str(PROFILE_DEFAULTS["deep"].get("legacy_depth", "confirm"))

    if profile is not None and profile not in PROFILE_DEFAULTS:
        raise ValueError(f"Unknown profile: {profile}")
    if depth is not None and depth not in DEPTH_DEFAULTS:
        raise ValueError(f"Unknown depth: {depth}")

    if repeats is not None:
        resolved_repeats = repeats
        repeat_source = "--repeats"
    elif depth is not None:
        resolved_repeats = int(DEPTH_DEFAULTS[depth]["repeats"])
        repeat_source = f"--depth {depth}"
    else:
        resolved_repeats = 1
        repeat_source = "default"

    if resolved_repeats <= 0:
        raise ValueError("--repeats must be positive")

    meta = {
        "requested_profile": requested_profile,
        "resolved_profile": profile,
        "requested_depth": requested_depth,
        "resolved_depth": depth,
        "repeats": resolved_repeats,
        "repeat_source": repeat_source,
        "legacy_profile_deep": legacy_profile_deep,
    }
    return profile, resolved_repeats, meta


def apply_profile(tasks: list[EvalTask], profile: str | None, *, seed: int = 0) -> list[EvalTask]:
    if not profile:
        return list(tasks)
    if profile == "deep":
        profile = "full"
    if profile not in PROFILE_DEFAULTS:
        raise ValueError(f"Unknown profile: {profile}")
    target = PROFILE_DEFAULTS[profile]["target_tasks"]
    if target is None or target >= len(tasks):
        return list(tasks)
    return stratified_select(tasks, int(target), seed=seed)


def stratified_select(tasks: list[EvalTask], target_count: int, *, seed: int = 0, key: str = "domain") -> list[EvalTask]:
    """Deterministic stratified sample preserving original order in the returned list."""
    if target_count <= 0:
        return []
    if target_count >= len(tasks):
        return list(tasks)

    groups: dict[str, list[EvalTask]] = defaultdict(list)
    for task in tasks:
        groups[str(getattr(task, key))].append(task)

    quotas = _proportional_quotas({name: len(items) for name, items in groups.items()}, target_count)
    rng = random.Random(seed)
    selected_ids: set[str] = set()
    for name, items in sorted(groups.items()):
        quota = quotas.get(name, 0)
        if quota <= 0:
            continue
        shuffled = list(items)
        rng.shuffle(shuffled)
        for task in shuffled[:quota]:
            selected_ids.add(task.id)

    # If rounding left a gap, fill by deterministic shuffled leftovers.
    if len(selected_ids) < target_count:
        leftovers = [task for task in tasks if task.id not in selected_ids]
        rng.shuffle(leftovers)
        for task in leftovers[: target_count - len(selected_ids)]:
            selected_ids.add(task.id)

    # If rounding over-filled, trim deterministically.
    if len(selected_ids) > target_count:
        selected = [task for task in tasks if task.id in selected_ids]
        rng.shuffle(selected)
        selected_ids = {task.id for task in selected[:target_count]}

    return [task for task in tasks if task.id in selected_ids]


def fit_request_budget(tasks: list[EvalTask], repeats: int, max_requests: int | None, *, seed: int = 0) -> list[EvalTask]:
    if max_requests is None:
        return tasks
    if max_requests <= 0:
        return []
    if repeats <= 0:
        raise ValueError("repeats must be positive")
    max_tasks = max_requests // repeats
    if max_tasks <= 0:
        return []
    if len(tasks) <= max_tasks:
        return tasks
    return stratified_select(tasks, max_tasks, seed=seed)


def _proportional_quotas(sizes: dict[str, int], target_count: int) -> dict[str, int]:
    """Allocate a stratified sample quota without exceeding group capacity.

    This helper is intentionally defensive because it is useful outside the
    current CLI path. If callers request more seats than total capacity, cap the
    target to the available total instead of looping forever.
    """
    total = sum(max(0, size) for size in sizes.values())
    if total <= 0 or target_count <= 0:
        return {name: 0 for name in sizes}
    target_count = min(int(target_count), total)
    positive_groups = {name: max(0, size) for name, size in sizes.items() if size > 0}
    raw = {name: size * target_count / total for name, size in positive_groups.items()}
    quotas = {name: 0 for name in sizes}
    quotas.update({name: min(int(value), positive_groups[name]) for name, value in raw.items()})

    # Ensure every non-empty group gets at least one item when possible.
    if target_count >= len(positive_groups):
        for name, size in positive_groups.items():
            if quotas[name] == 0:
                quotas[name] = 1

    current = sum(quotas.values())
    # Add remaining seats by largest fractional remainder. Rebuild the
    # growable list each pass so the loop terminates when capacity is exhausted.
    while current < target_count:
        growable = [name for name in positive_groups if quotas[name] < positive_groups[name]]
        if not growable:
            break
        growable.sort(key=lambda name: (raw[name] - int(raw[name]), positive_groups[name], name), reverse=True)
        name = growable[0]
        quotas[name] += 1
        current += 1

    # Remove excess from smallest fractional remainder, preserving at least one
    # per non-empty group when possible. Recompute shrinkable entries to avoid
    # non-progress cycles.
    min_allowed = 1 if target_count >= len(positive_groups) else 0
    while current > target_count:
        shrinkable = [name for name in positive_groups if quotas[name] > min_allowed]
        if not shrinkable:
            break
        shrinkable.sort(key=lambda name: (raw[name] - int(raw[name]), positive_groups[name], name))
        name = shrinkable[0]
        quotas[name] -= 1
        current -= 1
    return quotas
