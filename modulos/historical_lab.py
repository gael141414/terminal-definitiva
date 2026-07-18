"""Historical Lab: validación histórica de estrategias y score.

Grupo de navegación consolidado (docs/design/research_core_navegacion_kpi.html,
sección 1a): backtesting, máquina del tiempo, stress test de crisis y predictor
de techos/suelos. Las herramientas siguen siendo módulos propios enrutados por
modulos.tool_router; este módulo expone la tarjeta de grupo que usa la home
(modulos.app_home) y sirve de punto de referencia único para el target_module
declarado en modulos.tool_consolidation.
"""

from __future__ import annotations

from modulos.ui_components import render_navigation_group_card

GROUP_KEY = "historical_lab"


def render_group_card(index: int | None = None) -> None:
    render_navigation_group_card(GROUP_KEY, index=index)
