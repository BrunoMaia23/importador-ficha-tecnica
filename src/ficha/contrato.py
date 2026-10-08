"""O contrato entre a leitura e a carga: um JSON versionado com a ficha já validada.

A carga nunca lê o Excel. Ela recebe este JSON, que pode ser revisado, guardado e recarregado sem
depender da planilha. O hash do conteúdo identifica a ficha: a mesma ficha reenviada, mesmo com outro
nome de arquivo, tem o mesmo hash.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .modelo import Ficha
from .validacao import isrc_normalizado

VERSAO = 1


def montar(ficha: Ficha, arquivo: Path | str) -> dict:
    conteudo = {
        "gravadora": ficha.gravadora,
        "data_envio": ficha.data_envio.isoformat() if ficha.data_envio else None,
        "faixas": [{
            "numero": f.numero,
            "titulo": f.titulo,
            "isrc": isrc_normalizado(f.isrc),
            "duracao_seg": f.duracao_seg,
            "lancamento": f.lancamento.isoformat() if f.lancamento else None,
            "autores": [{"nome": a.nome, "documento": a.documento, "funcao": a.funcao,
                         "percentual": str(a.percentual)} for a in f.autores],
            "editoras": [{"nome": e.nome, "documento": e.documento, "percentual": str(e.percentual)}
                         for e in f.editoras],
            "musicos": [{"nome": m.nome, "documento": m.documento, "instrumento": m.instrumento}
                        for m in f.musicos],
        } for f in ficha.faixas],
    }
    dados = Path(arquivo).read_bytes()
    return {"versao": VERSAO, "hash": hash_conteudo(conteudo),
            "fonte": {"arquivo": Path(arquivo).name, "sha256": hashlib.sha256(dados).hexdigest()},
            **conteudo}


def hash_conteudo(conteudo: dict) -> str:
    texto = json.dumps(conteudo, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def gravar(bundle: dict, caminho: Path | str) -> None:
    Path(caminho).write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")


def ler(caminho: Path | str) -> dict:
    bundle = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if bundle.get("versao") != VERSAO:
        raise ValueError(f"versão do contrato não suportada: {bundle.get('versao')!r}")
    conteudo = {k: bundle[k] for k in ("gravadora", "data_envio", "faixas")}
    if hash_conteudo(conteudo) != bundle["hash"]:
        raise ValueError("o conteúdo do contrato não bate com o hash (arquivo editado à mão?)")
    return bundle
