"""Emisión segura de HTML a través de ``st.markdown``.

Streamlit no inyecta el HTML tal cual: primero lo pasa por su intérprete de
Markdown. Y en Markdown (CommonMark, bloque HTML de tipo 6) **una línea en
blanco cierra el bloque HTML**. Todo lo que venga después deja de tratarse como
HTML: si además está sangrado cuatro espacios o más, Markdown lo interpreta como
un bloque de código y lo pinta como texto literal en pantalla.

Las plantillas de este proyecto son f-strings multilínea sangradas que
interpolan fragmentos opcionales en su propia línea::

    <div style="...">
        {tag_html}          <-- si tag_html == "", queda una línea de espacios
        ...
    </div>                  <-- a partir de aquí, texto literal

Cuando ese fragmento venía vacío (una tarjeta KPI sin delta, una cabecera sin
insignias, una rejilla sin elementos), el usuario veía los ``</div>`` y los
``<div style="...">`` escritos en crudo sobre la interfaz.

``compactar_html`` aplana el bloque a una sola línea, con lo que desaparecen a
la vez las dos causas: no puede quedar ninguna línea en blanco intermedia y no
queda sangría que Markdown pueda confundir con código. Se unen las líneas con un
espacio porque las plantillas parten atributos CSS largos entre líneas y ahí el
separador es necesario (``border:1px solid X;`` + ``border-radius:10px``).

No usar con HTML donde los espacios sean significativos (``<pre>``,
``<textarea>``, ``white-space: pre``); para eso, ``st.markdown`` directo con la
plantilla ya escrita en una sola línea.
"""

from __future__ import annotations

import streamlit as st

__all__ = ["compactar_html", "escribir_html"]


def compactar_html(bloque: str) -> str:
    """Aplana un bloque HTML a una línea, sin líneas vacías ni sangría."""
    return " ".join(linea.strip() for linea in str(bloque).splitlines() if linea.strip())


def escribir_html(bloque: str) -> None:
    """Escribe HTML por ``st.markdown`` sin que Markdown pueda romperlo."""
    st.markdown(compactar_html(bloque), unsafe_allow_html=True)
