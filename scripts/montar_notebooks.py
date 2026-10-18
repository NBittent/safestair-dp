"""
Monta os dois notebooks a partir dos blocos em scripts/fonte/ (uso interno do squad):

- notebook.ipynb           = p1_falhas_sap + p23_grafo_rotas + p4_falhas_sap   (dados reais do SAP)
- notebook_sensores.ipynb  = p1_sensores   + p23_grafo_rotas + p4_sensores     (sensores simulados)

As Partes 2 e 3 (grafo, BFS, Dijkstra, A*) são o mesmo bloco nos dois notebooks.
"""
from pathlib import Path

import nbformat as nbf

FONTE = Path(__file__).resolve().parent / "fonte"
RAIZ = Path(__file__).resolve().parent.parent

NOTEBOOKS = {
    "notebook.ipynb": ["p1_falhas_sap.py", "p23_grafo_rotas.py", "p4_falhas_sap.py"],
    "notebook_sensores.ipynb": ["p1_sensores.py", "p23_grafo_rotas.py", "p4_sensores.py"],
}


def montar(blocos):
    celulas = []

    def md(texto):
        celulas.append(nbf.v4.new_markdown_cell(texto.strip("\n")))

    def code(texto):
        texto = texto.replace('\\"\\"\\"', '"""')
        celulas.append(nbf.v4.new_code_cell(texto.strip("\n")))

    for bloco in blocos:
        exec((FONTE / bloco).read_text(encoding="utf-8"), {"md": md, "code": code})
    nb = nbf.v4.new_notebook()
    nb["cells"] = celulas
    nb["metadata"] = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                      "language_info": {"name": "python"}}
    return nb


if __name__ == "__main__":
    for nome, blocos in NOTEBOOKS.items():
        (RAIZ / nome).write_text(nbf.writes(montar(blocos)), encoding="utf-8")
        print(nome, "gerado")
