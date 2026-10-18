"""
Gera data/rede_estacoes.json: estações das linhas operadas pela Motiva
(4-Amarela, 5-Lilás e 9-Esmeralda), a base de manutenção e os trechos com
tempo de deslocamento em minutos.

Os ids das estações da Linha 4 são os mesmos códigos do campo
"Local de Instalação" do SAP (PTA = Paulista, FRE = Oscar Freire,
FAL = Faria Lima, MBI = São Paulo-Morumbi, TVS = Terminal Vila Sônia),
o que liga cada escada do dataset a um vértice do grafo.

Coordenadas e tempos são aproximados. Trechos que saem de estações de
integração incluem a baldeação; trechos "agregados" representam estações
intermediárias não modeladas.

Autores: Squad 6 · Versão 2.0 — outubro/2026
"""
import json
from pathlib import Path

DADOS = Path(__file__).resolve().parent.parent / "data"

ESTACOES = [
    # id,  nome,                        linhas,                        lat,      lon
    ("LUZ", "Luz",                        ["4-Amarela"],                 -23.5365, -46.6339),
    ("REP", "República",                  ["4-Amarela"],                 -23.5443, -46.6425),
    ("HIG", "Higienópolis-Mackenzie",     ["4-Amarela"],                 -23.5478, -46.6516),
    ("PTA", "Paulista",                   ["4-Amarela"],                 -23.5553, -46.6619),
    ("FRE", "Oscar Freire",               ["4-Amarela"],                 -23.5615, -46.6721),
    ("FRA", "Fradique Coutinho",          ["4-Amarela"],                 -23.5660, -46.6840),
    ("FAL", "Faria Lima",                 ["4-Amarela"],                 -23.5673, -46.6935),
    ("PIN", "Pinheiros",                  ["4-Amarela", "9-Esmeralda"],  -23.5672, -46.7020),
    ("BUT", "Butantã",                    ["4-Amarela"],                 -23.5717, -46.7081),
    ("MBI", "São Paulo-Morumbi",          ["4-Amarela"],                 -23.5869, -46.7229),
    ("VSO", "Vila Sônia",                 ["4-Amarela"],                 -23.5937, -46.7363),
    ("TVS", "Terminal Vila Sônia",        ["4-Amarela"],                 -23.5951, -46.7378),
    ("CJD", "Cidade Jardim",              ["9-Esmeralda"],               -23.5855, -46.6956),
    ("VOL", "Vila Olímpia",               ["9-Esmeralda"],               -23.5945, -46.6920),
    ("BER", "Berrini",                    ["9-Esmeralda"],               -23.6082, -46.6957),
    ("SAM", "Santo Amaro",                ["9-Esmeralda", "5-Lilás"],    -23.6550, -46.7185),
    ("CBE", "Campo Belo",                 ["5-Lilás"],                   -23.6208, -46.6745),
    ("MOE", "Moema",                      ["5-Lilás"],                   -23.6008, -46.6637),
    ("SCZ", "Santa Cruz",                 ["5-Lilás"],                   -23.5990, -46.6366),
]
BASE = ("BASE", "Base de Manutenção (Pátio Vila Sônia)", ["base"], -23.5985, -46.7445)

TRECHOS = [
    # origem, destino, minutos, modo, linha, observação
    ("LUZ", "REP", 2, "metro", "4-Amarela", ""),
    ("REP", "HIG", 2, "metro", "4-Amarela", ""),
    ("HIG", "PTA", 2, "metro", "4-Amarela", ""),
    ("PTA", "FRE", 2, "metro", "4-Amarela", ""),
    ("FRE", "FRA", 2, "metro", "4-Amarela", ""),
    ("FRA", "FAL", 2, "metro", "4-Amarela", ""),
    ("FAL", "PIN", 2, "metro", "4-Amarela", ""),
    ("PIN", "BUT", 2, "metro", "4-Amarela", ""),
    ("BUT", "MBI", 3, "metro", "4-Amarela", ""),
    ("MBI", "VSO", 3, "metro", "4-Amarela", ""),
    ("VSO", "TVS", 3, "a pé", "acesso", "passarela entre a estação e o terminal"),
    ("PIN", "CJD", 9, "trem", "9-Esmeralda", "agregado; inclui baldeação de 4 min em Pinheiros"),
    ("CJD", "VOL", 3, "trem", "9-Esmeralda", ""),
    ("VOL", "BER", 3, "trem", "9-Esmeralda", ""),
    ("BER", "SAM", 9, "trem", "9-Esmeralda", "agregado (Morumbi, Granja Julieta, João Dias)"),
    ("SAM", "CBE", 15, "metro", "5-Lilás", "agregado; inclui baldeação de 3 min em Santo Amaro"),
    ("CBE", "MOE", 4, "metro", "5-Lilás", "agregado (Eucaliptos)"),
    ("MOE", "SCZ", 6, "metro", "5-Lilás", "agregado (AACD-Servidor, Hospital São Paulo)"),
    ("BASE", "VSO", 6, "rodovia", "rodovia", "van da equipe até a estação vizinha ao pátio"),
    ("BASE", "BUT", 14, "rodovia", "rodovia", "van pela Av. Francisco Morato"),
    ("BASE", "PTA", 35, "rodovia", "rodovia", "van pela Av. Rebouças, trânsito de pico"),
    ("BASE", "SAM", 25, "rodovia", "rodovia", "van pela Marginal Pinheiros"),
]

rede = {
    "descricao": "Rede de estações SafeStair — vértices = estações + base; arestas = trechos em minutos",
    "unidade_peso": "minutos",
    "base": BASE[0],
    "vertices": [{"id": i, "nome": n, "linhas": l, "lat": la, "lon": lo} for (i, n, l, la, lo) in ESTACOES + [BASE]],
    "arestas": [{"origem": a, "destino": b, "minutos": m, "modo": modo, "linha": linha, "obs": obs}
                for (a, b, m, modo, linha, obs) in TRECHOS],
}
(DADOS / "rede_estacoes.json").write_text(json.dumps(rede, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"rede_estacoes.json: {len(rede['vertices'])} vértices, {len(rede['arestas'])} arestas")
