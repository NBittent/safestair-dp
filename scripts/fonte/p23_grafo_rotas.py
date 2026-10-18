# ============================================================================
md(r"""
---
## Parte 2 — Rede de estações como grafo

### 2.1 Modelagem

- **Vértices:** 19 locais das linhas operadas pela Motiva e 1 **base de manutenção** no Pátio Vila Sônia. São as 11 estações da Linha 4-Amarela (ViaQuatro) mais o Terminal Vila Sônia, que são os 12 locais com escadas no dataset, e 7 estações das Linhas 9-Esmeralda e 5-Lilás (ViaMobilidade), ligadas à Linha 4 por Pinheiros.
- **Ids = códigos do SAP:** os vértices da Linha 4 usam os mesmos códigos do campo Local de Instalação (PTA = Paulista, FRE = Oscar Freire, FAL = Faria Lima, MBI = São Paulo-Morumbi, TVS = Terminal Vila Sônia). É isso que liga cada escada do dataset a um vértice.
- **Arestas:** trechos entre estações, com peso em **minutos de deslocamento** da equipe. Trechos que começam em estações de integração (Pinheiros, Santo Amaro) já incluem a baldeação. Na 5-Lilás e na 9-Esmeralda, alguns trechos agregam estações intermediárias não modeladas.
- **Trechos rodoviários:** a equipe também pode sair da base de van. Esses trechos têm **poucas arestas, mas tempo maior** no trânsito, o que faz o BFS e o Dijkstra discordarem.
- **Estrutura:** lista de adjacência (`dict` de vértice para lista de vizinhos), grafo não direcionado.

Coordenadas e tempos são aproximados, adequados para o exercício e não para operação real.
""")

code(r"""
def construir_lista_adjacencia(rede):
    \"\"\"Monta a lista de adjacência não direcionada a partir do JSON da rede.

    Args:
        rede (dict): conteúdo de rede_estacoes.json.

    Returns:
        dict[str, list[tuple[str, float, str]]]: vértice -> [(vizinho, minutos, modo), ...].
    \"\"\"
    adj = {v["id"]: [] for v in rede["vertices"]}
    for a in rede["arestas"]:
        adj[a["origem"]].append((a["destino"], a["minutos"], a["modo"]))
        adj[a["destino"]].append((a["origem"], a["minutos"], a["modo"]))
    for v in adj:
        adj[v].sort()
    return adj

ADJ = construir_lista_adjacencia(rede)
BASE = rede["base"]
COORD = {v["id"]: (v["lat"], v["lon"]) for v in rede["vertices"]}

for v, viz in ADJ.items():
    print(f"{v:>4} -> " + ", ".join(f"{u}({w} min, {m})" for u, w, m in viz))

sem_estacao = set(escadas.id_estacao) - set(ADJ)
print("\nEscadas ligadas a estações do grafo:", len(escadas) - len(sem_estacao), "de", len(escadas))
assert not sem_estacao, f"Escadas sem estação no grafo: {sem_estacao}"
print("Escadas por estação:", escadas.groupby("id_estacao").size().to_dict())
""")

code(r"""
estilo = {"4-Amarela": dict(color="#f2b705", lw=2.5, ls="-"), "9-Esmeralda": dict(color="#1aa37a", lw=2.5, ls="-"),
          "5-Lilás": dict(color="#8e5bb5", lw=2.5, ls="-"), "acesso": dict(color="#34495e", lw=1.2, ls="-"),
          "rodovia": dict(color="#7f8c8d", lw=1.5, ls=":")}
fig, ax = plt.subplots(figsize=(9, 7.5))
for a in rede["arestas"]:
    (y1, x1), (y2, x2) = COORD[a["origem"]], COORD[a["destino"]]
    ax.plot([x1, x2], [y1, y2], **estilo[a["linha"]], zorder=1)
    ax.text((x1 + x2) / 2, (y1 + y2) / 2, f'{a["minutos"]}', fontsize=7, color="#555",
            ha="center", va="center", bbox=dict(fc="white", ec="none", pad=0.5), zorder=2)
qtd = escadas.groupby("id_estacao").size()
for v in rede["vertices"]:
    y, x = v["lat"], v["lon"]
    if v["id"] == BASE:
        ax.scatter(x, y, s=260, marker="*", color="#c0392b", zorder=3)
    else:
        ax.scatter(x, y, s=30 + 12 * qtd.get(v["id"], 0), color="#34495e", zorder=3)
    ax.annotate(v["id"], (x, y), xytext=(5, 5), textcoords="offset points", fontsize=8)
for nome, e in estilo.items():
    ax.plot([], [], **e, label={"rodovia": "van (rodovia)", "acesso": "acesso a pé"}.get(nome, f"Linha {nome}"))
ax.scatter([], [], marker="*", s=150, color="#c0392b", label="base de manutenção")
ax.legend(loc="upper left"); ax.set(title="Rede de estações (peso = minutos; tamanho do ponto = nº de escadas)",
                                    xlabel="longitude", ylabel="latitude")
ax.set_aspect(1 / math.cos(math.radians(-23.58)))
plt.tight_layout(); plt.savefig(FIGURAS / "rede_estacoes.png", bbox_inches="tight"); plt.show()
""")

md(r"""
### 2.2 BFS (menos trechos) e Dijkstra (menor tempo)

- **BFS** explora o grafo em camadas e encontra o caminho com **menos arestas**, ignorando os pesos. Complexidade $O(V + E)$.
- **Dijkstra** usa uma fila de prioridade (heap) para sempre expandir o vértice de menor tempo acumulado e encontra o caminho de **menor tempo**. Complexidade $O((V + E)\log V)$.
- Os dois guardam o **predecessor** de cada vértice, e `reconstruir_rota` volta do destino até a origem para montar o caminho.
""")

code(r"""
def bfs(adj, origem):
    \"\"\"Busca em largura a partir da origem.

    Args:
        adj (dict): lista de adjacência.
        origem (str): vértice inicial.

    Returns:
        tuple[dict, dict]: (trechos até cada vértice, predecessor de cada vértice).
    \"\"\"
    trechos, pai = {origem: 0}, {origem: None}
    fila = deque([origem])
    while fila:
        v = fila.popleft()
        for u, _, _ in adj[v]:
            if u not in trechos:
                trechos[u] = trechos[v] + 1
                pai[u] = v
                fila.append(u)
    return trechos, pai


def dijkstra(adj, origem, destino=None):
    \"\"\"Menor tempo a partir da origem (Dijkstra com heap).

    Args:
        adj (dict): lista de adjacência com pesos em minutos.
        origem (str): vértice inicial.
        destino (str, opcional): se informado, para ao fechar o destino.

    Returns:
        tuple[dict, dict, int]: (tempo até cada vértice, predecessor, vértices expandidos).
    \"\"\"
    dist, pai = {origem: 0.0}, {origem: None}
    heap, fechados, expandidos = [(0.0, origem)], set(), 0
    while heap:
        d, v = heapq.heappop(heap)
        if v in fechados:
            continue
        fechados.add(v); expandidos += 1
        if v == destino:
            break
        for u, w, _ in adj[v]:
            nd = d + w
            if nd < dist.get(u, math.inf):
                dist[u], pai[u] = nd, v
                heapq.heappush(heap, (nd, u))
    return dist, pai, expandidos


def reconstruir_rota(pai, origem, destino):
    \"\"\"Reconstrói o caminho origem -> destino seguindo os predecessores.

    Returns:
        list[str]: vértices do caminho (vazia se o destino não for alcançável).
    \"\"\"
    if destino not in pai:
        return []
    rota, v = [], destino
    while v is not None:
        rota.append(v); v = pai[v]
    rota.reverse()
    return rota if rota[0] == origem else []


def tempo_rota(adj, rota):
    \"\"\"Soma dos minutos dos trechos de uma rota.\"\"\"
    return sum(next(w for u, w, _ in adj[a] if u == b) for a, b in zip(rota, rota[1:]))


trechos_bfs, pai_bfs = bfs(ADJ, BASE)
dist_dij, pai_dij, _ = dijkstra(ADJ, BASE)

linhas = []
for v in sorted(ADJ, key=lambda x: dist_dij[x]):
    if v == BASE:
        continue
    rb, rd = reconstruir_rota(pai_bfs, BASE, v), reconstruir_rota(pai_dij, BASE, v)
    linhas.append({"estação": nomes_est[v], "rota BFS": " → ".join(rb), "trechos BFS": len(rb) - 1,
                   "min BFS": tempo_rota(ADJ, rb), "rota Dijkstra": " → ".join(rd),
                   "trechos Dijkstra": len(rd) - 1, "min Dijkstra": dist_dij[v]})
rotas = pd.DataFrame(linhas)
rotas["ganho (min)"] = rotas["min BFS"] - rotas["min Dijkstra"]
display(rotas)
dif = rotas[rotas["ganho (min)"] > 0]
print(f"Estações em que o BFS escolhe uma rota mais lenta: {len(dif)} de {len(rotas)}; "
      f"ganho médio do Dijkstra nelas: {dif['ganho (min)'].mean():.1f} min; máximo: {dif['ganho (min)'].max():.0f} min")
""")

md(r"""
**Interpretação.**

- Em 13 das 19 estações o BFS escolhe uma rota mais lenta (em média 9,4 min a mais, até 21 min). Nas estações da Linha 4 perto da Paulista, o **BFS escolhe a van** (BASE → PTA), porque é um único trecho, mas ela leva 35 minutos no trânsito; o **Dijkstra prefere o metrô** desde Vila Sônia, com mais trechos e bem menos tempo (22 min até a Paulista). É a diferença entre "menos trechos" e "menor tempo".
- Entre caminhos com o mesmo número de trechos, o BFS fica com o primeiro que encontra, sem olhar o tempo: para São Paulo-Morumbi ele vai pela van até o Butantã (17 min) em vez da van até Vila Sônia (9 min).
- Quando a van também é a opção mais rápida, como para Santo Amaro (25 min de van contra cerca de 38 min de metrô e trem), os dois algoritmos concordam.
- Para o planejamento de manutenção o critério correto é o **tempo**, por isso o `planejar_turno` usa Dijkstra. O BFS serve como referência de quantas baldeações e trocas de modal a rota exige.
""")

# ============================================================================
md(r"""
---
## Parte 3 — Otimização de rotas com A*

### 3.1 Heurística

O A\* expande primeiro os vértices com menor $f(n) = g(n) + h(n)$, em que $g$ é o tempo já gasto e $h$ uma **estimativa do tempo restante**. Usamos:

$$
h(n) = \frac{\text{distância em linha reta}(n,\ \text{destino})}{v_{\max}}, \qquad
v_{\max} = \max_{(a,b) \in E} \frac{\text{distância em linha reta}(a,b)}{\text{minutos}(a,b)}
$$

A distância em linha reta é calculada pela fórmula de haversine sobre as coordenadas das estações, e $v_{\max}$ é a **maior velocidade efetiva** observada em algum trecho da própria rede.

**Por que é admissível (nunca superestima):** em qualquer trecho, $\text{minutos}(a,b) \ge \text{dist}(a,b)/v_{\max}$ pela definição de $v_{\max}$. Somando ao longo de qualquer caminho de $n$ até o destino e usando a desigualdade triangular (a linha reta é o menor percurso), o tempo real é sempre $\ge \text{dist}(n,\text{destino})/v_{\max} = h(n)$. **Consistência** sai do mesmo argumento aplicado a um único trecho: $h(a) \le \text{minutos}(a,b) + h(b)$. Com $h$ consistente, o A\* retorna o caminho ótimo sem reabrir vértices.

Usar a velocidade máxima da própria rede, em vez de um valor fixo como 80 km/h, deixa $h$ o mais informativa possível sem perder a garantia. Para comparar, testamos também $h_{80}$ (80 km/h fixos, mais fraca) e $h = 0$ (que transforma o A\* no próprio Dijkstra).
""")

code(r"""
def haversine_km(a, b):
    \"\"\"Distância em linha reta (km) entre dois vértices, pelas coordenadas.\"\"\"
    (la1, lo1), (la2, lo2) = COORD[a], COORD[b]
    la1, lo1, la2, lo2 = map(math.radians, (la1, lo1, la2, lo2))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))

VMAX = max(haversine_km(a["origem"], a["destino"]) / a["minutos"] for a in rede["arestas"])  # km/min
trecho_vmax = max(rede["arestas"], key=lambda a: haversine_km(a["origem"], a["destino"]) / a["minutos"])
print(f"v_max da rede = {VMAX:.3f} km/min = {VMAX * 60:.1f} km/h "
      f"(trecho {trecho_vmax['origem']}–{trecho_vmax['destino']})")


def heuristica_rede(destino):
    \"\"\"h(n) = distância em linha reta até o destino / v_max da rede (minutos).\"\"\"
    return lambda n: haversine_km(n, destino) / VMAX

def heuristica_80kmh(destino):
    \"\"\"h(n) com velocidade fixa de 80 km/h (admissível, porém mais fraca).\"\"\"
    return lambda n: haversine_km(n, destino) / (80 / 60)

def heuristica_zero(destino):
    \"\"\"h(n) = 0: o A* se reduz ao Dijkstra.\"\"\"
    return lambda n: 0.0


def a_estrela(adj, origem, destino, h):
    \"\"\"Busca A* do caminho de menor tempo.

    Args:
        adj (dict): lista de adjacência com pesos em minutos.
        origem (str): vértice inicial.
        destino (str): vértice final.
        h (callable): heurística h(n) em minutos, admissível e consistente.

    Returns:
        tuple[float, list[str], int]: (tempo mínimo, rota, vértices expandidos).
    \"\"\"
    g, pai = {origem: 0.0}, {origem: None}
    heap, fechados, expandidos = [(h(origem), 0.0, origem)], set(), 0
    while heap:
        _, gv, v = heapq.heappop(heap)
        if v in fechados:
            continue
        fechados.add(v); expandidos += 1
        if v == destino:
            return gv, reconstruir_rota(pai, origem, destino), expandidos
        for u, w, _ in adj[v]:
            ng = gv + w
            if ng < g.get(u, math.inf):
                g[u], pai[u] = ng, v
                heapq.heappush(heap, (ng + h(u), ng, u))
    return math.inf, [], expandidos


# Verificação numérica de admissibilidade e consistência, para todos os pares (n, destino)
viol_adm = viol_cons = 0
for destino in ADJ:
    real, _, _ = dijkstra(ADJ, destino)
    h = heuristica_rede(destino)
    viol_adm += sum(h(n) > real[n] + 1e-9 for n in ADJ)
    viol_cons += sum(h(a) > w + h(b) + 1e-9 for a in ADJ for b, w, _ in ADJ[a])
print("Violações de admissibilidade:", viol_adm, "| violações de consistência:", viol_cons)
""")

md(r"""
### 3.2 A\* comparado ao Dijkstra na rede de estações

Para uma comparação justa, o Dijkstra também para assim que fecha o destino. Medimos o tempo mínimo encontrado, os **vértices expandidos** e o tempo de execução (mediana de 200 repetições) da base até cada estação.
""")

code(r"""
def medir_us(func, rep=200):
    \"\"\"Mediana do tempo de execução de func() em microssegundos.\"\"\"
    t = []
    for _ in range(rep):
        t0 = time.perf_counter(); func(); t.append(time.perf_counter() - t0)
    return 1e6 * float(np.median(t))

linhas = []
for destino in [v for v in ADJ if v != BASE]:
    d_dij, _, exp_dij = dijkstra(ADJ, BASE, destino)
    c_a, rota_a, exp_a = a_estrela(ADJ, BASE, destino, heuristica_rede(destino))
    _, _, exp_80 = a_estrela(ADJ, BASE, destino, heuristica_80kmh(destino))
    linhas.append({"destino": destino, "min Dijkstra": d_dij[destino], "min A*": c_a,
                   "exp Dijkstra": exp_dij, "exp A* (v_max)": exp_a, "exp A* (80 km/h)": exp_80,
                   "µs Dijkstra": medir_us(lambda: dijkstra(ADJ, BASE, destino)),
                   "µs A*": medir_us(lambda: a_estrela(ADJ, BASE, destino, heuristica_rede(destino)))})
astar_rede = pd.DataFrame(linhas)
display(astar_rede.round(1))
print("Mesmo tempo ótimo em todos os destinos:", np.allclose(astar_rede["min Dijkstra"], astar_rede["min A*"]))
tot = astar_rede[["exp Dijkstra", "exp A* (v_max)", "exp A* (80 km/h)"]].sum()
print(f"Expansões totais — Dijkstra: {tot.iloc[0]} | A* v_max: {tot.iloc[1]} ({100 * (1 - tot.iloc[1] / tot.iloc[0]):.0f}% a menos)"
      f" | A* 80 km/h: {tot.iloc[2]} ({100 * (1 - tot.iloc[2] / tot.iloc[0]):.0f}% a menos)")
""")

md(r"""
### 3.3 Escalabilidade: uma malha urbana maior

A rede do exercício tem só 20 vértices, então qualquer algoritmo termina em microssegundos. Para ver como a diferença cresce, geramos uma **malha urbana sintética** de 60 × 60 cruzamentos (3 600 vértices, espaçamento de 0,5 km) com tempos de trecho entre 1× e 2,5× o tempo a 30 km/h (trânsito variável). A heurística é a mesma ideia: distância em linha reta dividida pela maior velocidade efetiva da malha. Rodamos 40 pares origem–destino aleatórios.
""")

code(r"""
def malha_urbana(lado=60, passo_km=0.5, semente=3):
    \"\"\"Cria uma malha urbana sintética (lista de adjacência + coordenadas em km).\"\"\"
    rnd = random.Random(semente)
    coord = {(i, j): (i * passo_km, j * passo_km) for i in range(lado) for j in range(lado)}
    adj = {v: [] for v in coord}
    for (i, j) in coord:
        for di, dj in ((1, 0), (0, 1)):
            u = (i + di, j + dj)
            if u in coord:
                w = passo_km / 0.5 * rnd.uniform(1.0, 2.5)   # 0,5 km/min = 30 km/h
                adj[(i, j)].append((u, w, "rua")); adj[u].append(((i, j), w, "rua"))
    return adj, coord

ADJ_M, COORD_M = malha_urbana()
VMAX_M = max(math.dist(COORD_M[a], COORD_M[b]) / w for a in ADJ_M for b, w, _ in ADJ_M[a])
rnd = random.Random(11)
pares = [(rnd.choice(list(ADJ_M)), rnd.choice(list(ADJ_M))) for _ in range(40)]

res = []
for o, d in pares:
    hm = lambda n, d=d: math.dist(COORD_M[n], COORD_M[d]) / VMAX_M
    dd, _, ed = dijkstra(ADJ_M, o, d)
    ca, _, ea = a_estrela(ADJ_M, o, d, hm)
    res.append({"min Dijkstra": dd[d], "min A*": ca, "exp Dijkstra": ed, "exp A*": ea,
                "ms Dijkstra": medir_us(lambda: dijkstra(ADJ_M, o, d), 5) / 1e3,
                "ms A*": medir_us(lambda: a_estrela(ADJ_M, o, d, hm), 5) / 1e3})
malha = pd.DataFrame(res)
print("Mesmo tempo ótimo em todos os pares:", np.allclose(malha["min Dijkstra"], malha["min A*"]))
resumo = malha[["exp Dijkstra", "exp A*", "ms Dijkstra", "ms A*"]].agg(["mean", "median"]).round(1)
display(resumo)

fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
ax[0].bar(["Dijkstra", "A* (v_max)", "A* (80 km/h)"], tot.values, color=["#7f8c8d", "#2980b9", "#85c1e9"])
ax[0].set(title="Rede de estações: vértices expandidos (soma, 19 destinos)", ylabel="vértices expandidos")
ax[1].scatter(malha["exp Dijkstra"], malha["exp A*"], color="#2980b9")
lim = malha["exp Dijkstra"].max() * 1.05
ax[1].plot([0, lim], [0, lim], "k--", lw=0.8, label="igual ao Dijkstra")
ax[1].set(title="Malha 60×60: expansões por consulta", xlabel="Dijkstra", ylabel="A*")
ax[1].legend()
plt.tight_layout(); plt.savefig(FIGURAS / "astar_vs_dijkstra.png", bbox_inches="tight"); plt.show()
""")

md(r"""
**Interpretação.**

- **Mesmo resultado, menos trabalho.** O A\* encontrou exatamente o mesmo tempo mínimo que o Dijkstra em todos os destinos, como garante a heurística admissível e consistente (verificada numericamente acima, sem nenhuma violação).
- **Na rede das estações o ganho em expansões é modesto e não vira ganho de tempo.** O A\* expande 14% menos vértices no total (180 contra 209), com o maior efeito nos destinos da Linha 9 (Santo Amaro: 6 expansões contra 13), porque deixa de explorar o lado da rede que se afasta do destino. Mesmo assim, em tempo de relógio ele leva cerca de 2 vezes mais microssegundos: calcular a haversine em cada vértice custa mais do que expandir os poucos vértices economizados em um grafo de 20 vértices.
- **A heurística mais informada ganha.** Usar a $v_{\max}$ da própria rede expande menos que os 80 km/h fixos, porque estima o tempo restante com mais precisão sem deixar de ser admissível.
- **Na malha de 3 600 vértices o A\* mostra a vantagem real:** na mediana expande 801 vértices contra 1 803 do Dijkstra (55% a menos) e também roda mais rápido (veja a tabela acima; os milissegundos variam um pouco a cada execução, as expansões não). O Dijkstra cresce em círculo a partir da origem, enquanto o A\* avança na direção do alvo.
- **Conclusão para o SafeStair:** com a rede atual, Dijkstra a partir da base (uma única execução calcula todas as rotas) é suficiente e mais simples. O A\* passa a compensar quando a rede incluir todas as estações e acessos viários das concessões da Motiva e as consultas forem ponto a ponto, como no replanejamento de um técnico já em campo.
""")

