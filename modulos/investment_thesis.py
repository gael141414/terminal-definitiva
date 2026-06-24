"""Motor de tesis de inversión para ValueQuant Terminal.

Este módulo convierte el ValueQuant Score, la valoración y las banderas rojas en
una tesis operativa estructurada. No ejecuta órdenes ni constituye asesoramiento
financiero personalizado; genera un marco de análisis para revisión humana.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any

import pandas as pd
import streamlit as st

from modulos.valuation_sensitivity import render_valuation_sensitivity


@dataclass
class ThesisSection:
    """Bloque textual dentro de la tesis."""

    title: str
    bullets: list[str] = field(default_factory=list)


@dataclass
class ValuationScenario:
    """Escenario de valoración usado para tesis y entrada."""

    name: str
    price: float | None
    description: str


@dataclass
class InvestmentThesis:
    """Resultado estructurado de tesis operativa."""

    ticker: str
    action: str
    action_detail: str
    final_score: float | None
    quality_score: float | None
    valuation_score: float | None
    risk_score: float | None
    growth_score: float | None
    buffett_score: float | None
    current_price: float | None
    intrinsic_value: float | None
    margin_of_safety: float | None
    conservative_entry_price: float | None
    reasonable_entry_price: float | None
    deep_value_entry_price: float | None
    expected_upside: float | None
    fcf_yield: float | None
    earnings_yield: float | None
    pe_actual: float | None
    pfcf_actual: float | None
    valuation_regime: str
    valuation_comment: str
    valuation_scenarios: list[ValuationScenario] = field(default_factory=list)
    positives: list[str] = field(default_factory=list)
    negatives: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    sections: list[ThesisSection] = field(default_factory=list)


def _as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return None
        return number
    except Exception:
        return None


def _score_attr(valuequant_score: Any, attr: str, default: Any = None) -> Any:
    if valuequant_score is None:
        return default
    return getattr(valuequant_score, attr, default)


def _component_score(valuequant_score: Any, component_name: str) -> float | None:
    components = _score_attr(valuequant_score, "components", []) or []
    target = component_name.lower()
    for component in components:
        name = str(getattr(component, "name", "")).lower()
        if target in name:
            return _as_float(getattr(component, "score", None))
    return None


def _first_numeric(source: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = _as_float(source.get(key))
        if value is not None:
            return value
    return None


def _positive_values(values: list[float | None]) -> list[float]:
    return [float(value) for value in values if value is not None and value > 0]


def _extract_valuation_inputs(res_val: dict[str, Any] | None) -> dict[str, float | None]:
    """Extrae inputs de valoración tolerando nombres de claves distintos."""

    if not isinstance(res_val, dict):
        return {
            "current_price": None,
            "intrinsic_value": None,
            "dcf_value": None,
            "epv_value": None,
            "graham_value": None,
            "lynch_value": None,
            "precio_seguridad_25": None,
            "fcf_yield": None,
            "earnings_yield": None,
            "pe_actual": None,
            "pfcf_actual": None,
        }

    current_price = _first_numeric(
        res_val,
        ["precio_actual", "current_price", "price", "precio", "market_price"],
    )
    dcf_value = _first_numeric(res_val, ["dcf_value", "valor_dcf", "valor_intrinseco_dcf"])
    epv_value = _first_numeric(res_val, ["epv_value", "earnings_power_value"])
    graham_value = _first_numeric(res_val, ["graham_value", "graham_number", "valor_graham"])
    lynch_value = _first_numeric(res_val, ["lynch_value", "valor_lynch"])

    explicit_intrinsic = _first_numeric(
        res_val,
        [
            "valor_intrinseco",
            "intrinsic_value",
            "precio_objetivo",
            "target_price",
            "fair_value",
            "valor_razonable",
        ],
    )

    valuation_values = _positive_values([dcf_value, epv_value, graham_value, lynch_value])
    if explicit_intrinsic is not None and explicit_intrinsic > 0:
        intrinsic_value = explicit_intrinsic
    elif valuation_values:
        intrinsic_value = float(median(valuation_values))
    else:
        intrinsic_value = None

    return {
        "current_price": current_price,
        "intrinsic_value": intrinsic_value,
        "dcf_value": dcf_value,
        "epv_value": epv_value,
        "graham_value": graham_value,
        "lynch_value": lynch_value,
        "precio_seguridad_25": _first_numeric(res_val, ["precio_seguridad_25", "margin_price", "safety_price"]),
        "fcf_yield": _first_numeric(res_val, ["fcf_yield", "freeCashFlowYield", "free_cash_flow_yield"]),
        "earnings_yield": _first_numeric(res_val, ["earnings_yield", "earningsYield"]),
        "pe_actual": _first_numeric(res_val, ["pe_actual", "peRatio", "priceEarningsRatio"]),
        "pfcf_actual": _first_numeric(res_val, ["pfcf_actual", "pfcfRatio", "priceToFreeCashFlow"]),
    }


def _margin(current_price: float | None, intrinsic_value: float | None) -> float | None:
    if current_price is None or intrinsic_value is None or current_price <= 0:
        return None
    return intrinsic_value / current_price - 1.0


def _fmt_score(value: float | None) -> str:
    return f"{value:.1f}/100" if value is not None else "N/D"


def _fmt_money(value: float | None) -> str:
    return f"${value:,.2f}" if value is not None else "N/D"


def _fmt_pct(value: float | None) -> str:
    return f"{value * 100:+.1f}%" if value is not None else "N/D"


def _fmt_ratio(value: float | None) -> str:
    return f"{value:.1f}x" if value is not None else "N/D"


def _valuation_regime(
    margin_of_safety: float | None,
    valuation_score: float | None,
    fcf_yield: float | None,
) -> tuple[str, str]:
    valuation = valuation_score if valuation_score is not None else 50.0

    if margin_of_safety is not None:
        if margin_of_safety >= 0.25:
            return "Infravalorada", "El precio ofrece margen de seguridad amplio frente al valor razonable estimado."
        if margin_of_safety >= 0.10:
            return "Zona de estudio", "El margen de seguridad es positivo, pero requiere validar supuestos antes de comprar."
        if margin_of_safety >= -0.10:
            return "Valor razonable", "El precio está cerca del valor razonable; la decisión depende más de calidad y catalizadores."
        if margin_of_safety >= -0.25:
            return "Exigente", "El precio descuenta buena parte de la tesis; conviene esperar mejor entrada."
        return "Muy exigente", "La cotización está claramente por encima del valor estimado; el riesgo de pagar demasiado es elevado."

    if fcf_yield is not None:
        if fcf_yield >= 0.06:
            return "Atractiva por FCF", "El FCF yield sugiere una valoración razonable si el flujo de caja es sostenible."
        if fcf_yield < 0.025:
            return "Exigente por FCF", "El FCF yield es bajo; la tesis depende de crecimiento futuro y múltiplos altos."

    if valuation < 35:
        return "Exigente", "El bloque de valoración del score penaliza precio, múltiplos o margen de seguridad."
    if valuation >= 65:
        return "Razonable", "El bloque de valoración es favorable frente al resto de componentes."
    return "No concluyente", "La valoración no es suficientemente clara; requiere revisión manual."


def _build_scenarios(inputs: dict[str, float | None]) -> list[ValuationScenario]:
    current_price = inputs.get("current_price")
    base = inputs.get("intrinsic_value")
    safety_25 = inputs.get("precio_seguridad_25")
    values = _positive_values(
        [
            inputs.get("dcf_value"),
            inputs.get("epv_value"),
            inputs.get("graham_value"),
            inputs.get("lynch_value"),
        ]
    )

    if values:
        low = min(values)
        high = max(values)
    elif base is not None:
        low = base * 0.80
        high = base * 1.20
    else:
        low = None
        high = None

    if safety_25 is not None and safety_25 > 0:
        low = min(low, safety_25) if low is not None else safety_25

    if base is None and values:
        base = float(median(values))

    scenarios = [
        ValuationScenario("Conservador", low, "Escenario prudente: usa el menor valor razonable disponible o precio con margen de seguridad."),
        ValuationScenario("Base", base, "Escenario central: valor intrínseco o mediana de métodos disponibles."),
        ValuationScenario("Optimista", high, "Escenario favorable: asume que se materializan calidad, crecimiento y múltiplos razonables."),
    ]

    if current_price is not None:
        scenarios.insert(0, ValuationScenario("Precio actual", current_price, "Cotización usada como referencia de entrada."))
    return scenarios


def _decision(
    final_score: float | None,
    quality_score: float | None,
    valuation_score: float | None,
    risk_score: float | None,
    margin_of_safety: float | None,
    fcf_yield: float | None,
    valuation_regime: str,
    red_flags: list[str],
) -> tuple[str, str]:
    """Clasificación operativa: Comprar / Vigilar / Mantener / Evitar.

    La decisión es deliberadamente exigente: una empresa de calidad puede quedar
    en Vigilar si la valoración no ofrece margen de seguridad.
    """

    score = final_score if final_score is not None else 0.0
    quality = quality_score if quality_score is not None else 50.0
    valuation = valuation_score if valuation_score is not None else 50.0
    risk = risk_score if risk_score is not None else 50.0
    margin = margin_of_safety if margin_of_safety is not None else None
    fcf = fcf_yield if fcf_yield is not None else None

    severe_red_flags = len(red_flags) >= 3 or risk < 35
    very_expensive = valuation_regime == "Muy exigente" or (margin is not None and margin <= -0.30)
    weak_fcf_value = fcf is not None and fcf < 0.025

    if severe_red_flags:
        return (
            "Evitar",
            "El perfil de riesgo o las banderas rojas obligan a descartar la operación hasta revisar datos, balance y calidad contable.",
        )

    if very_expensive and valuation < 40:
        return (
            "Evitar",
            "La empresa puede ser buena, pero el precio está demasiado alejado del valor razonable estimado.",
        )

    has_clear_margin = margin is not None and margin >= 0.15
    has_acceptable_margin = margin is not None and margin >= 0.08
    has_fcf_support = fcf is not None and fcf >= 0.045

    if score >= 78 and quality >= 75 and risk >= 60 and valuation >= 45 and (has_clear_margin or (has_acceptable_margin and has_fcf_support)):
        return (
            "Comprar / estudiar compra",
            "La combinación de calidad, riesgo controlado, valoración y margen de seguridad justifica análisis final de entrada.",
        )

    if score >= 68 and quality >= 72 and risk >= 55:
        if valuation >= 45 and (has_acceptable_margin or has_fcf_support):
            return (
                "Vigilar",
                "La empresa es candidata a compra, pero exige confirmar valoración, supuestos y zona exacta de entrada.",
            )
        return (
            "Vigilar",
            "La calidad es atractiva, pero el precio o el margen de seguridad todavía no compensan suficientemente.",
        )

    if score >= 55 and not weak_fcf_value:
        return (
            "Mantener / neutral",
            "El modelo no detecta ventaja suficiente para priorizar compra; conviene observar evolución de fundamentales y precio.",
        )

    return (
        "Evitar",
        "La puntuación agregada no compensa el riesgo, la valoración o la falta de calidad detectada.",
    )


def build_investment_thesis(
    ticker: str,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None = None,
) -> InvestmentThesis:
    """Construye una tesis estructurada desde los outputs del análisis."""

    final_score = _as_float(_score_attr(valuequant_score, "final_score"))
    quality_score = _component_score(valuequant_score, "calidad")
    valuation_score = _component_score(valuequant_score, "valoración")
    risk_score = _component_score(valuequant_score, "riesgo")
    growth_score = _component_score(valuequant_score, "crecimiento")
    buffett_score = _as_float(nota_buffett)

    positives = list(_score_attr(valuequant_score, "positives", []) or [])[:6]
    negatives = list(_score_attr(valuequant_score, "negatives", []) or [])[:6]
    red_flags = list(_score_attr(valuequant_score, "red_flags", []) or [])[:6]

    valuation_inputs = _extract_valuation_inputs(res_val)
    current_price = valuation_inputs["current_price"]
    intrinsic_value = valuation_inputs["intrinsic_value"]
    margin_of_safety = _margin(current_price, intrinsic_value)
    expected_upside = margin_of_safety
    fcf_yield = valuation_inputs["fcf_yield"]
    earnings_yield = valuation_inputs["earnings_yield"]
    pe_actual = valuation_inputs["pe_actual"]
    pfcf_actual = valuation_inputs["pfcf_actual"]

    valuation_regime, valuation_comment = _valuation_regime(margin_of_safety, valuation_score, fcf_yield)
    valuation_scenarios = _build_scenarios(valuation_inputs)

    conservative_entry_price = intrinsic_value * 0.75 if intrinsic_value is not None else None
    reasonable_entry_price = intrinsic_value * 0.85 if intrinsic_value is not None else None
    deep_value_entry_price = intrinsic_value * 0.65 if intrinsic_value is not None else None

    action, action_detail = _decision(
        final_score,
        quality_score,
        valuation_score,
        risk_score,
        margin_of_safety,
        fcf_yield,
        valuation_regime,
        red_flags,
    )

    bull_case: list[str] = []
    bear_case: list[str] = []
    valuation_notes: list[str] = []
    entry_conditions: list[str] = []
    exit_conditions: list[str] = []

    if quality_score is not None:
        bull_case.append("Calidad fundamental elevada." if quality_score >= 75 else "Calidad fundamental mejorable; requiere validación manual.")
    if growth_score is not None:
        bull_case.append("Crecimiento/catalizadores favorables." if growth_score >= 65 else "Catalizadores todavía poco concluyentes.")
    if risk_score is not None:
        if risk_score >= 70:
            bull_case.append("Riesgo financiero/forense contenido.")
        elif risk_score < 50:
            bear_case.append("Riesgo financiero o contable relevante.")

    valuation_notes.append(f"Régimen de valoración: {valuation_regime}. {valuation_comment}")
    if margin_of_safety is not None:
        if margin_of_safety >= 0.10:
            bull_case.append(f"Margen de seguridad positivo de {_fmt_pct(margin_of_safety)} frente al valor razonable estimado.")
        elif margin_of_safety < 0:
            bear_case.append(f"El precio está por encima del valor razonable estimado ({_fmt_pct(margin_of_safety)} de margen).")
    if valuation_score is not None and valuation_score < 35:
        bear_case.append("Valoración exigente según el componente de valoración del ValueQuant Score.")
    if fcf_yield is not None:
        valuation_notes.append(f"FCF yield estimado: {_fmt_pct(fcf_yield)}.")
        if fcf_yield >= 0.06:
            bull_case.append("FCF yield atractivo si el flujo de caja es sostenible.")
        elif fcf_yield < 0.025:
            bear_case.append("FCF yield bajo; la tesis depende de crecimiento futuro o múltiplos elevados.")
    if pe_actual is not None:
        valuation_notes.append(f"PER actual aproximado: {_fmt_ratio(pe_actual)}.")
    if pfcf_actual is not None:
        valuation_notes.append(f"P/FCF actual aproximado: {_fmt_ratio(pfcf_actual)}.")

    if positives:
        bull_case.extend(positives[:3])
    if negatives:
        bear_case.extend(negatives[:3])
    if red_flags:
        bear_case.extend([f"Bandera roja: {flag}" for flag in red_flags[:3]])

    if reasonable_entry_price is not None:
        entry_conditions.append(f"Zona razonable de estudio: por debajo de {_fmt_money(reasonable_entry_price)}.")
    if conservative_entry_price is not None:
        entry_conditions.append(f"Zona conservadora: por debajo de {_fmt_money(conservative_entry_price)}.")
    if deep_value_entry_price is not None:
        entry_conditions.append(f"Zona de oportunidad fuerte: por debajo de {_fmt_money(deep_value_entry_price)}.")
    if margin_of_safety is not None and margin_of_safety < 0:
        entry_conditions.append("Esperar caída de precio o revisión al alza del valor intrínseco antes de priorizar compra.")
    if fcf_yield is not None and fcf_yield < 0.03:
        entry_conditions.append("Exigir mayor FCF yield o crecimiento visible antes de pagar múltiplos altos.")
    entry_conditions.append("Confirmar que el DCF/valor intrínseco usa supuestos prudentes de crecimiento, margen, reinversión y WACC.")

    exit_conditions.extend(
        [
            "Deterioro persistente de FCF, márgenes o ROIC.",
            "Aumento material de deuda neta o dilución no justificada.",
            "ValueQuant Score cae por debajo de 50 o aparecen nuevas banderas rojas.",
            "La cotización supera claramente el escenario optimista sin mejora equivalente en fundamentales.",
            "El margen de seguridad desaparece por subida de precio o rebaja del valor intrínseco.",
        ]
    )

    sections = [
        ThesisSection("Tesis alcista", bull_case or ["No hay suficientes argumentos alcistas automáticos."]),
        ThesisSection("Tesis bajista / riesgos", bear_case or ["No se han detectado riesgos destacados en el resumen automático."]),
        ThesisSection("Lectura de valoración", valuation_notes),
        ThesisSection("Condiciones de entrada", entry_conditions),
        ThesisSection("Condiciones de salida o revisión", exit_conditions),
    ]

    return InvestmentThesis(
        ticker=ticker,
        action=action,
        action_detail=action_detail,
        final_score=final_score,
        quality_score=quality_score,
        valuation_score=valuation_score,
        risk_score=risk_score,
        growth_score=growth_score,
        buffett_score=buffett_score,
        current_price=current_price,
        intrinsic_value=intrinsic_value,
        margin_of_safety=margin_of_safety,
        conservative_entry_price=conservative_entry_price,
        reasonable_entry_price=reasonable_entry_price,
        deep_value_entry_price=deep_value_entry_price,
        expected_upside=expected_upside,
        fcf_yield=fcf_yield,
        earnings_yield=earnings_yield,
        pe_actual=pe_actual,
        pfcf_actual=pfcf_actual,
        valuation_regime=valuation_regime,
        valuation_comment=valuation_comment,
        valuation_scenarios=valuation_scenarios,
        positives=positives,
        negatives=negatives,
        red_flags=red_flags,
        sections=sections,
    )


def thesis_to_markdown(thesis: InvestmentThesis, competitor: str | None = None) -> str:
    """Exporta la tesis a Markdown para informe."""

    lines = [
        f"# Tesis de inversión — {thesis.ticker}",
        "",
        "> Documento generado automáticamente por ValueQuant Terminal. No constituye asesoramiento financiero personalizado.",
        "",
        f"**Acción operativa:** {thesis.action}",
        f"**Detalle:** {thesis.action_detail}",
    ]
    if competitor:
        lines.append(f"**Comparador:** {competitor}")
    lines.extend(
        [
            "",
            "## Métricas principales",
            f"- ValueQuant Score: {_fmt_score(thesis.final_score)}",
            f"- Buffett Quality: {_fmt_score(thesis.buffett_score)}",
            f"- Calidad: {_fmt_score(thesis.quality_score)}",
            f"- Valoración: {_fmt_score(thesis.valuation_score)}",
            f"- Riesgo: {_fmt_score(thesis.risk_score)}",
            f"- Crecimiento: {_fmt_score(thesis.growth_score)}",
            f"- Precio actual: {_fmt_money(thesis.current_price)}",
            f"- Valor intrínseco / objetivo: {_fmt_money(thesis.intrinsic_value)}",
            f"- Margen de seguridad estimado: {_fmt_pct(thesis.margin_of_safety)}",
            f"- FCF Yield: {_fmt_pct(thesis.fcf_yield)}",
            f"- Earnings Yield: {_fmt_pct(thesis.earnings_yield)}",
            f"- PER: {_fmt_ratio(thesis.pe_actual)}",
            f"- P/FCF: {_fmt_ratio(thesis.pfcf_actual)}",
            f"- Régimen de valoración: {thesis.valuation_regime}",
            f"- Zona razonable de entrada: {_fmt_money(thesis.reasonable_entry_price)}",
            f"- Zona conservadora de entrada: {_fmt_money(thesis.conservative_entry_price)}",
            f"- Zona de oportunidad fuerte: {_fmt_money(thesis.deep_value_entry_price)}",
            "",
            "## Escenarios de valoración",
            "| Escenario | Precio | Lectura |",
            "| --- | --- | --- |",
        ]
    )
    for scenario in thesis.valuation_scenarios:
        lines.append(f"| {scenario.name} | {_fmt_money(scenario.price)} | {scenario.description} |")
    lines.append("")

    for section in thesis.sections:
        lines.append(f"## {section.title}")
        for bullet in section.bullets:
            lines.append(f"- {bullet}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _scenario_dataframe(thesis: InvestmentThesis) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for scenario in thesis.valuation_scenarios:
        upside = _margin(thesis.current_price, scenario.price)
        rows.append(
            {
                "Escenario": scenario.name,
                "Precio/valor": _fmt_money(scenario.price),
                "Potencial vs actual": _fmt_pct(upside),
                "Lectura": scenario.description,
            }
        )
    return pd.DataFrame(rows)


def render_investment_thesis(
    ticker: str,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None = None,
    ticker_competidor: str | None = None,
) -> InvestmentThesis:
    """Renderiza la tesis profesional dentro de Streamlit."""

    thesis = build_investment_thesis(ticker, valuequant_score, res_val, nota_buffett)

    st.markdown("### Tesis de inversión")
    st.caption(
        "Lectura operativa generada desde fundamentales, valoración, riesgo y score. "
        "Debe validarse manualmente antes de cualquier decisión real."
    )

    st.info(f"**Acción operativa:** {thesis.action}. {thesis.action_detail}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ValueQuant", _fmt_score(thesis.final_score))
    c2.metric("Calidad", _fmt_score(thesis.quality_score))
    c3.metric("Valoración", _fmt_score(thesis.valuation_score))
    c4.metric("Riesgo", _fmt_score(thesis.risk_score))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Precio actual", _fmt_money(thesis.current_price))
    c6.metric("Valor razonable", _fmt_money(thesis.intrinsic_value))
    c7.metric("Margen seguridad", _fmt_pct(thesis.margin_of_safety))
    c8.metric("FCF Yield", _fmt_pct(thesis.fcf_yield))

    c9, c10, c11, c12 = st.columns(4)
    c9.metric("Entrada razonable", _fmt_money(thesis.reasonable_entry_price))
    c10.metric("Entrada conservadora", _fmt_money(thesis.conservative_entry_price))
    c11.metric("PER", _fmt_ratio(thesis.pe_actual))
    c12.metric("P/FCF", _fmt_ratio(thesis.pfcf_actual))

    st.caption(f"**Régimen de valoración:** {thesis.valuation_regime}. {thesis.valuation_comment}")

    tabs = st.tabs(["Tesis", "Valoración", "Entrada/Salida", "Riesgos", "Exportar"])

    with tabs[0]:
        col_a, col_b = st.columns(2)
        with col_a:
            section = thesis.sections[0]
            st.markdown(f"#### {section.title}")
            for bullet in section.bullets:
                st.write(f"- {bullet}")
        with col_b:
            section = thesis.sections[1]
            st.markdown(f"#### {section.title}")
            for bullet in section.bullets:
                st.write(f"- {bullet}")

    with tabs[1]:
        st.markdown("#### Escenarios de valoración")
        st.dataframe(_scenario_dataframe(thesis), use_container_width=True, hide_index=True)

        render_valuation_sensitivity(thesis)
        st.markdown("#### Lectura de valoración")
        for bullet in thesis.sections[2].bullets:
            st.write(f"- {bullet}")

    with tabs[2]:
        col_a, col_b = st.columns(2)
        with col_a:
            section = thesis.sections[3]
            st.markdown(f"#### {section.title}")
            for bullet in section.bullets:
                st.write(f"- {bullet}")
        with col_b:
            section = thesis.sections[4]
            st.markdown(f"#### {section.title}")
            for bullet in section.bullets:
                st.write(f"- {bullet}")

    with tabs[3]:
        if thesis.red_flags:
            st.error("Banderas rojas detectadas")
            for flag in thesis.red_flags:
                st.write(f"- {flag}")
        else:
            st.success("No hay banderas rojas principales en el score agregado.")

        if thesis.negatives:
            st.markdown("#### Puntos débiles")
            for item in thesis.negatives:
                st.write(f"- {item}")

    with tabs[4]:
        markdown = thesis_to_markdown(thesis, ticker_competidor)
        st.download_button(
            "Descargar tesis en Markdown",
            data=markdown,
            file_name=f"tesis_{ticker.lower()}.md",
            mime="text/markdown",
        )
        st.code(markdown, language="markdown")

    return thesis
