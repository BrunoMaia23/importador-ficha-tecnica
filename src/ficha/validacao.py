"""Regras da ficha. Problema grave bloqueia a carga da ficha inteira; aviso só vai para o relatório."""
from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal

from .modelo import Faixa, Ficha, Pessoa, Problema

ISRC = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$")
CEM = Decimal("100.00")
FUNCOES_AUTOR = {"AUTOR", "COMPOSITOR", "LETRISTA"}


def isrc_normalizado(isrc: str | None) -> str:
    return re.sub(r"[-\s]", "", (isrc or "").upper())


def cpf_valido(cpf: str) -> bool:
    if len(cpf) != 11 or not cpf.isdigit() or len(set(cpf)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        if int(cpf[tamanho]) != (soma * 10 % 11) % 10:
            return False
    return True


def cnpj_valido(cnpj: str) -> bool:
    if len(cnpj) != 14 or not cnpj.isdigit() or len(set(cnpj)) == 1:
        return False
    for tamanho, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        resto = sum(int(cnpj[i]) * pesos[i] for i in range(tamanho)) % 11
        if int(cnpj[tamanho]) != (0 if resto < 2 else 11 - resto):
            return False
    return True


def validar(ficha: Ficha) -> list[Problema]:
    problemas = []
    if not ficha.gravadora:
        problemas.append(Problema("", "gravadora não informada"))
    if not ficha.faixas:
        problemas.append(Problema("", "nenhuma faixa na ficha"))
    repetidos = Counter(isrc_normalizado(f.isrc) for f in ficha.faixas if f.isrc)
    for f in ficha.faixas:
        problemas += _faixa(f)
        if f.isrc and repetidos[isrc_normalizado(f.isrc)] > 1:
            problemas.append(Problema(f.celulas.get("isrc", f.celula), f"ISRC repetido na ficha: {f.isrc}"))
    return problemas


def _faixa(f: Faixa) -> list[Problema]:
    p = []
    onde = f"faixa {f.numero}"
    if not f.titulo:
        p.append(Problema(f.celulas.get("titulo", f.celula), f"{onde}: título ausente"))
    if not f.isrc:
        p.append(Problema(f.celulas.get("isrc", f.celula), f"{onde}: ISRC ausente"))
    elif not ISRC.match(isrc_normalizado(f.isrc)):
        p.append(Problema(f.celulas["isrc"], f"{onde}: ISRC fora do padrão: {f.isrc}"))
    if not f.duracao_seg:
        p.append(Problema(f.celulas.get("duracao_seg", f.celula), f"{onde}: duração ausente ou zero"))
    if not f.autores:
        p.append(Problema(f.celula, f"{onde}: nenhum autor"))
    p += _secao(f.autores, onde, "autores", cpf_valido, "CPF", soma_obrigatoria=True)
    p += _secao(f.editoras, onde, "editoras", cnpj_valido, "CNPJ", soma_obrigatoria=bool(f.editoras))
    p += _secao(f.musicos, onde, "músicos", cpf_valido, "CPF", soma_obrigatoria=False)
    for a in f.autores:
        if a.funcao not in FUNCOES_AUTOR:
            p.append(Problema(a.celula, f"{onde}: função de autor desconhecida: {a.funcao!r}"))
    for m in f.musicos:
        if not m.instrumento:
            p.append(Problema(m.celula, f"{onde}: músico sem instrumento: {m.nome}"))
    return p


def _secao(pessoas: list[Pessoa], onde: str, nome: str, documento_valido, tipo: str,
           soma_obrigatoria: bool) -> list[Problema]:
    p = []
    vistos: set[str] = set()
    for x in pessoas:
        if not x.nome:
            p.append(Problema(x.celula, f"{onde}: {nome} com nome vazio"))
        if not documento_valido(x.documento):
            p.append(Problema(x.celula, f"{onde}: {tipo} inválido em {nome}: {x.nome}"))
        elif x.documento in vistos and nome != "músicos":  # músico pode tocar dois instrumentos
            p.append(Problema(x.celula, f"{onde}: {x.nome} aparece duas vezes em {nome}"))
        vistos.add(x.documento)
    if soma_obrigatoria:
        if any(x.percentual is None for x in pessoas):
            p.append(Problema(pessoas[0].celula if pessoas else "", f"{onde}: {nome} sem percentual"))
        else:
            soma = sum(x.percentual for x in pessoas)
            if soma != CEM:
                texto = str(soma).replace(".", ",")
                p.append(Problema(pessoas[0].celula, f"{onde}: percentual de {nome} soma {texto}%, e não 100%"))
    return p
