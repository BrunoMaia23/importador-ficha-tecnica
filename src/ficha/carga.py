"""Carga do contrato no banco (SQLite aqui; no projeto real, Oracle).

A ficha inteira é uma transação. Antes do commit rodam as checagens de consistência, e qualquer
falha desfaz tudo. O manifesto (hash do conteúdo) entra na mesma transação: ficha já carregada é
pulada, a não ser com --force, que substitui as faixas daquela ficha. Percentual é guardado em
centésimos inteiros, para a soma fechar exata.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS pessoa (documento TEXT PRIMARY KEY, nome TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS editora (cnpj TEXT PRIMARY KEY, nome TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS obra (id INTEGER PRIMARY KEY, titulo TEXT NOT NULL, ficha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS autoria (
    obra_id INTEGER NOT NULL REFERENCES obra (id), documento TEXT NOT NULL REFERENCES pessoa (documento),
    funcao TEXT NOT NULL, centesimos INTEGER NOT NULL, PRIMARY KEY (obra_id, documento));
CREATE TABLE IF NOT EXISTS edicao (
    obra_id INTEGER NOT NULL REFERENCES obra (id), cnpj TEXT NOT NULL REFERENCES editora (cnpj),
    centesimos INTEGER NOT NULL, PRIMARY KEY (obra_id, cnpj));
CREATE TABLE IF NOT EXISTS fonograma (
    isrc TEXT PRIMARY KEY, obra_id INTEGER NOT NULL REFERENCES obra (id), titulo TEXT NOT NULL,
    duracao_seg INTEGER NOT NULL, lancamento TEXT, gravadora TEXT NOT NULL, ficha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS participacao (
    isrc TEXT NOT NULL REFERENCES fonograma (isrc), documento TEXT NOT NULL REFERENCES pessoa (documento),
    instrumento TEXT NOT NULL, PRIMARY KEY (isrc, documento, instrumento));
CREATE TABLE IF NOT EXISTS manifesto (
    hash TEXT PRIMARY KEY, arquivo TEXT NOT NULL, sha256_arquivo TEXT NOT NULL, faixas INTEGER NOT NULL,
    carregado_em TEXT NOT NULL DEFAULT (datetime('now')));
"""

CHECAGENS = {
    "autoria de cada obra soma 100%": """
        SELECT o.id FROM obra o LEFT JOIN autoria a ON a.obra_id = o.id
        WHERE o.ficha = :ficha GROUP BY o.id HAVING coalesce(sum(a.centesimos), 0) <> 10000""",
    "edição de cada obra soma 100% quando existe": """
        SELECT obra_id FROM edicao WHERE obra_id IN (SELECT id FROM obra WHERE ficha = :ficha)
        GROUP BY obra_id HAVING sum(centesimos) <> 10000""",
    "todo fonograma tem obra": """
        SELECT f.isrc FROM fonograma f LEFT JOIN obra o ON o.id = f.obra_id
        WHERE f.ficha = :ficha AND o.id IS NULL""",
    "toda participação tem pessoa": """
        SELECT p.isrc FROM participacao p JOIN fonograma f ON f.isrc = p.isrc
        LEFT JOIN pessoa x ON x.documento = p.documento WHERE f.ficha = :ficha AND x.documento IS NULL""",
}


@dataclass
class Resultado:
    situacao: str  # carregada, simulada, ja_carregada, conflito, reprovada
    contagens: dict[str, int] = field(default_factory=dict)
    detalhe: str = ""


class FalhaDeChecagem(Exception):
    pass


def conectar(banco: Path | str) -> sqlite3.Connection:
    con = sqlite3.connect(banco, isolation_level=None)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    return con


def carregar(con: sqlite3.Connection, bundle: dict, dry_run: bool = False, force: bool = False) -> Resultado:
    ficha = bundle["hash"]
    if con.execute("SELECT 1 FROM manifesto WHERE hash = ?", [ficha]).fetchone() and not force:
        quando = con.execute("SELECT carregado_em FROM manifesto WHERE hash = ?", [ficha]).fetchone()[0]
        return Resultado("ja_carregada", detalhe=f"carregada em {quando}; use --force para recarregar")
    isrcs = [f["isrc"] for f in bundle["faixas"]]
    existentes = [r[0] for r in con.execute(
        f"SELECT isrc FROM fonograma WHERE isrc IN ({','.join('?' * len(isrcs))})", isrcs)]
    if existentes and not force:
        return Resultado("conflito", detalhe=f"ISRC já carregado por outra ficha: {', '.join(existentes[:5])}")

    con.execute("BEGIN")
    try:
        if existentes:
            _remover(con, existentes)
        contagens = _inserir(con, bundle)
        falhas = {nome: [r[0] for r in con.execute(sql, {"ficha": ficha})] for nome, sql in CHECAGENS.items()}
        falhas = {nome: ids for nome, ids in falhas.items() if ids}
        if falhas:
            raise FalhaDeChecagem("; ".join(f"{nome} ({len(ids)} falhas)" for nome, ids in falhas.items()))
        con.execute("INSERT OR REPLACE INTO manifesto (hash, arquivo, sha256_arquivo, faixas) VALUES (?, ?, ?, ?)",
                    [ficha, bundle["fonte"]["arquivo"], bundle["fonte"]["sha256"], len(bundle["faixas"])])
    except FalhaDeChecagem as exc:
        con.execute("ROLLBACK")
        return Resultado("reprovada", detalhe=str(exc))
    except Exception:
        con.execute("ROLLBACK")
        raise
    if dry_run:
        con.execute("ROLLBACK")
        return Resultado("simulada", contagens, "nada foi gravado")
    con.execute("COMMIT")
    return Resultado("carregada", contagens, f"substituiu {len(existentes)} fonogramas" if existentes else "")


def _centesimos(percentual: str) -> int:
    return int(Decimal(percentual) * 100)


def _inserir(con: sqlite3.Connection, bundle: dict) -> dict[str, int]:
    n = {"obras": 0, "fonogramas": 0, "autorias": 0, "edicoes": 0, "participacoes": 0}
    for f in bundle["faixas"]:
        obra_id = con.execute("INSERT INTO obra (titulo, ficha) VALUES (?, ?)", [f["titulo"], bundle["hash"]]).lastrowid
        n["obras"] += 1
        for a in f["autores"]:
            _pessoa(con, a)
            con.execute("INSERT INTO autoria VALUES (?, ?, ?, ?)",
                        [obra_id, a["documento"], a["funcao"], _centesimos(a["percentual"])])
            n["autorias"] += 1
        for e in f["editoras"]:
            con.execute("INSERT INTO editora VALUES (?, ?) ON CONFLICT (cnpj) DO UPDATE SET nome = excluded.nome",
                        [e["documento"], e["nome"]])
            con.execute("INSERT INTO edicao VALUES (?, ?, ?)", [obra_id, e["documento"], _centesimos(e["percentual"])])
            n["edicoes"] += 1
        con.execute("INSERT INTO fonograma VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [f["isrc"], obra_id, f["titulo"], f["duracao_seg"], f["lancamento"], bundle["gravadora"],
                     bundle["hash"]])
        n["fonogramas"] += 1
        for m in f["musicos"]:
            _pessoa(con, m)
            con.execute("INSERT INTO participacao VALUES (?, ?, ?)", [f["isrc"], m["documento"], m["instrumento"]])
            n["participacoes"] += 1
    return n


def _pessoa(con: sqlite3.Connection, p: dict) -> None:
    con.execute("INSERT INTO pessoa VALUES (?, ?) ON CONFLICT (documento) DO UPDATE SET nome = excluded.nome",
                [p["documento"], p["nome"]])


def _remover(con: sqlite3.Connection, isrcs: list[str]) -> None:
    """--force: tira as faixas antigas (fonograma, participações, obra e o que pende da obra)."""
    marcadores = ",".join("?" * len(isrcs))
    obras = [r[0] for r in con.execute(f"SELECT obra_id FROM fonograma WHERE isrc IN ({marcadores})", isrcs)]
    con.execute(f"DELETE FROM participacao WHERE isrc IN ({marcadores})", isrcs)
    con.execute(f"DELETE FROM fonograma WHERE isrc IN ({marcadores})", isrcs)
    if obras:
        ids = ",".join("?" * len(obras))
        con.execute(f"DELETE FROM autoria WHERE obra_id IN ({ids})", obras)
        con.execute(f"DELETE FROM edicao WHERE obra_id IN ({ids})", obras)
        con.execute(f"DELETE FROM obra WHERE id IN ({ids})", obras)
