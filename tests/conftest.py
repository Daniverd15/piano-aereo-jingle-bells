"""Las pruebas nunca escriben en la carpeta del proyecto: todo va a un directorio temporal."""

import pytest

from piano_aereo import ajustes, grabacion, sesion


@pytest.fixture(autouse=True)
def carpetas_temporales(tmp_path, monkeypatch):
    monkeypatch.setattr(grabacion, "CARPETA", tmp_path / "grabaciones")
    monkeypatch.setattr(sesion, "CARPETA", tmp_path / "grabaciones")
    monkeypatch.setattr(ajustes, "RUTA", tmp_path / "ajustes.json")
    return tmp_path
