from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppRuntimePaths:
    """Stable filesystem paths used by the Streamlit application."""

    app_dir: Path
    logo_path: Path
    home_bg_path: Path


@dataclass(frozen=True)
class StreamlitPageConfig:
    """Streamlit page configuration values.

    Keep this module free of Streamlit imports. The actual call to
    st.set_page_config must remain at the top of app.py, immediately after
    importing streamlit, because Streamlit requires it to be the first
    Streamlit command executed by the page.
    """

    page_title: str = "ValueQuant Terminal"
    page_icon: str = "logo.png"
    layout: str = "wide"
    initial_sidebar_state: str = "collapsed"


PAGE_CONFIG = StreamlitPageConfig()


def build_runtime_paths(app_file: str | Path) -> AppRuntimePaths:
    """Build canonical asset paths from the current application file path."""

    app_dir = Path(app_file).resolve().parent
    return AppRuntimePaths(
        app_dir=app_dir,
        logo_path=app_dir / "logo.png",
        home_bg_path=app_dir / "fondo.png",
    )
