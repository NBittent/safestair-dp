# ============================================================================
md(r"""
---
## Parte 4 — Plano de manutenção: `planejar_turno(base, horas)`

**Regras:**

1. Entram no plano as escadas de classe **Crítica e Alta** (39 escadas, os 20% mais degradados); as demais seguem em monitoramento.
2. **Prioridade por classe:** nenhuma escada de uma classe é atendida antes das que cabem no turno da classe acima.
3. **Dentro da mesma classe:** primeiro as outras escadas da estação onde a equipe já está (deslocamento zero); depois, a de maior criticidade, onde quer que esteja. O caminho até ela é o de menor tempo (Dijkstra).
4. Uma escada só entra se o deslocamento + o serviço + **o retorno à base** ainda couberem no turno. Se não couber, fica como pendente e o algoritmo tenta a próxima.
5. **Tempo de serviço vindo dos dados:** para cada escada, o percentil 75 da duração das paradas dela nos últimos 12 meses, limitado entre 30 e 240 minutos. Escadas que costumam ficar paradas mais tempo recebem mais tempo no turno.

Os tempos entre estações vêm de uma tabela de menores tempos (Dijkstra a partir de cada vértice), e as rotas são reconstruídas com `reconstruir_rota`.
""")

code(r"""
ORDEM_CLASSES = ["Crítica", "Alta"]

# Tempo de serviço de cada escada = percentil 75 das paradas dela nos últimos 12 meses, entre 30 e 240 min
TEMPO_SERVICO = (ult12.groupby("cd_escada").horas_parada.quantile(0.75).mul(60).clip(30, 240).round()
                 .reindex(ranking.cd_escada).fillna(60))
ranking["servico_min"] = ranking.cd_escada.map(TEMPO_SERVICO)

# Menores tempos e predecessores de todos para todos (uma execução de Dijkstra por vértice)
TODOS_DIJ = {v: dijkstra(ADJ, v)[:2] for v in ADJ}


def planejar_turno(base, horas, ranking=None, adj=None, inicio="08:00"):
    \"\"\"Indica quais escadas atender no turno, em que ordem e por qual caminho.

    Args:
        base (str): id do vértice de onde a equipe sai e para onde volta (ex.: 'BASE').
        horas (float): duração do turno em horas.
        ranking (pd.DataFrame, opcional): ranking de criticidade (padrão: o calculado na Parte 1).
        adj (dict, opcional): lista de adjacência (padrão: a rede de estações).
        inicio (str): horário de início do turno, 'HH:MM'.

    Returns:
        tuple[pd.DataFrame, dict]: (plano de visitas em ordem, resumo do turno).
    \"\"\"
    ranking = RANKING_PADRAO if ranking is None else ranking
    adj = ADJ if adj is None else adj
    tempos = TODOS_DIJ if adj is ADJ else {v: dijkstra(adj, v)[:2] for v in adj}
    orcamento = horas * 60
    h0, m0 = map(int, inicio.split(":"))
    relogio = lambda minutos: f"{(h0 * 60 + m0 + int(round(minutos))) // 60 % 24:02d}:{(m0 + int(round(minutos))) % 60:02d}"

    posicao, t, plano, pendentes = base, 0.0, [], []
    for classe in ORDEM_CLASSES:
        restantes = ranking[ranking.classe == classe].copy()
        while not restantes.empty:
            dist_atual = tempos[posicao][0]
            restantes["desloc"] = restantes.id_estacao.map(dist_atual)
            restantes["volta"] = restantes.id_estacao.map(lambda e: tempos[e][0][base])
            restantes["cabe"] = t + restantes.desloc + restantes.servico_min + restantes.volta <= orcamento
            viaveis = restantes[restantes.cabe]
            if viaveis.empty:
                pendentes += restantes.cd_escada.tolist()
                break
            prox = (viaveis.assign(outra_estacao=viaveis.desloc > 0)
                    .sort_values(["outra_estacao", "criticidade"], ascending=[True, False]).iloc[0])
            rota = reconstruir_rota(tempos[posicao][1], posicao, prox.id_estacao)
            chegada = t + prox.desloc
            plano.append({"ordem": len(plano) + 1, "escada": prox.cd_escada, "estação": prox.estacao,
                          "classe": classe, "criticidade": round(prox.criticidade, 1),
                          "componente": prox.componente_principal,
                          "rota": " → ".join(rota) if len(rota) > 1 else "(mesma estação)",
                          "desloc. (min)": prox.desloc, "chegada": relogio(chegada),
                          "serviço (min)": prox.servico_min, "término": relogio(chegada + prox.servico_min)})
            t = chegada + prox.servico_min
            posicao = prox.id_estacao
            restantes = restantes[restantes.cd_escada != prox.cd_escada]

    volta = tempos[posicao][0][base]
    rota_volta = reconstruir_rota(tempos[posicao][1], posicao, base)
    total = t + volta
    resumo = {"turno (min)": orcamento, "escadas atendidas": len(plano),
              "deslocamento (min)": sum(p["desloc. (min)"] for p in plano) + volta,
              "serviço (min)": sum(p["serviço (min)"] for p in plano),
              "retorno": " → ".join(rota_volta) + f" ({volta:.0f} min, chegada {relogio(total)})",
              "ocupação do turno": f"{100 * total / orcamento:.0f}%",
              "pendentes": pendentes}
    return pd.DataFrame(plano).set_index("ordem") if plano else pd.DataFrame(), resumo


RANKING_PADRAO = ranking.copy()
print("Escadas candidatas por classe:", ranking[ranking.classe.isin(ORDEM_CLASSES)].classe.value_counts().to_dict())
print("Tempo de serviço das candidatas (min):", ranking[ranking.classe.isin(ORDEM_CLASSES)].servico_min.describe().round(0).to_dict())
""")

code(r"""
plano8, resumo8 = planejar_turno("BASE", 8)
print("TURNO DE 8 HORAS (início 08:00)")
display(plano8)
for k, v in resumo8.items():
    print(f"  {k}: {v}")
""")

code(r"""
comparativo = []
for horas in [4, 6, 8, 10, 12]:
    p, r = planejar_turno("BASE", horas)
    comparativo.append({"turno (h)": horas, "atendidas": r["escadas atendidas"],
                        "críticas atendidas": int((p.classe == "Crítica").sum()) if len(p) else 0,
                        "deslocamento (min)": r["deslocamento (min)"], "serviço (min)": r["serviço (min)"],
                        "ocupação": r["ocupação do turno"], "pendentes": len(r["pendentes"])})
display(pd.DataFrame(comparativo).set_index("turno (h)"))

plano4, resumo4 = planejar_turno("BASE", 4)
print("\nTURNO DE 4 HORAS")
display(plano4[["escada", "estação", "classe", "rota", "desloc. (min)", "chegada", "término"]])
print("Retorno:", resumo4["retorno"], "| pendentes:", resumo4["pendentes"])
""")

md(r"""
**Interpretação.**

- **Coerência com o ranking:** no turno de 8 h a equipe atende 4 das 9 escadas críticas, começando pela PTA-ER15, 1ª do ranking. Nenhuma escada de classe Alta entra antes das críticas.
- **Agrupamento por estação:** na Paulista a equipe atende a PTA-ER15 e, em seguida, a PTA-ER17, sem deslocamento entre elas. Depois vai de metrô para Pinheiros (8 min), onde faz a PIN-ER24 e a PIN-ER28. No total são 44 minutos de deslocamento contra 425 de serviço.
- **Rotas do Dijkstra:** a ida à Paulista é de metrô desde Vila Sônia (22 min), e não pela van direta (35 min). A volta sai de Pinheiros pela Linha 4 até Vila Sônia e de lá de van até a base.
- **Tempo de serviço vindo dos dados:** a PTA-ER15 recebe 230 minutos porque as paradas dela costumam ser longas, enquanto a PTA-ER17 recebe 51. Com tempos fixos por classe, o plano ignoraria essa diferença.
- **Prioridade × quantidade:** o turno de 6 h atende menos escadas (2) que o de 4 h (3). Em 6 h passa a caber a PTA-ER15, a mais crítica, que sozinha ocupa quase 4 horas; em 4 h ela não cabe e a equipe faz três serviços menores. O plano prioriza a criticidade, não o número de escadas.
- **Gargalo:** com 9 escadas críticas e tempo de serviço mediano de 75 minutos entre as 39 candidatas, uma equipe por turno não dá conta nem das críticas. O dado indica a necessidade de duas equipes, ou de uma base avançada perto de Pinheiros e da Paulista.
- **Limites:** o algoritmo é guloso e não garante o máximo de escadas por turno; o problema exato é uma variação do *orienteering problem*, NP-difícil. O tempo de serviço histórico inclui a espera pelo técnico, e os tempos de trecho não variam com o horário.
""")

md(r"""
## Conclusões

| Experimento | Resultado principal |
|---|---|
| Dataset | 27 200 falhas corretivas reais de 197 escadas da Linha 4 (jan/2023 a ago/2026), com recorte justificado pela mudança no registro em 2023. |
| Degradação (3 versões) | Resultados idênticos. A recursiva pura é exponencial: 1,8 bilhão de chamadas por escada na série de 44 meses. Memoizada e tabulação são lineares, e a tabulação foi adotada por não depender da pilha. |
| Ranking | 9 críticas, concentradas em Pinheiros, Paulista e Luz. A degradação acumulada destaca paradas longas e tendência de piora que uma contagem simples esconde. |
| BFS × Dijkstra | Em 13 de 19 estações o BFS escolhe uma rota mais lenta (até 21 min a mais); o planejamento usa Dijkstra. |
| A\* × Dijkstra | Mesmos tempos ótimos. Faz 14% menos expansões na rede de 20 vértices, mas sem ganho de tempo; faz 55% menos expansões na malha de 3 600 vértices, onde também roda mais rápido. |
| `planejar_turno` | Atende as críticas em ordem de criticidade, agrupa por estação, usa o tempo de reparo histórico de cada escada e respeita o turno e o retorno à base. |
""")

