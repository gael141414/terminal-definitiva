"""Discovery Engine: encontrar oportunidades.

Grupo de navegación consolidado (docs/design/research_core_navegacion_kpi.html,
sección 1a): screeners, small caps, multibaggers, insiders, alt data, ETFs y
catalizadores de crecimiento. Las herramientas siguen siendo módulos propios
enrutados por modulos.tool_router; este módulo expone la tarjeta de grupo que
usa la home (modulos.app_home) y sirve de punto de referencia único para el
target_module declarado en modulos.tool_consolidation.
"""

from __future__ import annotations

from modulos.ui_components import render_navigation_group_card

GROUP_KEY = "discovery_engine"


def render_group_card(index: int | None = None) -> None:
    render_navigation_group_card(GROUP_KEY, index=index)
