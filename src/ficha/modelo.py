"""O que sai da planilha: ficha, faixas e participantes, cada valor com a célula de onde veio."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Problema:
    celula: str      # "B14", ou "" quando é da ficha inteira
    mensagem: str
    grave: bool = True  # grave bloqueia a carga; aviso só aparece no relatório

    def __str__(self) -> str:
        return f"{self.celula + ': ' if self.celula else ''}{self.mensagem}"


@dataclass
class Pessoa:
    nome: str
    documento: str
    celula: str
    funcao: str | None = None        # autor, compositor, letrista
    percentual: Decimal | None = None
    instrumento: str | None = None


@dataclass
class Faixa:
    numero: int
    celula: str
    titulo: str | None = None
    isrc: str | None = None
    duracao_seg: int | None = None
    lancamento: date | None = None
    autores: list[Pessoa] = field(default_factory=list)
    editoras: list[Pessoa] = field(default_factory=list)
    musicos: list[Pessoa] = field(default_factory=list)
    celulas: dict[str, str] = field(default_factory=dict)  # campo -> célula, para apontar o erro


@dataclass
class Ficha:
    gravadora: str | None = None
    data_envio: date | None = None
    faixas: list[Faixa] = field(default_factory=list)
