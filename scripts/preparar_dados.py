"""
Prepara o dataset da Motiva (notas de manutenção SAP das escadas rolantes da
Linha 4-Amarela, arquivos data/raw/ecr_AAAA.XLSX) para o notebook.

Saídas:
- data/falhas.csv            : falhas corretivas (notas Z1) de jan/2023 a ago/2026,
                               sem notas canceladas ou duplicadas, uma linha por falha.
- data/escadas.csv           : cadastro das escadas (código, estação, local SAP).
- data/resumo_notas_ano.csv  : quantidade de notas por tipo e ano (2009–2026),
                               usada no notebook para justificar o recorte.

Decisões de limpeza (justificadas no README):
- Só notas Z1 (falha corretiva); Z3 = preventiva, Z2 = anomalia sem parada.
- Só a partir de 2023, quando o registro passou a ser automático (status OAUT):
  antes disso o volume não é comparável.
- Até ago/2026, último mês completo (o arquivo de 2026 termina em 22/09).
- Só locais no nível de escada (SP04-6-ECR-<ESTAÇÃO>-ER<nn>).
- Excluídas notas com status CANC (cancelada) ou DUPL (duplicada).

Autores: Squad 6 (Marcelo de Toledo, Nícolas Tanajura, Rafael Benez)
Versão: 2.0 — outubro/2026
"""
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
RAW = RAIZ / "data" / "raw"
SAIDA = RAIZ / "data"
INICIO, FIM = "2023-01-01", "2026-09-01"  # FIM exclusivo

arquivos = sorted(RAW.glob("ecr_*.XLSX"))
if not arquivos:
    raise SystemExit(f"Coloque as planilhas ecr_AAAA.XLSX em {RAW}")

notas = pd.concat([pd.read_excel(f, dtype=str).assign(arquivo=f.name) for f in arquivos],
                  ignore_index=True).fillna("")
notas.columns = [c.strip() for c in notas.columns]
print(f"{len(arquivos)} arquivos, {len(notas)} notas")

# Resumo por tipo e ano do arquivo
notas["ano_arquivo"] = notas.arquivo.str.extract(r"(\d{4})")[0].astype(int)
(notas.pivot_table(index="ano_arquivo", columns="Tipo de Nota", values="Nota", aggfunc="size", fill_value=0)
      .reset_index().to_csv(SAIDA / "resumo_notas_ano.csv", index=False))

# Nível de escada: SP04-6-ECR-PIN-ER24 -> estação PIN, escada PIN-ER24
local = notas["Local de Instalação"].str.strip()
notas = notas[local.str.count("-") == 4].copy()
partes = notas["Local de Instalação"].str.strip().str.split("-")
notas["id_estacao"] = partes.str[3]
notas["cd_escada"] = partes.str[3] + "-" + partes.str[4]


def data_hora(d, h):
    return pd.to_datetime(d + " " + h.astype(str), format="%d/%m/%Y %H:%M:%S", errors="coerce")


notas["inicio"] = data_hora(notas["Início avaria"], notas["Hora início avaria"])
notas["fim"] = data_hora(notas["Fim da avaria"], notas["Hora do fim da avaria"])

z1 = notas[(notas["Tipo de Nota"] == "Z1")
           & ~notas["Status do Usuário da Ordem"].str.contains("CANC|DUPL")
           & (notas.inicio >= INICIO) & (notas.inicio < FIM)].copy()
z1["horas_parada"] = ((z1.fim - z1.inicio).dt.total_seconds() / 3600).round(3)
z1["indisponivel"] = (z1["Indisponível"] == "X").astype(int)
z1["substituicao"] = z1["Ação"].str.startswith("SUBSTITU").astype(int)

falhas = z1.rename(columns={"Nota": "nota", "Sintoma": "sintoma", "Defeito": "defeito", "Causa": "causa",
                            "Objeto": "componente", "Ação": "acao"})[
    ["nota", "cd_escada", "id_estacao", "inicio", "fim", "horas_parada", "indisponivel", "substituicao",
     "sintoma", "defeito", "causa", "componente", "acao"]].sort_values(["cd_escada", "inicio"])
falhas.to_csv(SAIDA / "falhas.csv", index=False)

escadas = (notas[notas.inicio >= INICIO][["cd_escada", "id_estacao", "Local de Instalação"]]
           .drop_duplicates("cd_escada").rename(columns={"Local de Instalação": "local_sap"})
           .sort_values("cd_escada"))
escadas.to_csv(SAIDA / "escadas.csv", index=False)

print(f"falhas.csv: {len(falhas)} falhas · {falhas.cd_escada.nunique()} escadas · "
      f"{falhas.inicio.min():%d/%m/%Y} a {falhas.inicio.max():%d/%m/%Y}")
print(f"escadas.csv: {len(escadas)} escadas em {escadas.id_estacao.nunique()} locais")
