import random
from datetime import date, time
from decimal import Decimal

import pytest
from openpyxl import Workbook

from ficha import gerar_dados, leitura, validacao
from ficha.modelo import Faixa, Ficha, Pessoa


@pytest.fixture(scope="module")
def fichas(tmp_path_factory):
    return gerar_dados.gerar(tmp_path_factory.mktemp("entrada"))


def test_ficha_valida(fichas):
    ficha, problemas = leitura.ler(fichas[0])
    assert ficha.gravadora == "Selo Pedra Azul" and ficha.data_envio == date(2026, 3, 2)
    assert [f.numero for f in ficha.faixas] == [1, 2, 3, 4, 5]
    assert all(f.duracao_seg and f.isrc and f.autores for f in ficha.faixas)
    assert problemas == [] and validacao.validar(ficha) == []


def test_ficha_com_erros_aponta_a_celula(fichas):
    ficha, problemas = leitura.ler(fichas[2])
    todos = problemas + validacao.validar(ficha)
    graves = sorted(str(p) for p in todos if p.grave)
    assert len(graves) == 4
    assert any(g.startswith("A12: faixa 1: percentual de autores soma 95,00%") for g in graves)
    assert any("CPF inválido em autores" in g for g in graves)
    assert any(g.startswith("B38: faixa 3: ISRC ausente") for g in graves)
    assert any("aparece duas vezes em autores" in g for g in graves)
    assert [str(p) for p in todos if not p.grave] == ["A59: rótulo desconhecido: 'Observação'"]


def test_duracao_como_hora_do_excel_ou_texto_e_percentual_com_virgula(tmp_path):
    livro = Workbook()
    for linha in [["Gravadora", "Selo X"], ["Faixa", 1], ["Duração", time(0, 3, 42)], ["Faixa", 2],
                  ["Duração", "1:02:03"], ["Faixa", 3], ["Duração", "3:75"], ["Autores"],
                  ["Nome", "CPF", "Função", "%"], ["Ana Leite", "1", "Compositor", "33,33"]]:
        livro.active.append(linha)
    livro.save(tmp_path / "f.xlsx")
    ficha, problemas = leitura.ler(tmp_path / "f.xlsx")
    assert [f.duracao_seg for f in ficha.faixas] == [222, 3723, None]
    assert ficha.faixas[2].autores[0].percentual == Decimal("33.33")
    assert [str(p) for p in problemas] == ["B7: duração inválida: '3:75' (use mm:ss)"]


def test_documentos():
    rng = random.Random(1)
    assert all(validacao.cpf_valido(gerar_dados.cpf(rng)) for _ in range(200))
    assert all(validacao.cnpj_valido(gerar_dados.cnpj(rng)) for _ in range(200))
    assert not validacao.cpf_valido("11111111111") and not validacao.cpf_valido("123")
    valido = gerar_dados.cpf(rng)
    assert not validacao.cpf_valido(valido[:-1] + str((int(valido[-1]) + 1) % 10))


@pytest.mark.parametrize("isrc, ok", [("BR-SEL-26-00001", True), ("BRSEL2600001", True), ("BR-SEL-26-1", False),
                                      ("12-SEL-26-00001", False)])
def test_isrc(isrc, ok):
    assert bool(validacao.ISRC.match(validacao.isrc_normalizado(isrc))) is ok


def test_musico_pode_tocar_dois_instrumentos_mas_autor_nao_repete():
    rng = random.Random(2)
    doc = gerar_dados.cpf(rng)
    faixa = Faixa(1, "A5", "Título", "BRSEL2600001", 200, None,
                  autores=[Pessoa("Ana Leite", doc, "A10", "COMPOSITOR", Decimal("100.00"))],
                  musicos=[Pessoa("Ana Leite", doc, "A14", instrumento="VIOLAO"),
                           Pessoa("Ana Leite", doc, "A15", instrumento="VOZ")])
    assert validacao.validar(Ficha("Selo", None, [faixa])) == []
