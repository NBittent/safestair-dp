"""
Gera data/sensores/leituras_sensores.csv: leituras diárias SIMULADAS dos
sensores propostos pelo SafeStair (vibração, temperatura, corrente, tensão,
trepidação, nível de óleo e velocidade) para as 197 escadas reais de
data/escadas.csv.

A Linha 4 ainda não tem esses sensores; o arquivo existe para demonstrar o
notebook_sensores.ipynb, que aplica os mesmos algoritmos a esse tipo de dado.
Os perfis de falha são sorteados com semente fixa e NÃO têm relação com o
histórico real de falhas do SAP.

Autores: Squad 6 · Versão 1.0 — outubro/2026
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

DADOS = Path(__file__).resolve().parent.parent / "data"
SAIDA = DADOS / "sensores"
SAIDA.mkdir(exist_ok=True)
random.seed(42)

N_DIAS = 24
INICIO = date(2026, 9, 1)
PERFIS = ["saudavel"] * 55 + ["rolamento"] * 10 + ["superaquecimento"] * 9 + ["oleo"] * 9 + \
         ["eletrico"] * 8 + ["atrito"] * 9

with open(DADOS / "escadas.csv", encoding="utf-8") as f:
    escadas = [linha["cd_escada"] for linha in csv.DictReader(f)]


def leitura_base():
    return {
        "vibracao_mm_s": random.gauss(1.4, 0.15),
        "temperatura_c": random.gauss(38, 1.5),
        "corrente_a": random.gauss(28.5, 0.8),
        "tensao_v": random.gauss(380, 3),
        "trepidacao_hz": random.gauss(2.6, 0.2),
        "nivel_oleo_pct": random.gauss(90, 1.5),
        "velocidade_m_s": random.gauss(0.65, 0.003),
    }


def aplica_perfil(r, perfil, t, intensidade):
    """t vai de 0 (primeiro dia) a 1 (último dia); a degradação acelera com t²."""
    k = intensidade * t ** 2
    if perfil == "rolamento":
        r["vibracao_mm_s"] += 3.6 * k
        r["trepidacao_hz"] += 3.2 * k
        r["temperatura_c"] += 6 * k
    elif perfil == "superaquecimento":
        r["temperatura_c"] += 36 * k
        r["corrente_a"] += 3.5 * k
    elif perfil == "oleo":
        r["nivel_oleo_pct"] -= 55 * k
        r["temperatura_c"] += 8 * k
    elif perfil == "eletrico":
        r["corrente_a"] += 9 * k
        r["tensao_v"] -= 30 * k
    elif perfil == "atrito":
        r["velocidade_m_s"] -= 0.05 * k
        r["corrente_a"] += 6 * k
        r["temperatura_c"] += 10 * k
    return r


cols = ["cd_escada", "dt_leitura", "vibracao_mm_s", "temperatura_c", "corrente_a",
        "tensao_v", "trepidacao_hz", "nivel_oleo_pct", "velocidade_m_s"]
with open(SAIDA / "leituras_sensores.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(cols)
    for cd in escadas:
        perfil = random.choice(PERFIS)
        intensidade = random.uniform(0.3, 1.2) if perfil != "saudavel" else 0
        for d in range(N_DIAS):
            t = d / (N_DIAS - 1)
            r = aplica_perfil(leitura_base(), perfil, t, intensidade)
            r["nivel_oleo_pct"] = min(100, max(0, r["nivel_oleo_pct"]))
            w.writerow([cd, (INICIO + timedelta(days=d)).isoformat()] +
                       [round(r[c], 3 if c == "velocidade_m_s" else 2) for c in cols[2:]])

print(f"leituras_sensores.csv: {len(escadas)} escadas × {N_DIAS} dias")
