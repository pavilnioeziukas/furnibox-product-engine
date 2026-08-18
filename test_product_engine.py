from pathlib import Path
from types import ModuleType

import pytest

from webapp.product_engine import ProductEngineSettings, load_actions


def test_generic_settings_override_legacy_furnibox_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("FURNIBOX_WEB_PASSWORD", "legacy")
    monkeypatch.setenv("PRODUCT_ENGINE_BRAND", "Furnix")
    monkeypatch.setenv("PRODUCT_ENGINE_WEB_PASSWORD", "furnix-secret")
    monkeypatch.setenv("PRODUCT_ENGINE_STATE_DIR", str(tmp_path / "furnix"))
    monkeypatch.setenv("PRODUCT_ENGINE_ENABLED_ACTIONS", "stock, diagnostics")
    monkeypatch.setenv("PRODUCT_ENGINE_SHOW_PRICING_NAV", "false")

    settings = ProductEngineSettings.from_env(Path("."))

    assert settings.app_name == "Furnix Product Engine"
    assert settings.web_password == "furnix-secret"
    assert settings.enabled_actions == ("stock", "diagnostics")
    assert settings.show_pricing_nav is False


def test_legacy_furnibox_environment_remains_supported(monkeypatch, tmp_path):
    monkeypatch.delenv("PRODUCT_ENGINE_STATE_DIR", raising=False)
    monkeypatch.delenv("PRODUCT_ENGINE_WEB_PASSWORD", raising=False)
    monkeypatch.setenv("FURNIBOX_WEB_STATE_DIR", str(tmp_path / "legacy"))
    monkeypatch.setenv("FURNIBOX_WEB_PASSWORD", "legacy-secret")

    settings = ProductEngineSettings.from_env(Path("."))

    assert settings.brand_name == "Furnibox"
    assert settings.state_dir == (tmp_path / "legacy").resolve()
    assert settings.web_password == "legacy-secret"


def test_action_modules_extend_catalog_and_select_enabled_actions(monkeypatch):
    plugin = ModuleType("test_product_engine_plugin")
    plugin.ACTIONS = {"furnix_stock": {"title": "Furnix stock"}}
    monkeypatch.setitem(__import__("sys").modules, plugin.__name__, plugin)

    actions = load_actions(
        {"builtin": {"title": "Builtin"}},
        enabled_actions=("furnix_stock",),
        action_modules=(plugin.__name__,),
    )

    assert list(actions) == ["furnix_stock"]


def test_action_modules_cannot_replace_existing_action(monkeypatch):
    plugin = ModuleType("duplicate_product_engine_plugin")
    plugin.ACTIONS = {"stock": {"title": "Replacement"}}
    monkeypatch.setitem(__import__("sys").modules, plugin.__name__, plugin)

    with pytest.raises(ValueError, match="Pasikartojantys"):
        load_actions(
            {"stock": {"title": "Original"}},
            action_modules=(plugin.__name__,),
        )
