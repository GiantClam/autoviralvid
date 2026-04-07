import importlib.util
import json
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "run_reference_regression_once.py"
    spec = importlib.util.spec_from_file_location("run_reference_regression_once", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def _load_generate_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "generate_ppt_from_desc.py"
    spec = importlib.util.spec_from_file_location("generate_ppt_from_desc", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_phase_artifact_paths_are_normalized():
    mod = _load_module()
    paths = mod._phase_artifact_paths(Path("output/regression"), " Phase-1@Alpha ")
    assert paths["generated_ppt"].name == "generated.phase-1alpha.pptx"
    assert paths["render_json"].name == "generated.phase-1alpha.render.json"
    assert paths["issues_json"].name == "issues.phase-1alpha.json"
    assert paths["summary_json"].name == "round_summary.phase-1alpha.json"


def test_publish_phase_artifacts_and_append_fix_record(tmp_path: Path):
    mod = _load_module()
    generated = tmp_path / "generated.pptx"
    render = tmp_path / "generated.render.json"
    issues = tmp_path / "issues.json"
    summary = tmp_path / "summary.json"
    generated.write_bytes(b"pptx")
    render.write_text("{}", encoding="utf-8")
    issues.write_text("{}", encoding="utf-8")
    summary.write_text("{}", encoding="utf-8")

    published = mod._publish_phase_artifacts(
        phase="phase0",
        output_root=tmp_path,
        generated_ppt=generated,
        render_json=render,
        issues_json=issues,
        summary_json=summary,
    )
    published_ppt = Path(published["generated_ppt"])
    published_render = Path(published["render_json"])
    published_issues = Path(published["issues_json"])
    published_summary = Path(published["summary_json"])
    assert published_ppt.exists()
    assert published_render.exists()
    assert published_issues.exists()
    assert published_summary.exists()

    fix_record = tmp_path / "fix_record.json"
    mod._append_fix_record(
        fix_record_path=fix_record,
        phase="phase0",
        status="VERIFIED",
        score=88.5,
        generated_ppt=published_ppt,
        render_json=published_render,
        issues_json=published_issues,
        summary_json=published_summary,
    )
    data = json.loads(fix_record.read_text(encoding="utf-8"))
    assert data["phase_runs"][-1]["phase"] == "phase0"
    assert float(data["phase_runs"][-1]["score"]) == 88.5
    assert str(data["phase_runs"][-1]["render_json"]).endswith(".render.json")
    assert data["phase_runs"][-1]["active_cluster"] == ""


def test_build_compare_cmd_respects_allow_warnings():
    mod = _load_module()
    cmd = mod._build_compare_cmd(
        python_bin="python",
        reference_ppt=Path("ref.pptx"),
        generated_ppt=Path("gen.pptx"),
        issues_json=Path("issues.json"),
        compare_mode="structural",
        pass_score=70.0,
        allow_warnings=True,
        require_psnr=True,
    )
    assert "--require-no-issues" in cmd
    idx = cmd.index("--require-no-issues")
    assert cmd[idx + 1] == "off"
    idx_psnr = cmd.index("--require-psnr")
    assert cmd[idx_psnr + 1] == "on"
    assert "--pass-score" in cmd


def test_resolve_quality_bar_high_raises_gate():
    mod = _load_module()
    cfg = mod._resolve_quality_bar(
        quality_bar="high",
        target_score=70.0,
        compare_mode="structural",
        allow_warnings=True,
    )
    assert cfg["target_score"] >= 90.0
    assert cfg["compare_mode"] == "auto"
    assert cfg["allow_warnings"] is False
    assert cfg["require_psnr"] is True


def test_resolve_reconstruct_switches_high_defaults_to_on():
    mod = _load_module()
    cfg = mod._resolve_reconstruct_switches(
        creation_mode="fidelity",
        quality_bar="high",
        reconstruct_template_shell="auto",
        reconstruct_source_aligned="auto",
    )
    assert cfg["reconstruct_template_shell"] == "on"
    assert cfg["reconstruct_source_aligned"] == "on"


def test_resolve_reconstruct_switches_zero_create_forces_off():
    mod = _load_module()
    cfg = mod._resolve_reconstruct_switches(
        creation_mode="zero_create",
        quality_bar="high",
        reconstruct_template_shell="on",
        reconstruct_source_aligned="on",
    )
    assert cfg["reconstruct_template_shell"] == "off"
    assert cfg["reconstruct_source_aligned"] == "off"


def test_resolve_generation_mode_zero_create_defaults_to_api_on_auto():
    mod = _load_module()
    mode = mod._resolve_generation_mode(
        creation_mode="zero_create",
        requested_mode="auto",
        local_strategy="reconstruct",
        reconstruct_via_pipeline="on",
    )
    assert mode == "api"


def test_resolve_generation_mode_zero_create_keeps_explicit_api():
    mod = _load_module()
    mode = mod._resolve_generation_mode(
        creation_mode="zero_create",
        requested_mode="api",
        local_strategy="reconstruct",
        reconstruct_via_pipeline="on",
    )
    assert mode == "api"


def test_resolve_generation_mode_zero_create_keeps_explicit_local():
    mod = _load_module()
    mode = mod._resolve_generation_mode(
        creation_mode="zero_create",
        requested_mode="local",
        local_strategy="reconstruct",
        reconstruct_via_pipeline="off",
    )
    assert mode == "local"


def test_resolve_generation_mode_zero_create_auto_can_switch_to_local_by_env(monkeypatch):
    mod = _load_module()
    monkeypatch.setenv("PPT_ZERO_CREATE_DEFAULT_MODE", "local")
    mode = mod._resolve_generation_mode(
        creation_mode="zero_create",
        requested_mode="auto",
        local_strategy="reconstruct",
        reconstruct_via_pipeline="on",
    )
    assert mode == "local"


def test_resolve_generation_mode_source_replay_forces_local():
    mod = _load_module()
    mode = mod._resolve_generation_mode(
        creation_mode="fidelity",
        requested_mode="api",
        local_strategy="source-replay",
        reconstruct_via_pipeline="on",
    )
    assert mode == "local"


def test_resolve_generation_mode_reconstruct_pipeline_forces_api():
    mod = _load_module()
    mode = mod._resolve_generation_mode(
        creation_mode="fidelity",
        requested_mode="local",
        local_strategy="reconstruct",
        reconstruct_via_pipeline="on",
    )
    assert mode == "api"


def test_sanitize_input_for_zero_create_removes_reference_shortcuts(tmp_path: Path):
    mod = _load_module()
    source = tmp_path / "input.json"
    source.write_text(
        json.dumps(
            {
                "title": "Deck",
                "source_pptx_path": "C:/ref.pptx",
                "theme_manifest": [{"k": "v"}],
                "master_layout_manifest": [{"k": "v"}],
                "media_manifest": [{"k": "v"}],
                "slides": [
                    {
                        "page_number": 1,
                        "title": "Overview",
                        "elements": [{"type": "text", "content": "A"}],
                        "shapes": [{"type": "shape", "subtype": "rect"}],
                        "media_refs": [{"rid": "rId1"}],
                        "slide_layout_path": "ppt/slideLayouts/slideLayout1.xml",
                        "slide_layout_name": "Title and Content",
                        "slide_master_path": "ppt/slideMasters/slideMaster1.xml",
                        "slide_theme_path": "ppt/theme/theme1.xml",
                        "blocks": [{"block_type": "body", "content": "content"}],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = mod._sanitize_input_for_zero_create(source)
    assert out["applied"] is True
    after = json.loads(source.read_text(encoding="utf-8"))
    assert "source_pptx_path" not in after
    assert "theme_manifest" not in after
    assert "master_layout_manifest" not in after
    assert "media_manifest" not in after
    assert out.get("kept_sanitized_slides") is True
    assert isinstance(after.get("slides"), list) and len(after.get("slides")) == 1
    first_slide = after["slides"][0]
    assert "elements" not in first_slide
    assert "shapes" not in first_slide
    assert "media_refs" not in first_slide
    assert int(after.get("requested_total_pages") or 0) >= 3
    assert isinstance(after.get("required_facts"), list)


def test_build_pipeline_payload_allows_zero_create_without_media_manifest():
    mod = _load_generate_module()
    desc = {
        "title": "Deck",
        "slides": [{"slide_id": "s1", "title": "概览", "blocks": [{"block_type": "body", "content": "内容"}]}],
        "theme": {"primary": "22223b", "secondary": "4a4e69", "accent": "9a8c98", "bg": "f2e9e4"},
    }
    payload = mod._build_pipeline_payload_from_desc(
        desc,
        execution_profile="prod_safe",
        strict_no_fallback=False,
        creation_mode="zero_create",
    )
    assert isinstance(payload, dict)
    assert payload.get("reconstruct_from_reference") is False
    assert "reference_desc" not in payload
    assert payload.get("web_enrichment") is False
    assert payload.get("execution_profile") == "prod_safe"
    assert payload.get("quality_profile") == "lenient_draft"
    assert payload.get("force_ppt_master") is False


def test_generate_zero_create_sanitize_drops_manifests_and_slide_structures():
    mod = _load_generate_module()
    sanitized = mod._sanitize_desc_for_zero_create(
        {
            "title": "Deck",
            "source_pptx_path": "D:/ref.pptx",
            "theme_manifest": [{"path": "ppt/theme/theme1.xml"}],
            "master_layout_manifest": [{"path": "ppt/slideLayouts/slideLayout1.xml"}],
            "media_manifest": [{"path": "ppt/media/image1.png"}],
            "slides": [
                {
                    "page_number": 1,
                    "title": "Overview",
                    "elements": [{"type": "text", "content": "A"}],
                    "shapes": [{"type": "shape", "subtype": "rect"}],
                    "media_refs": [{"rid": "rId1"}],
                    "slide_layout_path": "ppt/slideLayouts/slideLayout1.xml",
                    "slide_layout_name": "Title",
                    "slide_master_path": "ppt/slideMasters/slideMaster1.xml",
                    "slide_theme_path": "ppt/theme/theme1.xml",
                    "blocks": [
                        {"block_type": "title", "content": "Overview"},
                        {"block_type": "body", "content": "content"},
                        {"block_type": "body", "content": "content"},
                    ],
                }
            ],
        }
    )
    assert "source_pptx_path" not in sanitized
    assert "theme_manifest" not in sanitized
    assert "master_layout_manifest" not in sanitized
    assert "media_manifest" not in sanitized
    assert "slides" not in sanitized
    assert int(sanitized.get("requested_total_pages") or 0) >= 3
    assert isinstance(sanitized.get("required_facts"), list)
    assert any("Overview" in str(item) for item in (sanitized.get("required_facts") or []))


def test_generate_zero_create_sanitize_adds_required_body_block_when_missing():
    mod = _load_generate_module()
    sanitized = mod._sanitize_desc_for_zero_create(
        {
            "title": "Deck",
            "slides": [
                {
                    "page_number": 1,
                    "title": "Only Chart",
                    "blocks": [{"block_type": "chart", "content": "trend"}],
                }
            ],
        }
    )
    assert "slides" not in sanitized
    assert isinstance(sanitized.get("required_facts"), list)
    assert any("Only Chart" in str(item) for item in (sanitized.get("required_facts") or []))


def test_generate_zero_create_sanitize_body_fallback_avoids_duplicate_text():
    mod = _load_generate_module()
    sanitized = mod._sanitize_desc_for_zero_create(
        {
            "title": "Deck",
            "slides": [
                {
                    "page_number": 6,
                    "title": "3.4",
                    "blocks": [
                        {"block_type": "subtitle", "content": "3.4"},
                        {"block_type": "kpi", "content": "9"},
                    ],
                }
            ],
        }
    )
    assert "slides" not in sanitized
    required = [str(item) for item in (sanitized.get("required_facts") or [])]
    assert required
    assert any("3.4" in item for item in required)


def test_generate_zero_create_sanitize_can_keep_sanitized_slides_for_local():
    mod = _load_generate_module()
    sanitized = mod._sanitize_desc_for_zero_create(
        {
            "title": "Deck",
            "slides": [
                {
                    "page_number": 1,
                    "title": "Overview",
                    "elements": [{"type": "text", "content": "A"}],
                    "shapes": [{"type": "shape", "subtype": "rect"}],
                    "slide_layout_path": "ppt/slideLayouts/slideLayout1.xml",
                    "blocks": [{"block_type": "body", "content": "content"}],
                }
            ],
        },
        keep_sanitized_slides=True,
    )
    slides = sanitized.get("slides")
    assert isinstance(slides, list)
    assert len(slides) == 1
    slide = slides[0]
    assert isinstance(slide, dict)
    assert "elements" not in slide
    assert "shapes" not in slide
    assert "slide_layout_path" not in slide
    assert isinstance(slide.get("blocks"), list)


def test_build_reference_desc_payload_preserves_render_path_and_semantic_constraints():
    mod = _load_generate_module()
    desc = {
        "title": "Deck",
        "slides": [
            {
                "slide_id": "s1",
                "title": "Overview",
                "layout_hint": "split_2",
                "layout_grid": "split_2",
                "render_path": "svg",
                "semantic_constraints": {"media_required": True, "diagram_type": "timeline"},
                "blocks": [{"block_type": "body", "content": "content"}],
            }
        ],
    }
    payload = mod._build_reference_desc_payload(desc)
    slide = (payload.get("slides") or [])[0]
    assert slide.get("render_path") == "svg"
    assert bool((slide.get("semantic_constraints") or {}).get("media_required")) is True
    assert (slide.get("semantic_constraints") or {}).get("diagram_type") == "timeline"


def test_build_pipeline_payload_injects_focus_cluster_constraint():
    mod = _load_generate_module()
    desc = {
        "title": "Deck",
        "slides": [{"slide_id": "s1", "title": "Overview", "blocks": [{"block_type": "body", "content": "content"}]}],
        "theme": {"primary": "22223b", "secondary": "4a4e69", "accent": "9a8c98", "bg": "f2e9e4"},
    }
    payload = mod._build_pipeline_payload_from_desc(
        desc,
        execution_profile="prod_safe",
        strict_no_fallback=False,
        creation_mode="zero_create",
        focus_cluster="layout",
    )
    constraints = payload.get("constraints") or []
    assert any("layout" in str(item).lower() for item in constraints)


def test_build_pipeline_payload_preserves_input_constraints_and_required_facts():
    mod = _load_generate_module()
    desc = {
        "title": "Deck",
        "constraints": ["蹇呴』淇濈暀鍏抽敭閰嶈壊", "姣忛〉閮芥湁娓呮櫚鏍囬"],
        "required_facts": ["鍏抽敭缁撹A", "鍏抽敭鏁版嵁B"],
        "slides": [{"slide_id": "s1", "title": "Overview", "blocks": [{"block_type": "body", "content": "content"}]}],
        "theme": {"primary": "22223b", "secondary": "4a4e69", "accent": "9a8c98", "bg": "f2e9e4"},
    }
    payload = mod._build_pipeline_payload_from_desc(
        desc,
        execution_profile="prod_safe",
        strict_no_fallback=False,
        creation_mode="zero_create",
    )
    constraints = [str(item) for item in (payload.get("constraints") or [])]
    required_facts = [str(item) for item in (payload.get("required_facts") or [])]
    assert any("蹇呴』淇濈暀鍏抽敭閰嶈壊" in item for item in constraints)
    assert any("鍏抽敭缁撹A" in item for item in required_facts)


def test_collapse_issue_buckets_to_clusters():
    mod = _load_module()
    clusters = mod._collapse_issue_buckets_to_clusters(
        {"visual": 7, "image": 2, "theme": 1, "text": 3, "page_count": 1}
    )
    assert clusters["geometry"] == 7
    assert clusters["media"] == 2
    assert clusters["theme"] == 1
    assert clusters["content"] == 3
    assert clusters["layout"] == 1


def test_pick_focus_cluster_prefers_explicit_choice():
    mod = _load_module()
    focus = mod._pick_focus_cluster(
        issue_clusters={"geometry": 9, "theme": 3},
        root_cause={"primary": "skill"},
        preferred="theme",
    )
    assert focus == "theme"


def test_build_fix_plan_contains_single_cluster_protocol():
    mod = _load_module()
    plan = mod._build_fix_plan(
        phase="t3",
        status="NEEDS_IMPROVEMENT",
        score=64.3,
        active_cluster="geometry",
        recommended_cluster="layout",
        issue_clusters={"geometry": 20},
        root_cause={"primary": "skill", "confidence": 0.7},
        single_cluster_enforced=True,
    )
    assert plan["protocol"]["single_cluster_enforced"] is True
    assert plan["active_cluster"] == "geometry"
    assert plan["recommended_next_cluster"] == "layout"
    assert "layout" in plan["protocol"]["blocked_clusters"]


def test_build_visual_critic_patch_targets_low_similarity_pages():
    mod = _load_module()
    report = {
        "issues": [
            {"page": 3, "similarity": 59.2, "issue": "Slide 3 visual similarity is low (59.2%)", "severity": "error"},
            {"page": 1, "similarity": 57.8, "issue": "Slide 1 visual similarity is low (57.8%)", "severity": "error"},
            {"page": 2, "similarity": 66.1, "issue": "Slide 2 visual similarity is low (66.1%)", "severity": "warning"},
        ]
    }
    patch = mod._build_visual_critic_patch(
        report=report,
        active_cluster="geometry",
        max_pages=2,
    )
    assert patch["active_cluster"] == "geometry"
    assert patch["target_pages"] == [1, 3]
    assert isinstance(patch.get("slide_mutations"), list)
    assert len(patch["slide_mutations"]) == 2
    first = patch["slide_mutations"][0]
    assert first.get("page") == 1
    assert first.get("layout_hint") in {"split_2", "grid_3", "asymmetric_2"}
    assert first.get("render_path") in {"svg"}
    assert isinstance(first.get("template_family_whitelist"), list)
    assert len(first.get("template_family_whitelist") or []) >= 1
    assert str(first.get("template_family") or "").strip()
    assert bool(first.get("template_lock")) is True
    assert len(patch["global_constraints"]) >= 1
    execution_overrides = patch.get("execution_overrides") or {}
    assert execution_overrides.get("reconstruct_source_aligned") == "on"
    assert execution_overrides.get("reconstruct_template_shell") == "on"
    assert execution_overrides.get("force_mode") == "local"


def test_build_visual_critic_patch_zero_create_links_theme_media_clusters():
    mod = _load_module()
    report = {
        "issues": [
            {"issue": "Low theme color overlap: 33.3%", "severity": "warning"},
            {"issue": "Media asset mismatch: 2 vs 1", "severity": "warning"},
            {"page": 4, "similarity": 56.2, "issue": "Slide 4 visual similarity is low (56.2%)", "severity": "error"},
        ]
    }
    patch = mod._build_visual_critic_patch(
        report=report,
        active_cluster="geometry",
        max_pages=2,
        issue_clusters={"geometry": 20, "theme": 2, "media": 1},
        single_cluster_enforced=True,
        creation_mode="zero_create",
    )
    repair_clusters = patch.get("repair_clusters") or []
    assert "geometry" in repair_clusters
    assert "theme" in repair_clusters
    assert "media" in repair_clusters
    first = (patch.get("slide_mutations") or [{}])[0]
    whitelist = first.get("template_family_whitelist") if isinstance(first, dict) else []
    assert isinstance(whitelist, list)
    assert len(whitelist) >= 1
    assert "dashboard_dark" not in set(str(item) for item in whitelist)
    execution_overrides = patch.get("execution_overrides") or {}
    assert "restore_reference_manifests" not in execution_overrides
    assert "reconstruct_template_shell" not in execution_overrides
    assert "reconstruct_source_aligned" not in execution_overrides
    assert execution_overrides.get("force_mode") == "local"


def test_build_visual_critic_patch_zero_create_avoids_media_expansion_on_image_mismatch():
    mod = _load_module()
    report = {
        "diagnostics": {"ref_image_count": 0, "gen_image_count": 6},
        "issues": [
            {"issue": "Image count mismatch: 0 vs 6", "severity": "warning"},
            {"issue": "Media asset mismatch: 5 vs 12", "severity": "warning"},
            {"page": 4, "similarity": 56.2, "issue": "Slide 4 visual similarity is low (56.2%)", "severity": "error"},
        ],
    }
    patch = mod._build_visual_critic_patch(
        report=report,
        active_cluster="geometry",
        max_pages=2,
        issue_clusters={"geometry": 20, "media": 3},
        single_cluster_enforced=True,
        creation_mode="zero_create",
    )
    repair_clusters = patch.get("repair_clusters") or []
    assert "media" not in repair_clusters
    strategy_flags = patch.get("strategy_flags") or {}
    assert strategy_flags.get("avoid_media_expansion") is True
    execution_overrides = patch.get("execution_overrides") or {}
    assert execution_overrides.get("force_focus_cluster") != "media"


def test_apply_visual_critic_patch_to_input_updates_targets(tmp_path: Path):
    mod = _load_module()
    source = tmp_path / "input.json"
    source.write_text(
        json.dumps(
            {
                "title": "Deck",
                "slides": [
                    {"page_number": 1, "title": "A", "blocks": [], "elements": [], "shapes": []},
                    {"page_number": 2, "title": "B", "blocks": [], "elements": [], "shapes": []},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    patch = {
        "active_cluster": "geometry",
        "target_pages": [2],
        "slide_mutations": [
            {
                "page": 2,
                "layout_hint": "split_2",
                "layout_grid": "split_2",
                "render_path": "svg",
                "template_family_whitelist": ["split_media_dark", "consulting_warm_light"],
                "template_family": "split_media_dark",
                "template_lock": True,
                "semantic_constraints_patch": {"media_required": True},
                "visual_patch": {"visual_priority": True},
            }
        ],
        "global_constraints": ["fix geometry"],
        "required_facts_additions": ["repair page 2"],
    }
    out = mod._apply_visual_critic_patch_to_input(input_json_path=source, patch=patch)
    assert out["ok"] is True
    assert int(out.get("updated_fields", 0)) >= 3
    assert int(out.get("inserted_blocks", 0)) >= 1
    after = json.loads(source.read_text(encoding="utf-8"))
    assert "fix geometry" in (after.get("constraints") or [])
    assert "repair page 2" in (after.get("required_facts") or [])
    slide2 = (after.get("slides") or [])[1]
    assert slide2.get("layout_hint") == "split_2"
    assert slide2.get("layout_grid") == "split_2"
    assert slide2.get("render_path") == "svg"
    assert slide2.get("template_family") == "split_media_dark"
    assert slide2.get("template_id") == "split_media_dark"
    assert bool(slide2.get("template_lock")) is True
    assert (slide2.get("template_family_whitelist") or [])[0] == "split_media_dark"
    assert bool((slide2.get("semantic_constraints") or {}).get("media_required")) is True
    assert any(
        str((b or {}).get("block_type") or "").lower() == "image"
        for b in (slide2.get("blocks") or [])
        if isinstance(b, dict)
    )
    assert bool((slide2.get("visual") or {}).get("critic_repair", {}).get("enabled")) is True


def test_apply_visual_critic_patch_to_input_respects_avoid_media_expansion_flag(tmp_path: Path):
    mod = _load_module()
    source = tmp_path / "input.json"
    source.write_text(
        json.dumps(
            {
                "title": "Deck",
                "slides": [
                    {"page_number": 1, "title": "A", "blocks": []},
                    {"page_number": 2, "title": "B", "blocks": []},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    patch = {
        "active_cluster": "geometry",
        "creation_mode": "zero_create",
        "repair_clusters": ["geometry", "media"],
        "strategy_flags": {"avoid_media_expansion": True},
        "target_pages": [2],
        "slide_mutations": [
            {
                "page": 2,
                "layout_hint": "split_2",
                "layout_grid": "split_2",
                "visual_patch": {"visual_priority": True},
            }
        ],
        "global_constraints": [],
        "required_facts_additions": [],
    }
    out = mod._apply_visual_critic_patch_to_input(input_json_path=source, patch=patch)
    assert out["ok"] is True
    after = json.loads(source.read_text(encoding="utf-8"))
    slide2 = (after.get("slides") or [])[1]
    assert not any(
        str((b or {}).get("block_type") or (b or {}).get("type") or "").strip().lower() == "image"
        for b in (slide2.get("blocks") or [])
        if isinstance(b, dict)
    )


def test_apply_visual_critic_patch_geometry_compacts_middle_slide_blocks(tmp_path: Path):
    mod = _load_module()
    source = tmp_path / "input.json"
    source.write_text(
        json.dumps(
            {
                "title": "Deck",
                "slides": [
                    {"page_number": 1, "title": "Cover", "blocks": [{"block_type": "title", "content": "Cover"}]},
                    {
                        "page_number": 2,
                        "title": "Middle",
                        "blocks": [
                            {"block_type": "title", "content": "Long title " * 20},
                            {"block_type": "subtitle", "content": "sub"},
                            {"block_type": "body", "content": "body"},
                            {"block_type": "list", "content": "list"},
                            {"block_type": "image", "content": "img"},
                            {"block_type": "chart", "content": "chart"},
                        ],
                    },
                    {"page_number": 3, "title": "End", "blocks": [{"block_type": "title", "content": "End"}]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    patch = {
        "active_cluster": "geometry",
        "target_pages": [2],
        "slide_mutations": [{"page": 2, "layout_hint": "split_2", "layout_grid": "split_2"}],
        "global_constraints": [],
        "required_facts_additions": [],
    }
    out = mod._apply_visual_critic_patch_to_input(input_json_path=source, patch=patch)
    assert out["ok"] is True
    after = json.loads(source.read_text(encoding="utf-8"))
    blocks = ((after.get("slides") or [])[1].get("blocks") or [])
    assert len(blocks) <= 4
    assert all(str((b or {}).get("position") or "").strip() for b in blocks if isinstance(b, dict))


def test_restore_reference_shortcuts_for_repair_restores_manifests(tmp_path: Path):
    mod = _load_module()
    source = tmp_path / "input.json"
    source.write_text(
        json.dumps(
            {
                "title": "Deck",
                "slides": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    snapshot = {
        "source_pptx_path": "D:/ref.pptx",
        "theme_manifest": [{"k": "theme"}],
        "master_layout_manifest": [{"k": "layout"}],
        "media_manifest": [{"k": "media"}],
    }
    out = mod._restore_reference_shortcuts_for_repair(
        input_json_path=source,
        reference_input_snapshot=snapshot,
    )
    assert out["ok"] is True
    assert set(out["restored_keys"]) == {
        "source_pptx_path",
        "theme_manifest",
        "master_layout_manifest",
        "media_manifest",
    }
    after = json.loads(source.read_text(encoding="utf-8"))
    assert str(after.get("source_pptx_path") or "").endswith("ref.pptx")
    assert isinstance(after.get("theme_manifest"), list)
    assert isinstance(after.get("master_layout_manifest"), list)
    assert isinstance(after.get("media_manifest"), list)


def test_restore_slides_for_zero_create_local_fallback_rehydrates_sanitized_slides(tmp_path: Path):
    mod = _load_module()
    source = tmp_path / "input.json"
    source.write_text(
        json.dumps(
            {
                "title": "Deck",
                "requested_total_pages": 3,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    snapshot = {
        "slides": [
            {
                "page_number": 1,
                "title": "Overview",
                "elements": [{"type": "text", "content": "A"}],
                "shapes": [{"type": "shape", "subtype": "rect"}],
                "slide_layout_path": "ppt/slideLayouts/slideLayout1.xml",
                "blocks": [{"block_type": "body", "content": "content"}],
            }
        ]
    }
    out = mod._restore_slides_for_zero_create_local_fallback(
        input_json_path=source,
        reference_input_snapshot=snapshot,
    )
    assert out["ok"] is True
    assert int(out["restored_slide_count"]) == 1
    after = json.loads(source.read_text(encoding="utf-8"))
    slides = after.get("slides")
    assert isinstance(slides, list) and len(slides) == 1
    slide = slides[0]
    assert "elements" not in slide
    assert "shapes" not in slide
    assert "slide_layout_path" not in slide
    assert isinstance(slide.get("blocks"), list)


def test_prepare_zero_create_input_for_attempt_restores_slides_for_local_mode(tmp_path: Path):
    mod = _load_module()
    source = tmp_path / "input.json"
    source.write_text(
        json.dumps(
            {
                "title": "Deck",
                "requested_total_pages": 2,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    snapshot = {
        "slides": [
            {"page_number": 1, "title": "A", "blocks": []},
            {"page_number": 2, "title": "B", "blocks": []},
        ]
    }
    out = mod._prepare_zero_create_input_for_attempt(
        input_json_path=source,
        reference_input_snapshot=snapshot,
        attempt_mode="local",
        creation_mode="zero_create",
    )
    assert out["ok"] is True
    assert out["action"] == "restore_slides"
    assert int(out.get("restored_slide_count") or 0) == 2
    after = json.loads(source.read_text(encoding="utf-8"))
    assert isinstance(after.get("slides"), list)
    assert len(after.get("slides")) == 2


def test_prepare_zero_create_input_for_attempt_skips_when_not_local(tmp_path: Path):
    mod = _load_module()
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"title": "Deck"}, ensure_ascii=False), encoding="utf-8")
    out = mod._prepare_zero_create_input_for_attempt(
        input_json_path=source,
        reference_input_snapshot={"slides": [{"page_number": 1, "title": "A", "blocks": []}]},
        attempt_mode="api",
        creation_mode="zero_create",
    )
    assert out["ok"] is True
    assert out["action"] == "noop"
    assert out["reason"] == "not_local_mode"


def test_extract_schema_invalid_contract_slide_indexes_from_failure_report():
    mod = _load_module()
    report = {
        "failure_code": "schema_invalid",
        "failure_reason": (
            "Render contract invalid: slides[5] content contract: one of [chart|kpi] is required; "
            "slides[5] content contract: visual anchor requirement not satisfied; "
            "slides[18] content contract: one of [chart|kpi] is required"
        ),
    }
    indexes = mod._extract_schema_invalid_contract_slide_indexes(report)
    assert indexes == [5, 18]


def test_inject_chart_blocks_for_zero_create_contract_repair_adds_missing_chart(tmp_path: Path):
    mod = _load_module()
    source = tmp_path / "input.json"
    source.write_text(
        json.dumps(
            {
                "title": "Deck",
                "slides": [
                    {"page_number": 1, "blocks": [{"block_type": "body", "content": "alpha"}]},
                    {"page_number": 2, "blocks": [{"block_type": "list", "content": "beta"}]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = mod._inject_chart_blocks_for_zero_create_contract_repair(
        input_json_path=source,
        slide_indexes=[1],
    )
    assert out["ok"] is True
    assert int(out.get("inserted") or 0) == 1
    assert out.get("touched_slide_indexes") == [1]
    after = json.loads(source.read_text(encoding="utf-8"))
    slide2_blocks = ((after.get("slides") or [])[1].get("blocks") or [])
    assert any(
        str((b or {}).get("block_type") or "").strip().lower() == "chart"
        for b in slide2_blocks
        if isinstance(b, dict)
    )


def test_wait_for_path_unlock_handles_missing_and_existing_file(tmp_path: Path):
    mod = _load_module()
    missing = tmp_path / "missing.pptx"
    assert mod._wait_for_path_unlock(missing, timeout_sec=0.2, poll_sec=0.05) is True
    existing = tmp_path / "existing.pptx"
    existing.write_bytes(b"pptx")
    assert mod._wait_for_path_unlock(existing, timeout_sec=0.2, poll_sec=0.05) is True


