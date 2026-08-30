from __future__ import annotations

import importlib.util
from pathlib import Path

from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product


def _config(tmp_path: Path) -> LocalProductConfig:
    product_root = tmp_path / "DynamicSubjectAgent"
    return LocalProductConfig(
        product_parent=product_root / "m0" / "experiments",
        state_path=product_root / "state.json",
        relationship_mode="dynamic",
    )


def test_local_product_creates_and_reopens_the_same_authority(tmp_path: Path) -> None:
    config = _config(tmp_path)
    first = open_local_product(config, cognition=DormantDeepSeekCognition())
    try:
        profile_id = first.profile_id
        timeline_id = first.timeline_id
        assert config.state_path.is_file()
    finally:
        first.close()

    second = open_local_product(config, cognition=DormantDeepSeekCognition())
    try:
        assert second.profile_id == profile_id
        assert second.timeline_id == timeline_id
    finally:
        second.close()


def test_desktop_adapter_uses_only_the_product_opening_seam() -> None:
    server_path = Path(__file__).resolve().parents[1] / "app" / "desktop" / "server.py"
    source = server_path.read_text(encoding="utf-8")
    assert "sys.path" not in source
    assert "ds_key.txt" not in source
    for internal_name in (
        "SubjectStudio",
        "RuntimeHost",
        "QualifiedRuntimeInput",
        "StudioRootRef",
        "DeepSeekUrlLibTransport",
    ):
        assert internal_name not in source

    spec = importlib.util.spec_from_file_location("desktop_server_test", server_path)
    assert spec is not None and spec.loader is not None
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    assert callable(server.build_product)
