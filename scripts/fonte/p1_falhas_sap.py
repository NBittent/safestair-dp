# ============================================================================
md(r"""
# SafeStair — Dynamic Programming
**Challenge Motiva + FIAP 2026/2027 · Engenharia de Software · Turma 2ESPR · Squad 6**

| Integrante | RM |
|---|---|
| Marcelo Checchia Pivello de Toledo | 538697 |
| Nícolas Miguel Bittencourt Tanajura | 568108 |
| Rafael Benez Martins | 574994 |

Este notebook implementa a camada algorítmica do SafeStair sobre o **dataset real da Motiva**: o histórico de notas de manutenção (SAP) das escadas rolantes da Linha 4-Amarela, de 2009 a 2026.

1. **Degradação acumulada** de cada escada, mês a mês, em três versões (recursiva pura, memoizada com dicionário e iterativa com tabulação), com medição e **ranking por criticidade**.
2. **Rede de estações como grafo** (lista de adjacência), com **BFS** (menos trechos) e **Dijkstra** (menor tempo) a partir da base de manutenção, reconstruindo as rotas.
3. **Otimização de rotas com A\***, com heurística justificada e comparação com o Dijkstra.
4. **Plano de manutenção** `planejar_turno(base, horas)`: quais escadas atender, em que ordem e por qual caminho.

Os arquivos em `data/` são gerados por `scripts/preparar_dados.py` (a partir das planilhas `ecr_AAAA.XLSX`) e `scripts/gerar_rede.py`.

> **Notebook complementar:** `notebook_sensores.ipynb` aplica os mesmos algoritmos a leituras de sensores simuladas (vibração, temperatura, corrente/tensão, óleo, velocidade), o tipo de dado que o SafeStair propõe coletar, usando os mesmos limites do `ManutencaoService` (DDD-Java).
""")

code(r"""
import sys, json, math, time, heapq, random
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.setrecursionlimit(20_000)
pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", None)
plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.3})

DADOS = Path("data")
FIGURAS = Path("figuras"); FIGURAS.mkdir(exist_ok=True)

falhas = pd.read_csv(DADOS / "falhas.csv", parse_dates=["inicio", "fim"])
escadas = pd.read_csv(DADOS / "escadas.csv")
resumo_anos = pd.read_csv(DADOS / "resumo_notas_ano.csv").set_index("ano_arquivo")
rede = json.loads((DADOS / "rede_estacoes.json").read_text(encoding="utf-8"))
nomes_est = {v["id"]: v["nome"] for v in rede["vertices"]}

print(f"Falhas (Z1): {len(falhas)} · {falhas.cd_escada.nunique()} escadas · "
      f"{falhas.inicio.min():%d/%m/%Y} a {falhas.inicio.max():%d/%m/%Y}")
print(f"Escadas: {len(escadas)} em {escadas.id_estacao.nunique()} locais · "
      f"rede: {len(rede['vertices'])} vértices, {len(rede['arestas'])} arestas")
falhas.head()
""")

md(r"""
### 0. O que é o dataset e por que o recorte 2023–2026

Cada linha das planilhas é uma **nota de manutenção** do SAP. Os tipos mais frequentes:

| Tipo | O que representa |
|---|---|
| Z1 | Falha corretiva (a escada parou ou deu alarme) |
| Z2 | Anomalia percebida sem parada (ruído, folga, óleo baixo) |
| Z3 | Preventiva programada (planos P1, P6…) |

O campo **Local de Instalação** identifica a escada (`SP04-6-ECR-PIN-ER24` = Linha 4, Pinheiros, escada ER24); dele vêm o código da escada e da estação. Usamos as **falhas Z1**, porque são elas que medem a degradação real do equipamento.
""")

code(r"""
display(resumo_anos[["Z1", "Z2", "Z3"]].T)
""")

md(r"""
**Interpretação do recorte.** O volume de falhas Z1 salta de cerca de 2 mil para mais de 7 mil por ano em 2023. Não é a frota quebrando mais: a partir de 2023 cerca de 78% das falhas passam a ser abertas automaticamente pelo monitoramento (status OAUT, descrição "Falha Técnica"). Misturar os dois regimes faria toda escada parecer piorar em 2023. Por isso a análise usa **jan/2023 a ago/2026** (44 meses completos; o arquivo de 2026 termina em 22/09), e o arquivo de 2009, que é quase todo carga do plano preventivo (Z3), fica de fora. Também foram excluídas notas canceladas ou duplicadas.

---
## Parte 1 — Degradação acumulada (recursão, memoização e tabulação)

### 1.1 Penalidade de cada falha e de cada mês

Cada falha recebe um peso em pontos:

$$\text{peso} = \underbrace{b}_{\text{1 se parou a escada, 0,5 se não}} \times \underbrace{f}_{\text{1,5 se houve troca de peça}} + \frac{\min(\text{horas parada},\ 72)}{4}$$

- A **troca de peça** indica desgaste físico, mais grave que um reset (44% das falhas se resolvem com "RESETADO E TESTADO").
- Cada **4 horas de parada** valem 1 ponto, com teto de 72 h por falha para que um único evento extremo (há paradas de mais de 30 dias) não domine a série.

A **penalidade do mês** $p_i$ de uma escada é a soma dos pesos das falhas que começaram naquele mês. O resultado é uma série de 44 valores por escada.
""")

code(r"""
falhas["peso"] = (np.where(falhas.indisponivel == 1, 1.0, 0.5) * np.where(falhas.substituicao == 1, 1.5, 1.0)
                  + falhas.horas_parada.clip(0, 72).fillna(0) / 4)
falhas["mes"] = falhas.inicio.dt.to_period("M")
MESES = pd.period_range("2023-01", "2026-08", freq="M")

P = (falhas.pivot_table(index="cd_escada", columns="mes", values="peso", aggfunc="sum", fill_value=0)
           .reindex(index=escadas.cd_escada, columns=MESES, fill_value=0))
series_p = {cd: P.loc[cd].tolist() for cd in P.index}

print(f"Matriz de penalidades: {P.shape[0]} escadas × {P.shape[1]} meses")
print("Penalidade mensal (pontos):", pd.Series(P.values.ravel()).describe(percentiles=[.5, .9, .99]).round(1).to_dict())
P.sum(axis=1).sort_values(ascending=False).head(5).round(1).rename("penalidade total 44 meses")
""")

md(r"""
### 1.2 Recorrência da degradação acumulada

Desgaste acumula e, quando está acelerando, merece ainda mais atenção. Definimos, mês a mês:

$$
D(0) = p_0, \qquad D(1) = p_1 + \alpha\,D(0)
$$
$$
D(i) = p_i + \alpha\,D(i-1) + \beta\,\max\bigl(0,\ D(i-1) - D(i-2)\bigr), \quad i \ge 2
$$

- $\alpha = 0{,}85$ é a **memória**: o histórico pesa, mas perde 15% por mês. Depois de 12 meses resta só $0{,}85^{12} \approx 14\%$, então $D$ reflete principalmente o último ano.
- $\beta = 0{,}5$ é o **termo de aceleração**: se a degradação subiu do mês $i-2$ para o $i-1$, metade desse aumento é somada. Uma escada piorando passa à frente de outra com o mesmo nível estável.

Como $D(i)$ depende de $D(i-1)$ **e** de $D(i-2)$, a recursão pura recalcula os mesmos subproblemas várias vezes, como na sequência de Fibonacci.
""")

code(r"""
ALFA, BETA = 0.85, 0.5


def degradacao_recursiva(p, i, contador=None):
    \"\"\"Versão 1 — recursiva pura. Complexidade O(φ^n) chamadas (φ ≈ 1,618).

    Args:
        p (list[float]): penalidades mensais, em ordem cronológica.
        i (int): índice do mês cuja degradação acumulada se quer.
        contador (list[int], opcional): contador de chamadas, para medição.

    Returns:
        float: D(i).
    \"\"\"
    if contador is not None:
        contador[0] += 1
    if i == 0:
        return p[0]
    if i == 1:
        return p[1] + ALFA * degradacao_recursiva(p, 0, contador)
    d1 = degradacao_recursiva(p, i - 1, contador)
    d2 = degradacao_recursiva(p, i - 2, contador)
    return p[i] + ALFA * d1 + BETA * max(0.0, d1 - d2)


def degradacao_memo(p, i, memo=None, contador=None):
    \"\"\"Versão 2 — recursiva com memoização em dicionário. O(n) tempo e memória.

    Args:
        p (list[float]): penalidades mensais.
        i (int): índice do mês.
        memo (dict[int, float], opcional): cache {índice: D(índice)}.
        contador (list[int], opcional): contador de chamadas.

    Returns:
        float: D(i).
    \"\"\"
    if memo is None:
        memo = {}
    if contador is not None:
        contador[0] += 1
    if i in memo:
        return memo[i]
    if i == 0:
        valor = p[0]
    elif i == 1:
        valor = p[1] + ALFA * degradacao_memo(p, 0, memo, contador)
    else:
        d1 = degradacao_memo(p, i - 1, memo, contador)
        d2 = degradacao_memo(p, i - 2, memo, contador)
        valor = p[i] + ALFA * d1 + BETA * max(0.0, d1 - d2)
    memo[i] = valor
    return valor


def degradacao_tabulacao(p):
    \"\"\"Versão 3 — iterativa com tabulação (bottom-up). O(n) tempo, sem pilha de recursão.

    Args:
        p (list[float]): penalidades mensais.

    Returns:
        list[float]: a série completa D(0), D(1), ..., D(n-1).
    \"\"\"
    n = len(p)
    tabela = [0.0] * n
    tabela[0] = p[0]
    if n > 1:
        tabela[1] = p[1] + ALFA * tabela[0]
    for i in range(2, n):
        tabela[i] = p[i] + ALFA * tabela[i - 1] + BETA * max(0.0, tabela[i - 1] - tabela[i - 2])
    return tabela
""")

md(r"""
### 1.3 As três versões dão o mesmo resultado?

A série completa tem 44 meses, longa demais para a recursão pura (estimamos o custo abaixo). Por isso a comparação das **três** versões é feita nos **últimos 24 meses** de cada uma das 197 escadas; memoizada e tabulação também são comparadas na série completa.
""")

code(r"""
JANELA = 24
linhas = []
for cd, p_total in series_p.items():
    p = p_total[-JANELA:]
    c_rec, c_memo = [0], [0]
    t0 = time.perf_counter(); d_rec = degradacao_recursiva(p, JANELA - 1, c_rec); t_rec = time.perf_counter() - t0
    t0 = time.perf_counter(); d_memo = degradacao_memo(p, JANELA - 1, {}, c_memo); t_memo = time.perf_counter() - t0
    t0 = time.perf_counter(); d_tab = degradacao_tabulacao(p)[-1]; t_tab = time.perf_counter() - t0
    linhas.append({"cd_escada": cd, "D_rec": d_rec, "D_memo": d_memo, "D_tab": d_tab,
                   "chamadas_rec": c_rec[0], "chamadas_memo": c_memo[0],
                   "ms_rec": 1e3 * t_rec, "ms_memo": 1e3 * t_memo, "ms_tab": 1e3 * t_tab})
comparacao = pd.DataFrame(linhas)

iguais_24 = np.allclose(comparacao.D_rec, comparacao.D_memo) and np.allclose(comparacao.D_memo, comparacao.D_tab)
iguais_44 = all(math.isclose(degradacao_memo(p, len(p) - 1, {}), degradacao_tabulacao(p)[-1]) for p in series_p.values())
print(f"Janela de {JANELA} meses — as três versões coincidem nas {len(comparacao)} escadas: {iguais_24}")
print(f"Série completa de {len(MESES)} meses — memoizada e tabulação coincidem: {iguais_44}")
print(f"Diferença máxima recursiva × tabulação: {np.max(np.abs(comparacao.D_rec - comparacao.D_tab)):.2e}\n")
tot = comparacao[["chamadas_rec", "chamadas_memo", "ms_rec", "ms_memo", "ms_tab"]].sum()
print(tot.round(1).to_string())

# Custo estimado da recursão pura na série completa: C(0)=1, C(1)=2, C(i)=1+C(i-1)+C(i-2)
C = [1, 2]
for i in range(2, len(MESES)):
    C.append(1 + C[-1] + C[-2])
us_por_chamada = 1e3 * tot.ms_rec / tot.chamadas_rec
estimativa_h = C[-1] * us_por_chamada / 1e6 / 3600
print(f"\nRecursão pura com {len(MESES)} meses: {C[-1]:,} chamadas por escada "
      f"≈ {estimativa_h * 60:.0f} min por escada ≈ {estimativa_h * len(series_p):.0f} h para as {len(series_p)} escadas")
""")

md(r"""
### 1.4 Medição: como o custo cresce com o tamanho da série

Usamos séries de tamanho $n$ crescente sorteadas (com reposição) das penalidades mensais reais. Cada tempo é a mediana de várias execuções. A recursão pura vai só até $n = 28$; memoizada e tabulação vão até 5 000 meses, para mostrar o comportamento linear.
""")

code(r"""
def medir(func, repeticoes=5):
    \"\"\"Mediana do tempo de execução (ms) de func() em algumas repetições.\"\"\"
    tempos = []
    for _ in range(repeticoes):
        t0 = time.perf_counter(); func(); tempos.append(time.perf_counter() - t0)
    return 1e3 * float(np.median(tempos))

rng = np.random.default_rng(7)
serie_longa = list(rng.choice(P.values.ravel(), size=6000, replace=True))

medicoes = []
for n in [5, 10, 15, 20, 22, 24, 26, 28]:
    p = serie_longa[:n]
    c = [0]; degradacao_recursiva(p, n - 1, c)
    cm = [0]; degradacao_memo(p, n - 1, {}, cm)
    medicoes.append({"n": n, "chamadas_rec": c[0], "chamadas_memo": cm[0],
                     "ms_rec": medir(lambda: degradacao_recursiva(p, n - 1), 3),
                     "ms_memo": medir(lambda: degradacao_memo(p, n - 1, {})),
                     "ms_tab": medir(lambda: degradacao_tabulacao(p))})
for n in [44, 100, 1000, 5000]:
    p = serie_longa[:n]
    cm = [0]; degradacao_memo(p, n - 1, {}, cm)
    medicoes.append({"n": n, "chamadas_rec": C[-1] if n == 44 else np.nan, "chamadas_memo": cm[0], "ms_rec": np.nan,
                     "ms_memo": medir(lambda: degradacao_memo(p, n - 1, {})),
                     "ms_tab": medir(lambda: degradacao_tabulacao(p))})
medicoes = pd.DataFrame(medicoes)
display(medicoes.round(4))

fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
m = medicoes.dropna(subset=["ms_rec"])
ax[0].semilogy(m.n, m.chamadas_rec, "o-", label="recursiva pura")
ax[0].semilogy(m.n, m.chamadas_memo, "s-", label="memoizada")
ax[0].semilogy([44], [C[-1]], "o", mfc="none", color="C0", label=f"recursiva, 44 meses (estimado)")
ax[0].set(title="Chamadas de função por tamanho da série", xlabel="n (meses)", ylabel="chamadas (escala log)")
ax[0].legend()
ax[1].loglog(medicoes.n, medicoes.ms_rec, "o-", label="recursiva pura")
ax[1].loglog(medicoes.n, medicoes.ms_memo, "s-", label="memoizada (dicionário)")
ax[1].loglog(medicoes.n, medicoes.ms_tab, "^-", label="tabulação")
ax[1].set(title="Tempo de execução (mediana)", xlabel="n (meses, escala log)", ylabel="ms (escala log)")
ax[1].legend()
plt.tight_layout(); plt.savefig(FIGURAS / "tempo_degradacao.png", bbox_inches="tight"); plt.show()

razao = medicoes.dropna(subset=["ms_rec"]).set_index("n").chamadas_rec
print("Crescimento das chamadas da recursiva a cada +2 meses:",
      (razao.loc[[24, 26, 28]].values / razao.loc[[22, 24, 26]].values).round(3), "(φ² ≈ 2,618)")
""")

md(r"""
**Interpretação.**

- **Resultados idênticos.** As três versões produzem o mesmo $D$ para as 197 escadas. Memoização e tabulação mudam **o custo**, não **a resposta**.
- **Recursiva pura é exponencial.** O número de chamadas multiplica-se por 2,618 a cada dois meses a mais, exatamente $\varphi^2$. Na janela de 24 meses já são 121 392 chamadas por escada (24 milhões nas 197 escadas, contra 9 062 da memoizada). Na série real de 44 meses seriam 1,8 bilhão de chamadas por escada: cerca de 7 minutos por escada e quase um dia inteiro para a frota.
- **Memoizada é linear** ($2n - 2$ chamadas: cada mês é calculado uma vez e consultado no dicionário uma vez), mas depende da pilha de recursão, cujo limite precisamos aumentar para séries longas.
- **Tabulação é linear, não usa pilha** e devolve a série inteira de $D$. Para séries longas ela também é mais rápida que a memoizada, que paga o custo das chamadas de função e das consultas ao dicionário. É a versão adotada no ranking e no restante do projeto.

### 1.5 Ranking das escadas por criticidade

A **criticidade** é a degradação acumulada no último mês (ago/2026), calculada pela tabulação sobre os 44 meses. Como $D$ não tem uma escala física, as classes são definidas pela **posição na frota**, o que transforma o ranking numa fila de atendimento:

| Classe | Posição no ranking das 197 escadas |
|---|---|
| Crítica | 5% com maior $D$ (9 escadas) |
| Alta | até 20% (30 escadas) |
| Média | até 50% (59 escadas) |
| Baixa | 50% restantes (99 escadas) |

A coluna `tendencia` compara $D$ de agosto/2026 com o de seis meses antes: mais de 20% acima é "piorando", mais de 20% abaixo é "melhorando".
""")

code(r"""
serie_D = {cd: degradacao_tabulacao(p) for cd, p in series_p.items()}
ult12 = falhas[falhas.mes >= MESES[-12]]

ranking = pd.DataFrame({"cd_escada": list(serie_D), "criticidade": [s[-1] for s in serie_D.values()],
                        "D_6m_atras": [s[-7] for s in serie_D.values()]}).merge(escadas[["cd_escada", "id_estacao"]])
ranking["estacao"] = ranking.id_estacao.map(nomes_est)
ranking["falhas_12m"] = ranking.cd_escada.map(ult12.groupby("cd_escada").size()).fillna(0).astype(int)
ranking["horas_parada_12m"] = ranking.cd_escada.map(ult12.groupby("cd_escada").horas_parada.sum()).fillna(0).round(0)
ranking["componente_principal"] = ranking.cd_escada.map(
    ult12.dropna(subset=["componente"]).groupby("cd_escada").componente.agg(lambda s: s.value_counts().index[0])).fillna("—")
ranking["tendencia"] = np.where(ranking.criticidade > 1.2 * ranking.D_6m_atras, "piorando",
                                np.where(ranking.criticidade < 0.8 * ranking.D_6m_atras, "melhorando", "estável"))
ranking = ranking.sort_values("criticidade", ascending=False).reset_index(drop=True)
pct = (ranking.index + 1) / len(ranking)
ranking["classe"] = np.select([pct <= 0.05, pct <= 0.20, pct <= 0.50], ["Crítica", "Alta", "Média"], "Baixa")
ranking.index = ranking.index + 1
ranking.index.name = "posição"

colunas = ["cd_escada", "estacao", "criticidade", "classe", "tendencia", "falhas_12m", "horas_parada_12m", "componente_principal"]
display(ranking[colunas].head(20).round(1))
print(ranking.classe.value_counts().reindex(["Crítica", "Alta", "Média", "Baixa"]).to_string())
""")

code(r"""
# O que a degradação acumulada acrescenta a uma simples contagem de falhas?
ranking["pos_D"] = ranking.index
ranking["pos_contagem"] = ranking.falhas_12m.rank(ascending=False, method="min").astype(int)
rho = ranking[["criticidade", "falhas_12m"]].corr(method="spearman").iloc[0, 1]
print(f"Correlação de Spearman entre D e falhas nos últimos 12 meses: {rho:.2f}")
top20_D, top20_cont = set(ranking.cd_escada.head(20)), set(ranking.nsmallest(20, "pos_contagem").cd_escada)
print(f"Escadas em comum no top 20 dos dois critérios: {len(top20_D & top20_cont)} de 20")
ranking["subiu"] = ranking.pos_contagem - ranking.pos_D
display(ranking.sort_values("subiu", ascending=False).head(5)[
    ["cd_escada", "pos_D", "pos_contagem", "falhas_12m", "horas_parada_12m", "tendencia"]])
""")

code(r"""
cores = {"Crítica": "#c0392b", "Alta": "#e67e22", "Média": "#f1c40f", "Baixa": "#27ae60"}
fig, ax = plt.subplots(1, 2, figsize=(13, 5.4), gridspec_kw={"width_ratios": [1, 1.15]})
r = ranking.head(25).iloc[::-1]
ax[0].barh(r.cd_escada, r.criticidade, color=[cores[c] for c in r.classe])
ax[0].set(title="25 escadas mais críticas (degradação acumulada em ago/2026)", xlabel="D")
ax[0].tick_params(axis="y", labelsize=8)
from matplotlib.patches import Patch
ax[0].legend(handles=[Patch(color=cores[c], label=c) for c in ["Crítica", "Alta"]], loc="lower right")
datas = MESES.to_timestamp()
for cd in ranking.cd_escada.head(5):
    ax[1].plot(datas, serie_D[cd], marker=".", label=cd)
mediana = np.median(np.array(list(serie_D.values())), axis=0)
ax[1].plot(datas, mediana, color="grey", ls=":", lw=2, label="mediana da frota")
ax[1].set(title="Evolução de D: 5 mais críticas × mediana da frota", ylabel="D(i)")
ax[1].xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
ax[1].legend(fontsize=8)
plt.tight_layout(); plt.savefig(FIGURAS / "ranking_criticidade.png", bbox_inches="tight"); plt.show()
""")

md(r"""
**Interpretação.**

- **Onde está a degradação.** Das 9 escadas críticas, 4 ficam em Pinheiros, 2 na Paulista, 2 na Luz e 1 em Vila Sônia. São as estações de integração e de maior movimento da linha. Pinheiros também é a estação com mais escadas (32).
- **A 1ª do ranking não é a que mais falha.** A PTA-ER15 tem 75 falhas nos últimos 12 meses, contra 129 da PIN-ER24. Ela lidera porque somou 532 horas parada e está **piorando**: o termo de aceleração $\beta$ a coloca à frente de escadas com histórico pior, mas estável.
- **O que $D$ acrescenta a uma contagem simples.** A correlação com o número de falhas é alta (Spearman 0,89), mas o top 20 dos dois critérios só coincide em 14 escadas. A diferença está nas **paradas longas**. A PIN-ER15 tem só 25 falhas em 12 meses (128ª por contagem), mas ficou 3 823 horas parada por problema nas correntes do corrimão; pela degradação acumulada, ela sobe para a 18ª posição. Uma contagem simples esconderia esse caso.
- **Componentes recorrentes.** Rolete de degrau, sensores de presença e dispositivos de segurança aparecem repetidamente entre as mais críticas. O componente principal de cada escada orienta a ordem de serviço: o que verificar e quais peças levar.
- **Limites.** $D$ mede o **histórico de falhas**, não a condição física. Os pesos, $\alpha$ e $\beta$, foram definidos por critério técnico do squad e precisam ser validados com a engenharia da Motiva. Os sensores de vibração, temperatura e óleo previstos no projeto entrariam como novas parcelas da penalidade mensal, sem mudar o algoritmo.
""")


