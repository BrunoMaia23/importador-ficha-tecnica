import copy
import json
import shutil

import pytest

from ficha import carga, contrato, gerar_dados, leitura


@pytest.fixture(scope="module")
def bundles(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("entrada")
    fichas = gerar_dados.gerar(pasta)
    return [contrato.montar(leitura.ler(f)[0], f) for f in fichas[:2]], fichas


@pytest.fixture
def con(tmp_path):
    c = carga.conectar(tmp_path / "banco.sqlite")
    yield c
    c.close()


def _contar(con, tabela):
    return con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]


def test_hash_e_do_conteudo_e_nao_do_nome_do_arquivo(bundles, tmp_path):
    (b1, _), fichas = bundles
    copia = tmp_path / "outro_nome.xlsx"
    shutil.copy(fichas[0], copia)
    b_copia = contrato.montar(leitura.ler(copia)[0], copia)
    assert b_copia["hash"] == b1["hash"] and b_copia["fonte"]["arquivo"] != b1["fonte"]["arquivo"]


def test_contrato_editado_a_mao_e_recusado(bundles, tmp_path):
    (b1, _), _ = bundles
    editado = copy.deepcopy(b1)
    editado["faixas"][0]["titulo"] = "Outro título"
    contrato.gravar(editado, tmp_path / "editado.json")
    with pytest.raises(ValueError, match="hash"):
        contrato.ler(tmp_path / "editado.json")
    contrato.gravar(b1, tmp_path / "ok.json")
    assert contrato.ler(tmp_path / "ok.json") == json.loads(json.dumps(b1))


def test_carga_reenvio_e_force(bundles, con):
    (b1, b2), _ = bundles
    r = carga.carregar(con, b1)
    assert r.situacao == "carregada" and r.contagens["fonogramas"] == len(b1["faixas"]) == _contar(con, "fonograma")
    assert carga.carregar(con, b1).situacao == "ja_carregada"
    forcada = carga.carregar(con, b1, force=True)
    assert forcada.situacao == "carregada" and _contar(con, "fonograma") == len(b1["faixas"])
    assert _contar(con, "obra") == len(b1["faixas"])           # o force não deixa obra órfã para trás
    assert carga.carregar(con, b2).situacao == "carregada"
    assert _contar(con, "manifesto") == 2


def test_isrc_de_outra_ficha_e_conflito(bundles, con):
    (b1, _), _ = bundles
    carga.carregar(con, b1)
    outra = copy.deepcopy(b1)
    outra["gravadora"] = "Outra gravadora"
    outra["hash"] = contrato.hash_conteudo({k: outra[k] for k in ("gravadora", "data_envio", "faixas")})
    r = carga.carregar(con, outra)
    assert r.situacao == "conflito" and "ISRC já carregado" in r.detalhe


def test_dry_run_nao_grava_nada(bundles, con):
    (b1, _), _ = bundles
    r = carga.carregar(con, b1, dry_run=True)
    assert r.situacao == "simulada" and r.contagens["obras"] == len(b1["faixas"])
    assert _contar(con, "obra") == _contar(con, "manifesto") == 0


def test_checagem_antes_do_commit_desfaz_tudo(bundles, con):
    (b1, _), _ = bundles
    ruim = copy.deepcopy(b1)
    ruim["faixas"][0]["autores"][0]["percentual"] = "1.00"      # passou da validação de algum jeito
    ruim["hash"] = contrato.hash_conteudo({k: ruim[k] for k in ("gravadora", "data_envio", "faixas")})
    r = carga.carregar(con, ruim)
    assert r.situacao == "reprovada" and "autoria de cada obra soma 100%" in r.detalhe
    assert _contar(con, "obra") == _contar(con, "fonograma") == _contar(con, "manifesto") == 0
