import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.core.paginacion import PaginatedResponse, armar_paginacion, ParamsPaginacion


def test_paginacion_calculo_correcto():
    items = ["item1", "item2"]
    total = 45
    page = 2
    size = 10

    resp = armar_paginacion(items=items, total=total, page=page, size=size)
    assert resp.items == items
    assert resp.total == 45
    assert resp.page == 2
    assert resp.size == 10
    assert resp.pages == 5


def test_paginacion_limite_exacto_de_pagina():
    items = [f"item{i}" for i in range(10)]
    total = 40
    size = 10
    page = 4

    resp = armar_paginacion(items=items, total=total, page=page, size=size)
    assert resp.pages == 4
    assert resp.page == 4
    assert len(resp.items) == 10

    # Página 5 ya desborda
    with pytest.raises(HTTPException) as exc_info:
        armar_paginacion(items=[], total=total, page=5, size=size)
    assert exc_info.value.status_code == 422


def test_paginacion_total_cero():
    items = []
    total = 0
    page = 1
    size = 20

    resp = armar_paginacion(items=items, total=total, page=page, size=size)
    assert resp.items == []
    assert resp.total == 0
    assert resp.page == 1
    assert resp.size == 20
    assert resp.pages == 1


def test_paginacion_pagina_desbordada_lanza_422():
    total = 45
    size = 10  # 5 páginas
    page = 6

    with pytest.raises(HTTPException) as exc_info:
        armar_paginacion(items=[], total=total, page=page, size=size)
    
    assert exc_info.value.status_code == 422
    assert "fuera de rango" in exc_info.value.detail.lower()


def test_paginacion_total_cero_pagina_excedida_lanza_422():
    total = 0
    size = 20
    page = 2

    with pytest.raises(HTTPException) as exc_info:
        armar_paginacion(items=[], total=total, page=page, size=size)
    
    assert exc_info.value.status_code == 422
    assert "fuera de rango" in exc_info.value.detail.lower()


def test_paginacion_size_invalido():
    with pytest.raises(HTTPException) as exc_info:
        armar_paginacion(items=[], total=10, page=1, size=0)
    assert exc_info.value.status_code == 422


def test_params_paginacion_limites():
    # Parámetros válidos por defecto
    params = ParamsPaginacion()
    assert params.page == 1
    assert params.size == 20

    # Page < 1 rechazado
    with pytest.raises(ValidationError):
        ParamsPaginacion(page=0)

    # Size < 1 rechazado
    with pytest.raises(ValidationError):
        ParamsPaginacion(size=0)

    # Size > 100 rechazado
    with pytest.raises(ValidationError):
        ParamsPaginacion(size=101)
