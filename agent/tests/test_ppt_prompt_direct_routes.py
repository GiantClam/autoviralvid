from __future__ import annotations

import src.ppt_routes as routes


def test_legacy_pipeline_route_removed() -> None:
    route_paths = {route.path for route in routes.router.routes}
    assert "/api/v1/ppt/pipeline" not in route_paths


def test_prompt_direct_route_present() -> None:
    route_paths = {route.path for route in routes.router.routes}
    assert "/api/v1/ppt/generate-from-prompt" in route_paths
