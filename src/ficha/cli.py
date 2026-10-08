"""Ficha técnica em Excel -> contrato JSON -> banco, com validação por célula e manifesto."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import carga, contrato, gerar_dados, leitura, validacao
from .modelo import Problema

MARCADOR = ".ficha-demo"
SITUACOES = {"carregada": "carregada", "simulada": "simulada", "ja_carregada": "já carregada",
             "conflito": "conflito", "reprovada": "reprovada nas checagens"}


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _linha(p: Problema) -> int:
    digitos = "".join(c for c in p.celula if c.isdigit())
    return int(digitos) if digitos else 0


def ler(planilha: Path, saida: Path | None = None) -> dict | None:
    """Lê e valida. Devolve o contrato, ou None se houver problema grave."""
    ficha, problemas = leitura.ler(planilha)
    problemas = sorted(problemas + validacao.validar(ficha), key=_linha)
    graves = [p for p in problemas if p.grave]
    print(f"[{planilha.stem}]  {len(ficha.faixas)} faixas lidas | "
          f"{_plural(len(graves), 'problema grave', 'problemas graves')}, "
          f"{_plural(len(problemas) - len(graves), 'aviso', 'avisos')}")
    for p in problemas:
        print(f"      {'ERRO ' if p.grave else 'aviso'} {p}")
    if graves:
        print(f"      carga bloqueada: corrija a planilha e envie de novo")
        return None
    bundle = contrato.montar(ficha, planilha)
    if saida:
        contrato.gravar(bundle, saida)
    return bundle


def carregar(bundle: dict, banco: Path, dry_run: bool = False, force: bool = False) -> carga.Resultado:
    con = carga.conectar(banco)
    try:
        r = carga.carregar(con, bundle, dry_run=dry_run, force=force)
    finally:
        con.close()
    contagens = ", ".join(f"{k} {v}" for k, v in r.contagens.items())
    print(f"      {SITUACOES[r.situacao]}: {contagens or r.detalhe}{' (' + r.detalhe + ')' if contagens and r.detalhe else ''}")
    return r


def demo(base: Path) -> int:
    if base.exists():
        if not (base / MARCADOR).exists():
            print(f"A pasta {base} já existe e não foi criada pela demo; escolha outra com --base.")
            return 2
        shutil.rmtree(base)
    base.mkdir(parents=True)
    (base / MARCADOR).write_text("pasta da demo do importador\n", encoding="utf-8")
    fichas = gerar_dados.gerar(base / "entrada")
    print(f"[dados]     {len(fichas)} fichas fictícias em entrada/ (a última com erros de propósito)\n")
    banco = base / "banco.sqlite"
    situacoes = []
    for planilha in fichas:
        bundle = ler(planilha, base / f"{planilha.stem}.json")
        situacoes.append(carregar(bundle, banco).situacao if bundle else "bloqueada")
        print()

    print("[reenvio]   a ficha_01 chega de novo, com outro nome de arquivo")
    copia = base / "entrada" / "ficha_01_reenvio.xlsx"
    shutil.copy(fichas[0], copia)
    reenvio = carregar(ler(copia), banco).situacao
    print("\n[simulação] ficha_02 com --dry-run --force: mostra o que faria, sem gravar")
    simulada = carregar(contrato.ler(base / "ficha_02.json"), banco, dry_run=True, force=True).situacao
    esperado = ["carregada", "carregada", "bloqueada"]
    return 0 if situacoes == esperado and reenvio == "ja_carregada" and simulada == "simulada" else 1


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="ficha", description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("demo", help="gera fichas fictícias e passa todas pelo processo")
    p.add_argument("--base", type=Path, default=Path("demo"))
    p = sub.add_parser("ler", help="lê e valida a planilha e grava o contrato JSON")
    p.add_argument("planilha", type=Path)
    p.add_argument("--saida", type=Path)
    for nome, ajuda in (("carregar", "carrega um contrato JSON no banco"),
                        ("processar", "lê a planilha e carrega, num passo só")):
        p = sub.add_parser(nome, help=ajuda)
        p.add_argument("arquivo", type=Path)
        p.add_argument("--banco", type=Path, default=Path("banco.sqlite"))
        p.add_argument("--dry-run", action="store_true", help="mostra o que faria e desfaz")
        p.add_argument("--force", action="store_true", help="recarrega ficha já carregada ou ISRC já existente")
    a = parser.parse_args(argv)

    if a.comando == "demo":
        return demo(a.base)
    if a.comando == "ler":
        return 0 if ler(a.planilha, a.saida or a.planilha.with_suffix(".json")) else 1
    bundle = contrato.ler(a.arquivo) if a.comando == "carregar" else ler(a.arquivo)
    if bundle is None:
        return 1
    return 0 if carregar(bundle, a.banco, a.dry_run, a.force).situacao in ("carregada", "simulada") else 1
