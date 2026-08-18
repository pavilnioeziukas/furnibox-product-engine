from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


def _env(name: str, legacy_name: str | None, default: str = "") -> str:
    value = os.getenv(name)
    if value is None and legacy_name:
        value = os.getenv(legacy_name)
    return (value if value is not None else default).strip()


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _boolean(value: str, default: bool) -> bool:
    return default if not value else value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ProductEngineSettings:
    app_name: str
    brand_name: str
    brand_mark: str
    hero_eyebrow: str
    hero_title: str
    hero_description: str
    state_dir: Path
    shared_data_dir: Path
    web_secret: str
    web_password: str
    max_upload_mb: int
    environment: str
    enabled_actions: tuple[str, ...]
    action_modules: tuple[str, ...]
    show_bom_workspace: bool
    show_pricing_nav: bool

    @classmethod
    def from_env(cls, base_dir: Path) -> "ProductEngineSettings":
        brand = _env("PRODUCT_ENGINE_BRAND", None, "Furnibox")
        state_dir = Path(
            _env(
                "PRODUCT_ENGINE_STATE_DIR",
                "FURNIBOX_WEB_STATE_DIR",
                str(base_dir / "web_state"),
            )
        ).resolve()
        shared_data_dir = Path(
            _env(
                "PRODUCT_ENGINE_SHARED_DATA_DIR",
                "FURNIBOX_SHARED_DATA_DIR",
                str(state_dir / "shared_data"),
            )
        ).resolve()
        return cls(
            app_name=_env(
                "PRODUCT_ENGINE_APP_NAME", None, f"{brand} Product Engine"
            ),
            brand_name=brand,
            brand_mark=_env("PRODUCT_ENGINE_BRAND_MARK", None, brand[:1]),
            hero_eyebrow=_env(
                "PRODUCT_ENGINE_HERO_EYEBROW",
                None,
                "Production · tik skaitymas ir failų generavimas",
            ),
            hero_title=_env(
                "PRODUCT_ENGINE_HERO_TITLE",
                None,
                "Produktų ir BOM paruošimas vienoje vietoje",
            ),
            hero_description=_env(
                "PRODUCT_ENGINE_HERO_DESCRIPTION",
                None,
                "Įkelkite aktualų Reform BOM, paleiskite patikras ir "
                "atsisiųskite paruoštus Odoo importo failus.",
            ),
            state_dir=state_dir,
            shared_data_dir=shared_data_dir,
            web_secret=_env(
                "PRODUCT_ENGINE_WEB_SECRET", "FURNIBOX_WEB_SECRET"
            ),
            web_password=_env(
                "PRODUCT_ENGINE_WEB_PASSWORD", "FURNIBOX_WEB_PASSWORD"
            ),
            max_upload_mb=int(
                _env(
                    "PRODUCT_ENGINE_MAX_UPLOAD_MB",
                    "FURNIBOX_MAX_UPLOAD_MB",
                    "100",
                )
            ),
            environment=_env(
                "PRODUCT_ENGINE_ENVIRONMENT",
                "FURNIBOX_ENVIRONMENT",
                "PRODUCTION",
            ),
            enabled_actions=_csv(
                _env("PRODUCT_ENGINE_ENABLED_ACTIONS", None)
            ),
            action_modules=_csv(
                _env("PRODUCT_ENGINE_ACTION_MODULES", None)
            ),
            show_bom_workspace=_boolean(
                _env("PRODUCT_ENGINE_SHOW_BOM_WORKSPACE", None), True
            ),
            show_pricing_nav=_boolean(
                _env("PRODUCT_ENGINE_SHOW_PRICING_NAV", None), True
            ),
        )


def load_actions(
    builtins: Mapping[str, dict[str, Any]],
    *,
    enabled_actions: tuple[str, ...] = (),
    action_modules: tuple[str, ...] = (),
) -> dict[str, dict[str, Any]]:
    actions = {key: dict(value) for key, value in builtins.items()}
    for module_name in action_modules:
        module = importlib.import_module(module_name)
        additions = (
            module.register_actions()
            if hasattr(module, "register_actions")
            else getattr(module, "ACTIONS")
        )
        overlap = actions.keys() & additions.keys()
        if overlap:
            raise ValueError(
                "Pasikartojantys Product Engine veiksmai: "
                + ", ".join(sorted(overlap))
            )
        actions.update({key: dict(value) for key, value in additions.items()})

    if not enabled_actions:
        return actions
    unknown = set(enabled_actions) - actions.keys()
    if unknown:
        raise ValueError(
            "Nežinomi Product Engine veiksmai: "
            + ", ".join(sorted(unknown))
        )
    return {key: actions[key] for key in enabled_actions}
