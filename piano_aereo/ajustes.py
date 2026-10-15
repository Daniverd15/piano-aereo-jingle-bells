"""Ajustes que se recuerdan entre sesiones, en ``ajustes.json``.

Así la configuración elegida en casa (forma de tocar, sensibilidad, corrección
de retraso…) sigue igual al abrir la aplicación en clase. Con
``--ajustes-de-fabrica`` se ignora el archivo.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from . import config

log = logging.getLogger(__name__)

RUTA = config.RAIZ / "ajustes.json"


def _valido(clave: str, valor: Any) -> bool:
    if clave == "sensibilidad":
        return isinstance(valor, (int, float)) and config.SENSIBILIDAD_MIN <= valor <= config.SENSIBILIDAD_MAX
    if clave == "retraso_camara":
        return isinstance(valor, (int, float)) and 0.0 <= valor <= config.RETRASO_MAX
    if clave == "timbre":
        return valor in config.TIMBRES
    if clave == "dificultad":
        return valor in config.DIFICULTADES
    if clave in ("cinco_dedos", "asistencia", "acompanar"):
        return isinstance(valor, bool)
    return False


def cargar(ruta: Optional[Path] = None) -> Dict[str, Any]:
    """Lee los ajustes guardados; descarta lo que falte, sobre o no tenga sentido."""
    ruta = ruta if ruta is not None else RUTA
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("No se pudieron leer los ajustes (%s): se usan los de fábrica", exc)
        return {}
    if not isinstance(datos, dict):
        return {}
    return {clave: valor for clave, valor in datos.items() if _valido(clave, valor)}


def guardar(datos: Dict[str, Any], ruta: Optional[Path] = None) -> None:
    ruta = ruta if ruta is not None else RUTA
    try:
        ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        log.warning("No se pudieron guardar los ajustes: %s", exc)
