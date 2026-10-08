# importador-ficha-tecnica

[![testes](https://github.com/BrunoMaia23/importador-ficha-tecnica/actions/workflows/testes.yml/badge.svg)](https://github.com/BrunoMaia23/importador-ficha-tecnica/actions/workflows/testes.yml)

A ficha técnica de gravação chega da gravadora numa planilha feita para gente ler, não para programa:
um bloco por faixa, rótulo na coluna A e valor na B, e no meio de cada bloco as tabelas de autores,
editoras e músicos. No trabalho eu montei o importador dessas fichas para o banco de obras e fonogramas,
que é Oracle e tem trava de ambiente (rodar contra produção exige pedir e confirmar). Aqui as fichas
são inventadas e o banco é um SQLite; as regras de conversão que vieram do sistema antigo ficaram de
fora.

## Uma ficha

```
Ficha técnica de gravação
Gravadora:       Selo Pedra Azul
Data de envio:   02/03/2026

Faixa            1
Título           Lua de Agosto
ISRC             BR-SEL-26-00001
Duração          03:42
Lançamento       15/01/2026
Autores
Nome             CPF              Função       %
Natália Paiva    123.456.789-09   Compositor   50
Raul Teles       ...              Letrista     50,00
Editoras
Nome             CNPJ             %
...
Músicos
Nome             CPF              Instrumento
...

Faixa            2
...
```

Duração pode vir como texto ou como hora do Excel, percentual com vírgula ou ponto, CPF com ou sem
máscara. É o tipo de variação que aparece quando a planilha é preenchida à mão.

## Do Excel ao banco

**Leitura** (`leitura.py`). A ficha não é uma tabela, então a leitura anda linha a linha, como uma
máquina de estados: "Faixa" abre um bloco, os rótulos preenchem os campos, "Autores", "Editoras" e
"Músicos" abrem as seções, e uma linha em branco fecha a seção. Cada valor guarda a célula de origem.

**Validação** (`validacao.py`). Título, ISRC no padrão, duração, CPF e CNPJ com dígito verificador,
percentual de autores somando 100% (e o de editoras também, quando há editora), pessoa repetida na
mesma seção. Problema grave bloqueia a ficha inteira, sempre apontando a célula; rótulo desconhecido só
gera aviso.

**Contrato** (`contrato.py`). A carga nunca lê o Excel. A leitura entrega um JSON versionado, com um
hash do conteúdo: a mesma ficha reenviada com outro nome tem o mesmo hash, e um JSON editado à mão é
recusado porque o conteúdo não bate com o hash.

**Carga** (`carga.py`). Uma transação por ficha. Antes do commit rodam checagens em SQL (autoria de
cada obra somando 100%, fonograma sem obra, participação sem pessoa), e qualquer falha desfaz tudo. O
manifesto entra na mesma transação. Ficha já carregada é pulada; ISRC que já veio de outra ficha é
conflito. `--force` substitui as faixas antigas sem deixar obra órfã, e `--dry-run` mostra o que seria
feito e desfaz. Percentual é gravado em centésimos inteiros, para a soma fechar exata.

## Três fichas, uma com erros

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m ficha demo
```

```
[dados]     3 fichas fictícias em entrada/ (a última com erros de propósito)

[ficha_01]  5 faixas lidas | 0 problemas graves, 0 avisos
      carregada: obras 5, fonogramas 5, autorias 13, edicoes 6, participacoes 15

[ficha_02]  3 faixas lidas | 0 problemas graves, 0 avisos
      carregada: obras 3, fonogramas 3, autorias 8, edicoes 4, participacoes 8

[ficha_03]  4 faixas lidas | 4 problemas graves, 1 aviso
      ERRO  A12: faixa 1: percentual de autores soma 95,00%, e não 100%
      ERRO  A27: faixa 2: CPF inválido em autores: Hugo Monteiro
      ERRO  B38: faixa 3: ISRC ausente
      aviso A59: rótulo desconhecido: 'Observação'
      ERRO  A63: faixa 4: Cecília Vasconcelos aparece duas vezes em autores
      carga bloqueada: corrija a planilha e envie de novo

[reenvio]   a ficha_01 chega de novo, com outro nome de arquivo
[ficha_01_reenvio]  5 faixas lidas | 0 problemas graves, 0 avisos
      já carregada: carregada em 2026-10-08 18:58:52; use --force para recarregar

[simulação] ficha_02 com --dry-run --force: mostra o que faria, sem gravar
      simulada: obras 3, fonogramas 3, autorias 8, edicoes 4, participacoes 8 (nada foi gravado)
```

Os comandos soltos: `ficha ler planilha.xlsx` (grava o JSON), `ficha carregar ficha.json --banco
banco.sqlite`, e `ficha processar planilha.xlsx` para os dois passos de uma vez, com `--dry-run` e
`--force` quando precisar.
