# ============================================================================
md(r"""
# SafeStair — Dynamic Programming · Versão com sensores (simulação)
**Challenge Motiva + FIAP 2026/2027 · Engenharia de Software · Turma 2ESPR · Squad 6**

| Integrante | RM |
|---|---|
| Marcelo Checchia Pivello de Toledo | 538697 |
| Nícolas Miguel Bittencourt Tanajura | 568108 |
| Rafael Benez Martins | 574994 |

> **Este notebook é complementar ao `notebook.ipynb`.** O notebook principal usa o dataset real da Motiva (histórico de falhas do SAP). Este aplica **os mesmos algoritmos** ao tipo de dado que o SafeStair propõe coletar: leituras de sensores de vibração, temperatura, corrente/tensão, trepidação, nível de óleo e velocidade. Como a Linha 4 ainda não tem esses sensores, as leituras são **simuladas** (`scripts/gerar_sensores.py`, semente fixa) para as **197 escadas reais**, e os perfis de falha são sorteados, **sem relação com o histórico do SAP**.

O objetivo é mostrar que a camada algorítmica está pronta para receber a telemetria e que os limites usados são os mesmos do `ManutencaoService` (DDD-Java) e do Database Design.

1. **Degradação acumulada** por escada ao longo das leituras diárias, em três versões, com medição e **ranking por criticidade**.
2. **Rede de estações como grafo**, com **BFS** e **Dijkstra** a partir da base.
3. **A\*** com heurística justificada × Dijkstra.
4. **`planejar_turno(base, horas)`** sobre o ranking dos sensores.
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
FIGURAS = Path("figuras") / "sensores"; FIGURAS.mkdir(parents=True, exist_ok=True)

leituras = pd.read_csv(DADOS / "sensores" / "leituras_sensores.csv", parse_dates=["dt_leitura"])
escadas = pd.read_csv(DADOS / "escadas.csv")
rede = json.loads((DADOS / "rede_estacoes.json").read_text(encoding="utf-8"))
nomes_est = {v["id"]: v["nome"] for v in rede["vertices"]}

leituras = leituras.sort_values(["cd_escada", "dt_leitura"]).reset_index(drop=True)
print(f"Leituras simuladas: {len(leituras)} linhas · {leituras.cd_escada.nunique()} escadas · "
      f"{leituras.dt_leitura.min():%d/%m/%Y} a {leituras.dt_leitura.max():%d/%m/%Y}")
print(f"Rede: {len(rede['vertices'])} vértices · {len(rede['arestas'])} arestas · base = {rede['base']}")
leituras.head()
""")

md(r"""
---
## Parte 1 — Degradação acumulada (recursão, memoização e tabulação)

### 1.1 Penalidade de cada leitura

Cada leitura diária recebe uma **penalidade** $p_i$, em pontos, que soma o quanto cada variável se afastou da faixa normal. Os limites de vibração, temperatura, nível de óleo e trepidação são **os mesmos do `ManutencaoService`**. Corrente, tensão e velocidade, que o Java ainda não usa, entram com limites relativos ao valor nominal.

Para cada variável, a severidade é $s = \min\left(2,\ \max\left(0,\ \frac{\text{desvio} - \text{normal}}{\text{crítico} - \text{normal}}\right)\right)$: vale 0 na faixa normal, 1 no limite crítico e satura em 2. A penalidade da variável é $s \times \text{peso}$, em que o peso é a penalidade crítica do Java. A escala é contínua, e não em degraus como no Java, o que separa melhor duas escadas que estão ambas "em atenção".
""")

code(r"""
TENSAO_NOMINAL, VELOCIDADE_NOMINAL, CORRENTE_NOMINAL = 380.0, 0.65, 30.0

# variável: (tipo, limite normal, limite crítico, peso em pontos)
LIMITES = {
    "vibracao_mm_s":  ("acima",       2.0,  4.5, 25),  # mm/s
    "temperatura_c":  ("acima",      45.0, 65.0, 30),  # °C
    "trepidacao_hz":  ("acima",       3.5,  6.0, 20),  # Hz
    "nivel_oleo_pct": ("abaixo",     80.0, 40.0, 25),  # %
    "corrente_a":     ("acima_rel",  1.10, 1.30, 15),  # corrente / corrente nominal
    "tensao_v":       ("desvio_rel", 0.05, 0.10, 10),  # |V - 380| / 380
    "velocidade_m_s": ("desvio_rel", 0.02, 0.08, 15),  # |v - 0,65| / 0,65
}
NOMINAL = {"corrente_a": CORRENTE_NOMINAL, "tensao_v": TENSAO_NOMINAL, "velocidade_m_s": VELOCIDADE_NOMINAL}


def severidade(valor, tipo, normal, critico, nominal=None):
    \"\"\"Severidade de uma variável: 0 na faixa normal, 1 no limite crítico, no máximo 2.

    Args:
        valor (float): valor medido.
        tipo (str): 'acima', 'abaixo', 'acima_rel' ou 'desvio_rel'.
        normal (float): limite da faixa normal.
        critico (float): limite crítico.
        nominal (float, opcional): referência para os tipos relativos.

    Returns:
        float: severidade entre 0 e 2.
    \"\"\"
    if tipo == "acima":
        excesso = (valor - normal) / (critico - normal)
    elif tipo == "abaixo":
        excesso = (normal - valor) / (normal - critico)
    elif tipo == "acima_rel":
        excesso = (valor / nominal - normal) / (critico - normal)
    else:  # desvio_rel
        excesso = (abs(valor - nominal) / nominal - normal) / (critico - normal)
    return min(2.0, max(0.0, excesso))


def penalidades_por_variavel(linha):
    \"\"\"Penalidade (pontos) de cada variável de uma leitura.\"\"\"
    return {var: peso * severidade(linha[var], tipo, normal, crit, NOMINAL.get(var))
            for var, (tipo, normal, crit, peso) in LIMITES.items()}


def health_score_java(r):
    \"\"\"Replica o ManutencaoService (DDD-Java): parte de 100 e desconta penalidades em degraus.

    Returns:
        tuple[float, str]: (health score, situação).
    \"\"\"
    desc, critico = 0, False
    regras = [("vibracao_mm_s", 2.0, 4.5, 12, 25, ">"), ("temperatura_c", 45, 65, 12, 30, ">"),
              ("nivel_oleo_pct", 80, 40, 10, 25, "<"), ("trepidacao_hz", 3.5, 6.0, 10, 20, ">")]
    for var, lim_at, lim_cr, p_at, p_cr, op in regras:
        v = r[var]
        cr = v > lim_cr if op == ">" else v < lim_cr
        at = v > lim_at if op == ">" else v < lim_at
        if cr: desc += p_cr; critico = True
        elif at: desc += p_at
    hs = max(0, 100 - desc)
    if hs < 70 or critico: sit = "INTERVENCAO RECOMENDADA"
    elif hs < 85: sit = "ATENCAO"
    else: sit = "OPERANDO NORMALMENTE"
    return hs, sit


pen = leituras.apply(penalidades_por_variavel, axis=1, result_type="expand")
leituras["penalidade"] = pen.sum(axis=1).round(3)
leituras["variavel_dominante"] = pen.idxmax(axis=1).where(pen.max(axis=1) > 0, "—")
leituras[["hs_java", "situacao_java"]] = leituras.apply(health_score_java, axis=1, result_type="expand")
print("Penalidade por leitura:", leituras.penalidade.describe(percentiles=[.5, .9, .99]).round(1).to_dict())
leituras[["cd_escada", "dt_leitura", "penalidade", "variavel_dominante", "hs_java", "situacao_java"]].tail(5)
""")

md(r"""
### 1.2 Recorrência da degradação acumulada

A mesma recorrência do notebook principal, agora sobre as leituras diárias:

$$
D(0) = p_0, \qquad D(1) = p_1 + \alpha\,D(0)
$$
$$
D(i) = p_i + \alpha\,D(i-1) + \beta\,\max\bigl(0,\ D(i-1) - D(i-2)\bigr), \quad i \ge 2
$$

- $\alpha = 0{,}85$ é a **memória**: o desgaste dos dias anteriores continua pesando, mas perde 15% por leitura.
- $\beta = 0{,}5$ é o **termo de aceleração**: metade da piora recente é somada, então uma escada piorando rápido passa à frente de outra com o mesmo nível estável.

Como $D(i)$ depende de $D(i-1)$ **e** de $D(i-2)$, a recursão pura recalcula subproblemas como na sequência de Fibonacci.
""")

code(r"""
ALFA, BETA = 0.85, 0.5


def degradacao_recursiva(p, i, contador=None):
    \"\"\"Versão 1 — recursiva pura. Complexidade O(φ^n) chamadas (φ ≈ 1,618).

    Args:
        p (list[float]): penalidades das leituras, em ordem cronológica.
        i (int): índice da leitura cuja degradação acumulada se quer.
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
        p (list[float]): penalidades das leituras.
        i (int): índice da leitura.
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
        p (list[float]): penalidades das leituras.

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

Cada escada tem 24 leituras diárias (01 a 24/09/2026), tamanho em que a recursão pura ainda roda, então as três versões são comparadas na série completa das 197 escadas.
""")

code(r"""
series_p = {cd: g.penalidade.tolist() for cd, g in leituras.groupby("cd_escada")}

linhas = []
for cd, p in series_p.items():
    n = len(p)
    c_rec, c_memo = [0], [0]
    t0 = time.perf_counter(); d_rec = degradacao_recursiva(p, n - 1, c_rec); t_rec = time.perf_counter() - t0
    t0 = time.perf_counter(); d_memo = degradacao_memo(p, n - 1, {}, c_memo); t_memo = time.perf_counter() - t0
    t0 = time.perf_counter(); d_tab = degradacao_tabulacao(p)[-1]; t_tab = time.perf_counter() - t0
    linhas.append({"cd_escada": cd, "D_rec": d_rec, "D_memo": d_memo, "D_tab": d_tab,
                   "chamadas_rec": c_rec[0], "chamadas_memo": c_memo[0],
                   "ms_rec": 1e3 * t_rec, "ms_memo": 1e3 * t_memo, "ms_tab": 1e3 * t_tab})
comparacao = pd.DataFrame(linhas)

iguais = np.allclose(comparacao.D_rec, comparacao.D_memo) and np.allclose(comparacao.D_memo, comparacao.D_tab)
print(f"As três versões coincidem nas {len(comparacao)} escadas:", iguais)
print(f"Diferença máxima recursiva × tabulação: {np.max(np.abs(comparacao.D_rec - comparacao.D_tab)):.2e}\n")
print(comparacao[["chamadas_rec", "chamadas_memo", "ms_rec", "ms_memo", "ms_tab"]].sum().round(1).to_string())
""")

md(r"""
### 1.4 Medição: como o custo cresce com o número de leituras

Séries de tamanho $n$ crescente, sorteadas das penalidades simuladas. Cada tempo é a mediana de várias execuções. Se os sensores enviarem uma leitura por hora, um único mês já tem 720 leituras por escada; por isso medimos memoizada e tabulação até 5 000.
""")

code(r"""
def medir(func, repeticoes=5):
    \"\"\"Mediana do tempo de execução (ms) de func() em algumas repetições.\"\"\"
    tempos = []
    for _ in range(repeticoes):
        t0 = time.perf_counter(); func(); tempos.append(time.perf_counter() - t0)
    return 1e3 * float(np.median(tempos))

rng = np.random.default_rng(7)
serie_longa = list(rng.choice(leituras.penalidade.values, size=6000, replace=True))

medicoes = []
for n in [5, 10, 15, 20, 22, 24, 26, 28]:
    p = serie_longa[:n]
    c = [0]; degradacao_recursiva(p, n - 1, c)
    cm = [0]; degradacao_memo(p, n - 1, {}, cm)
    medicoes.append({"n": n, "chamadas_rec": c[0], "chamadas_memo": cm[0],
                     "ms_rec": medir(lambda: degradacao_recursiva(p, n - 1), 3),
                     "ms_memo": medir(lambda: degradacao_memo(p, n - 1, {})),
                     "ms_tab": medir(lambda: degradacao_tabulacao(p))})
for n in [100, 720, 1000, 5000]:
    p = serie_longa[:n]
    cm = [0]; degradacao_memo(p, n - 1, {}, cm)
    medicoes.append({"n": n, "chamadas_rec": np.nan, "chamadas_memo": cm[0], "ms_rec": np.nan,
                     "ms_memo": medir(lambda: degradacao_memo(p, n - 1, {})),
                     "ms_tab": medir(lambda: degradacao_tabulacao(p))})
medicoes = pd.DataFrame(medicoes)
display(medicoes.round(4))

fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
m = medicoes.dropna(subset=["ms_rec"])
ax[0].semilogy(m.n, m.chamadas_rec, "o-", label="recursiva pura")
ax[0].semilogy(m.n, m.chamadas_memo, "s-", label="memoizada")
ax[0].set(title="Chamadas de função por tamanho da série", xlabel="n (leituras)", ylabel="chamadas (escala log)")
ax[0].legend()
ax[1].loglog(medicoes.n, medicoes.ms_rec, "o-", label="recursiva pura")
ax[1].loglog(medicoes.n, medicoes.ms_memo, "s-", label="memoizada (dicionário)")
ax[1].loglog(medicoes.n, medicoes.ms_tab, "^-", label="tabulação")
ax[1].set(title="Tempo de execução (mediana)", xlabel="n (leituras, escala log)", ylabel="ms (escala log)")
ax[1].legend()
plt.tight_layout(); plt.savefig(FIGURAS / "tempo_degradacao.png", bbox_inches="tight"); plt.show()

razao = m.set_index("n").chamadas_rec
print("Crescimento das chamadas da recursiva a cada +2 leituras:",
      (razao.loc[[24, 26, 28]].values / razao.loc[[22, 24, 26]].values).round(3), "(φ² ≈ 2,618)")
""")

md(r"""
**Interpretação.**

- **Resultados idênticos.** As três versões produzem exatamente o mesmo $D$ nas 197 escadas. Memoização e tabulação mudam **o custo**, não **a resposta**.
- **Recursiva pura é exponencial.** O número de chamadas cresce 2,618 vezes a cada duas leituras a mais, exatamente $\varphi^2$. Só com 24 leituras diárias são 121 392 chamadas por escada, ou 24 milhões para a frota, contra 9 062 da memoizada.
- **Com telemetria real, só a tabulação serve.** Uma leitura por hora gera 720 leituras por escada em um mês. Com esse volume a recursão pura não termina, e a memoizada depende de aumentar o limite de pilha do Python. A tabulação processa as 720 leituras em fração de milissegundo, sem pilha. É a versão adotada no ranking.
""")

md(r"""
### 1.5 Ranking das escadas por criticidade

A **criticidade** é a degradação acumulada na última leitura, $D(n-1)$. Aqui as classes podem usar **limites fixos**, porque a penalidade tem escala física: com penalidade constante $p$ e sem aceleração, $D$ converge para $p/(1-\alpha) \approx 6{,}7\,p$. Assim, $D \ge 200$ corresponde a manter cerca de 30 pontos de penalidade, ou seja, pelo menos uma variável no limite crítico.

| Classe | Degradação acumulada $D$ |
|---|---|
| Crítica | $D \ge 200$ |
| Alta | $100 \le D < 200$ |
| Média | $40 \le D < 100$ |
| Baixa | $D < 40$ |
""")

code(r"""
def classe_criticidade(d):
    \"\"\"Classe de criticidade a partir da degradação acumulada final.\"\"\"
    if d >= 200: return "Crítica"
    if d >= 100: return "Alta"
    if d >= 40:  return "Média"
    return "Baixa"

ultimas = leituras.groupby("cd_escada").tail(1).set_index("cd_escada")
serie_D = {cd: degradacao_tabulacao(p) for cd, p in series_p.items()}

ranking = (pd.DataFrame({"cd_escada": list(serie_D), "criticidade": [s[-1] for s in serie_D.values()]})
           .merge(escadas[["cd_escada", "id_estacao"]], on="cd_escada"))
ranking["estacao"] = ranking.id_estacao.map(nomes_est)
ranking["classe"] = ranking.criticidade.apply(classe_criticidade)
ranking["penalidade_ultima"] = ranking.cd_escada.map(ultimas.penalidade)
ranking["componente_principal"] = ranking.cd_escada.map(ultimas.variavel_dominante)
ranking["hs_java"] = ranking.cd_escada.map(ultimas.hs_java)
ranking["situacao_java"] = ranking.cd_escada.map(ultimas.situacao_java)
ranking = ranking.sort_values("criticidade", ascending=False).reset_index(drop=True)
ranking.index = ranking.index + 1
ranking.index.name = "posição"
display(ranking.head(20).round(1))
print(ranking.classe.value_counts().reindex(["Crítica", "Alta", "Média", "Baixa"]).to_string())
print("\nSituação no Java × classe pelo SafeStair:")
display(pd.crosstab(ranking.situacao_java, ranking.classe).reindex(columns=["Crítica", "Alta", "Média", "Baixa"], fill_value=0))
""")

code(r"""
cores = {"Crítica": "#c0392b", "Alta": "#e67e22", "Média": "#f1c40f", "Baixa": "#27ae60"}
from matplotlib.patches import Patch
fig, ax = plt.subplots(1, 2, figsize=(13, 5.4), gridspec_kw={"width_ratios": [1, 1.15]})
r = ranking.head(25).iloc[::-1]
ax[0].barh(r.cd_escada, r.criticidade, color=[cores[c] for c in r.classe])
for lim in (100, 200):
    ax[0].axvline(lim, color="grey", ls="--", lw=0.8)
ax[0].set(title="25 escadas mais críticas (sensores simulados)", xlabel="D(n-1)")
ax[0].tick_params(axis="y", labelsize=8)
ax[0].legend(handles=[Patch(color=cores[c], label=c) for c in ["Crítica", "Alta", "Média"]], loc="lower right")
datas = leituras.dt_leitura.drop_duplicates().sort_values()
for cd in ranking.cd_escada.head(5):
    ax[1].plot(datas.values, serie_D[cd], marker=".", label=cd)
mediana = np.median(np.array(list(serie_D.values())), axis=0)
ax[1].plot(datas.values, mediana, color="grey", ls=":", lw=2, label="mediana da frota")
ax[1].set(title="Evolução de D: 5 mais críticas × mediana da frota", ylabel="D(i)")
ax[1].xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
ax[1].legend(fontsize=8)
plt.tight_layout(); plt.savefig(FIGURAS / "ranking_criticidade.png", bbox_inches="tight"); plt.show()
""")

md(r"""
**Interpretação.**

- **Coerência com o Java:** as 17 escadas críticas também aparecem como "INTERVENCAO RECOMENDADA" no `ManutencaoService`. Os dois modelos concordam nos casos graves.
- **O ranking desempata o que o Java iguala:** 26 escadas recebem "intervenção recomendada" do Java. A degradação acumulada separa as 17 críticas das 9 que são só Alta e dá a ordem de atendimento.
- **O ranking antecipa o que o Java não vê:** 9 escadas estão "OPERANDO NORMALMENTE" para o Java, mas são Alta para o SafeStair. Em 6 delas o problema dominante é a **velocidade**, que cai por atrito enquanto a corrente sobe, e o Java ainda não usa essas variáveis. As outras 3 têm temperatura subindo dentro da faixa de atenção, mas com tendência de piora que o termo de aceleração capta. Isso é manutenção **preditiva**: agir antes de a regra em degrau disparar.
- **Componentes:** nas críticas dominam vibração (9) e temperatura (8), enquanto nível de óleo lidera entre as de classe Alta (10). Isso orienta a ordem de serviço.
- **Limites:** como os perfis de falha foram sorteados, **a distribuição por estação não tem significado**. O que este notebook demonstra é o método, não o diagnóstico da frota, que está no notebook principal.
""")

