# ============================================================================
md(r"""
---
## Parte 4 — Plano de manutenção: `planejar_turno(base, horas)`

**Regras:**

1. Entram no plano as escadas de classe **Crítica e Alta**; as demais seguem em monitoramento.
2. **Prioridade por classe:** nenhuma escada de uma classe é atendida antes das que cabem no turno da classe acima.
3. **Dentro da mesma classe:** primeiro as outras escadas da estação onde a equipe já está (deslocamento zero); depois, a de maior criticidade, onde quer que esteja. O caminho até ela é o de menor tempo (Dijkstra).
4. Uma escada só entra se o deslocamento + o serviço + **o retorno à base** ainda couberem no turno. Se não couber, fica como pendente e o algoritmo tenta a próxima.
5. **Tempo de serviço estimado por classe:** Crítica 90 min e Alta 60 min. Sem histórico de reparos nesta versão, não há como estimar por escada, como faz o notebook principal.

Os tempos entre estações vêm de uma tabela de menores tempos (Dijkstra a partir de cada vértice), e as rotas são reconstruídas com `reconstruir_rota`.
""")

code(r"""
ORDEM_CLASSES = ["Crítica", "Alta"]

# Tempo de serviço estimado por classe (minutos)
TEMPO_SERVICO = {"Crítica": 90, "Alta": 60}
ranking["servico_min"] = ranking.classe.map(TEMPO_SERVICO)

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

- **Coerência com o ranking:** no turno de 8 h a equipe começa pela TVS-ER06, 1ª do ranking (9 min da base), e segue para a HIG-ER22, a 2ª.
- **Agrupamento por estação:** em Higienópolis a equipe atende três escadas críticas em sequência (HIG-ER22, ER08 e ER07) e ainda uma de classe Alta (HIG-ER03), sem deslocamento entre elas.
- **Regra de classe respeitada:** a HIG-ER03 (Alta) só entra porque nenhuma das críticas restantes cabe no tempo que sobrou com o retorno à base. Ela cabe porque o serviço de classe Alta é mais curto (60 min) e a equipe já está na estação.
- **Deslocamento × serviço:** 54 min de deslocamento contra 420 min de serviço. O gargalo continua sendo o número de escadas críticas: 17 críticas a 90 min cada exigiriam mais de 3 turnos de uma equipe.
- **Diferença para o notebook principal:** aqui o tempo de serviço é fixo por classe, porque não há histórico de reparos. Na operação real, as duas fontes se complementam: os sensores dizem **qual** escada está degradando, e o histórico do SAP diz **quanto tempo** o reparo costuma levar.
""")

md(r"""
## Conclusões

| Experimento | Resultado principal |
|---|---|
| Dataset | 4 728 leituras diárias simuladas (24 dias × 197 escadas reais), com os limites do `ManutencaoService`. |
| Degradação (3 versões) | Resultados idênticos; recursiva exponencial (24 milhões de chamadas), memoizada e tabulação lineares. Com telemetria horária, só a tabulação é viável. |
| Ranking | 17 críticas, todas também com "intervenção recomendada" no Java; 9 escadas que o Java considera normais aparecem como Alta, principalmente por queda de velocidade. |
| BFS × Dijkstra e A\* | Mesmo grafo e mesmos resultados do notebook principal (as Partes 2 e 3 não dependem da fonte de dados). |
| `planejar_turno` | 4 críticas e 1 escada Alta em 8 h, agrupadas em Higienópolis, com retorno à base dentro do turno. |

**Os dois notebooks juntos:** o principal mostra o que o histórico real do SAP permite fazer hoje, e este mostra que os mesmos algoritmos recebem a telemetria proposta pelo SafeStair sem mudança, apenas trocando a origem da penalidade.
""")
