from collections import Counter
from pathlib import Path

from model_regression_eval.cli import mock_answer
from model_regression_eval.graders import grade
from model_regression_eval.profiles import apply_profile, fit_request_budget
from model_regression_eval.tasks import load_tasks


def test_core_task_file_loads_and_mock_answers_grade_correctly():
    tasks = load_tasks(Path('tasks/core.zh.jsonl'))
    assert len(tasks) == 300
    ids = [task.id for task in tasks]
    assert len(ids) == len(set(ids))
    for task in tasks:
        result = grade(task, mock_answer(task))
        assert result.correct, f'{task.id}: {result}'


def test_core_task_file_prompts_are_unique():
    tasks = load_tasks(Path('tasks/core.zh.jsonl'))
    prompts = [task.prompt for task in tasks]
    duplicates = [prompt for prompt, count in Counter(prompts).items() if count > 1]
    assert duplicates == []


def test_core_task_file_has_basic_domain_coverage():
    tasks = load_tasks(Path('tasks/core.zh.jsonl'))
    domains = {task.domain for task in tasks}
    assert {'math', 'logic', 'code', 'instruction', 'reading', 'robustness', 'metacognition'}.issubset(domains)


def test_core_task_file_includes_reviewed_replacement_tasks():
    tasks = load_tasks(Path('tasks/core.zh.jsonl'))
    ids = {task.id for task in tasks}
    assert {
        'math_colored_polygon_isosceles_trapezoid_001',
        'math_rectangle_five_points_small_triangles_001',
        'math_concat_permutation_001',
        'math_recurrence_integer_terms_001',
        'logic_nand_nand_expression_001',
        'math_cube_cut_water_level_001',
        'math_folding_dihedral_min_cos_001',
        'math_rational_recurrence_mod_001',
        'math_parabola_focus_conic_slope_001',
        'math_trig_product_max_sum_001',
        'logic_safe_password_001',
        'math_svm_max_margin_001',
        'math_raindrop_variable_mass_distance_001',
        'math_piecewise_function_collinear_slope_001',
        'math_tetrahedron_inner_cube_sphere_area_001',
        'math_seating_constraints_001',
        'math_triangle_incircle_distance_extrema_001',
        'math_grid_coloring_three_colors_interval_001',
        'logic_letter_average_cipher_001',
        'math_random_flip_absorption_001',
        'robust_trick_bamboo_door_001',
        'robust_trick_polar_bear_penguin_001',
        'robust_trick_car_wash_001',
        'robust_trick_cake_cut_001',
    }.issubset(ids)
    assert 'math_arithmetic_001' not in ids
    assert 'logic_boolean_001' not in ids
    assert 'robust_counterexample_002' not in ids


def test_reviewed_complex_tasks_are_marked_as_hard_frontier():
    tasks = load_tasks(Path('tasks/core.zh.jsonl'))
    complex_ids = {
        'math_colored_polygon_isosceles_trapezoid_001',
        'math_rectangle_five_points_small_triangles_001',
        'math_concat_permutation_001',
        'math_recurrence_integer_terms_001',
        'logic_nand_nand_expression_001',
        'math_cube_cut_water_level_001',
        'math_folding_dihedral_min_cos_001',
        'math_rational_recurrence_mod_001',
        'math_parabola_focus_conic_slope_001',
        'math_trig_product_max_sum_001',
        'logic_safe_password_001',
        'math_svm_max_margin_001',
        'math_raindrop_variable_mass_distance_001',
        'math_piecewise_function_collinear_slope_001',
        'math_tetrahedron_inner_cube_sphere_area_001',
        'math_seating_constraints_001',
        'math_triangle_incircle_distance_extrema_001',
        'math_grid_coloring_three_colors_interval_001',
        'logic_letter_average_cipher_001',
        'math_random_flip_absorption_001',
    }
    by_id = {task.id: task for task in tasks}
    assert complex_ids.issubset(by_id)
    for task_id in complex_ids:
        task = by_id[task_id]
        assert task.difficulty == 'hard'
        assert task.tier == 'frontier'
        assert task.answer_mode == 'deterministic'


def test_lateral_reasoning_replacement_avoids_negative_false_positive():
    tasks = load_tasks(Path('tasks/core.zh.jsonl'))
    bamboo = next(task for task in tasks if task.id == 'robust_trick_bamboo_door_001')
    result = grade(bamboo, '不能，因为不能垂直通过')
    assert not result.correct


def test_formula_and_ordered_complex_tasks_reject_known_false_positives():
    tasks = load_tasks(Path('tasks/core.zh.jsonl'))
    raindrop = next(task for task in tasks if task.id == 'math_raindrop_variable_mass_distance_001')
    wrong_log_sign = 'gt^2/4 + gm_0t/(2lambda) + gm_0^2/(2lambda^2) ln(1+lambdat/m_0)'
    assert not grade(raindrop, wrong_log_sign).correct

    triangle = next(task for task in tasks if task.id == 'math_triangle_incircle_distance_extrema_001')
    assert not grade(triangle, '72, 88').correct


def test_profiles_have_expected_sizes_and_coverage():
    tasks = load_tasks(Path('tasks/core.zh.jsonl'))
    smoke = apply_profile(tasks, 'smoke', seed=0)
    standard = apply_profile(tasks, 'standard', seed=0)
    full = apply_profile(tasks, 'full', seed=0)
    assert len(smoke) == 40
    assert len(standard) == 100
    assert len(full) == 300
    assert len({task.domain for task in smoke}) >= 5
    assert len({task.domain for task in standard}) >= 6


def test_max_requests_caps_cases_by_reducing_tasks_stratified():
    tasks = load_tasks(Path('tasks/core.zh.jsonl'))
    selected = fit_request_budget(tasks, repeats=3, max_requests=30, seed=0)
    assert len(selected) == 10
    assert len(selected) * 3 <= 30

from argparse import Namespace
from model_regression_eval.cli import select_tasks_for_args
from model_regression_eval.profiles import resolve_profile_and_repeats


def test_depth_confirm_sets_repeats_without_changing_profile_size():
    args = Namespace(
        tasks='tasks/core.zh.jsonl',
        include_quarantined=False,
        task_id=None,
        profile='smoke',
        depth='confirm',
        repeats=None,
        limit=None,
        max_requests=None,
        seed=0,
    )
    selected, repeats, meta = select_tasks_for_args(args)
    assert len(selected) == 40
    assert repeats == 3
    assert meta['resolved_profile'] == 'smoke'
    assert meta['repeat_source'] == '--depth confirm'


def test_repeats_overrides_depth():
    resolved_profile, repeats, meta = resolve_profile_and_repeats('standard', 'deep', 2)
    assert resolved_profile == 'standard'
    assert repeats == 2
    assert meta['repeat_source'] == '--repeats'


def test_legacy_deep_profile_maps_to_full_confirm():
    args = Namespace(
        tasks='tasks/core.zh.jsonl',
        include_quarantined=False,
        task_id=None,
        profile='deep',
        depth=None,
        repeats=None,
        limit=None,
        max_requests=None,
        seed=0,
    )
    selected, repeats, meta = select_tasks_for_args(args)
    assert len(selected) == 300
    assert repeats == 3
    assert meta['resolved_profile'] == 'full'
    assert meta['legacy_profile_deep'] is True


def test_max_requests_caps_after_depth():
    args = Namespace(
        tasks='tasks/core.zh.jsonl',
        include_quarantined=False,
        task_id=None,
        profile='standard',
        depth='confirm',
        repeats=None,
        limit=None,
        max_requests=120,
        seed=0,
    )
    selected, repeats, _ = select_tasks_for_args(args)
    assert repeats == 3
    assert len(selected) == 40
    assert len(selected) * repeats <= 120


def test_metadata_filters_select_frontier_tasks_before_profile():
    args = Namespace(
        tasks='tasks/core.zh.jsonl',
        include_quarantined=False,
        task_id=None,
        difficulty=['hard'],
        tier=['frontier'],
        answer_mode=['deterministic'],
        profile='smoke',
        depth='quick',
        repeats=None,
        limit=None,
        max_requests=None,
        seed=0,
    )
    selected, repeats, meta = select_tasks_for_args(args)
    assert repeats == 1
    assert meta['resolved_profile'] == 'smoke'
    assert len(selected) == 20
    assert {task.difficulty for task in selected} == {'hard'}
    assert {task.tier for task in selected} == {'frontier'}
    assert {task.answer_mode for task in selected} == {'deterministic'}

from model_regression_eval.profiles import _proportional_quotas


def test_proportional_quotas_caps_target_to_capacity():
    quotas = _proportional_quotas({'a': 2, 'b': 2, 'c': 2}, 100)
    assert sum(quotas.values()) == 6
    assert quotas == {'a': 2, 'b': 2, 'c': 2}


def test_proportional_quotas_handles_zero_or_negative_targets():
    assert _proportional_quotas({'a': 2, 'b': 2}, 0) == {'a': 0, 'b': 0}
