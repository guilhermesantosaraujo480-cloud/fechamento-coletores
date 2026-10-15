"""Acompanhamento dia a dia: compara a 'fotografia' de cada relatório para ver quem avançou.

Atenção ao significado: uma OS que SAI da lista de um dia para o outro pode ter sido coletada, cancelada ou encerrada
na plataforma. Não é prova de coleta; é o melhor indicador que a planilha permite (e costuma ser bem próximo)."""
import pandas as pd

from .processamento import SEM_COLETOR


def montar_snapshot(can, atrib, empresa, data):
    """Linhas leves (sem dados pessoais do cliente) para guardar no banco."""
    linhas = []
    for idx, r in can.iterrows():
        os_id = str(r["id"]).strip()
        if not os_id:
            continue
        linhas.append({
            "chave": f"{empresa}|{data}|{os_id}", "empresa": empresa, "data": str(data), "os_id": os_id,
            "coletor": str(atrib.get(idx, SEM_COLETOR)), "bairro": str(r.get("bairro_ef", ""))[:80],
            "cidade": str(r.get("cidade", ""))[:60], "motivo": str(r.get("motivo", ""))[:80],
            "urgente": bool(r.get("urgente", False)),
        })
    return linhas


def comparar(anterior, atual):
    """anterior/atual: listas de snapshots (dicts). Devolve dict com tabelas prontas para a tela."""
    a = pd.DataFrame(anterior, columns=["os_id", "coletor", "bairro", "cidade", "motivo", "urgente"])
    b = pd.DataFrame(atual, columns=["os_id", "coletor", "bairro", "cidade", "motivo", "urgente"])
    ids_a, ids_b = set(a["os_id"]), set(b["os_id"])
    saiu = a[~a["os_id"].isin(ids_b)]
    entrou = b[~b["os_id"].isin(ids_a)]
    ficou = a.merge(b, on="os_id", suffixes=("_ant", "_hoje"))
    trocou = ficou[ficou["coletor_ant"] != ficou["coletor_hoje"]]
    parou = ficou[ficou["coletor_ant"] == ficou["coletor_hoje"]]

    coletores = sorted(set(a["coletor"]) | set(b["coletor"]))
    linhas = []
    for c in coletores:
        ant = int((a["coletor"] == c).sum())
        hoje = int((b["coletor"] == c).sum())
        s = int((saiu["coletor"] == c).sum())
        linhas.append({
            "Coletor": c, "Antes": ant, "Hoje": hoje, "Saíram da lista": s,
            "% que saiu": round(100 * s / ant, 1) if ant else 0.0,
            "Entraram": int((entrou["coletor"] == c).sum()),
            "Recebeu de outro": int((trocou["coletor_hoje"] == c).sum()),
            "Passou para outro": int((trocou["coletor_ant"] == c).sum()),
            "Continuam com ele": int((parou["coletor_hoje"] == c).sum()),
        })
    return {"por_coletor": pd.DataFrame(linhas), "saiu": saiu, "entrou": entrou, "trocou": trocou,
            "total_antes": len(a), "total_hoje": len(b)}


def produtividade(snapshots_por_data):
    """snapshots_por_data: {data: [linhas]} em qualquer ordem. Devolve DataFrame data x coletor com 'saíram da lista'."""
    datas = sorted(snapshots_por_data)
    linhas = []
    for ant, atual in zip(datas, datas[1:]):
        r = comparar(snapshots_por_data[ant], snapshots_por_data[atual])["saiu"]
        cont = r["coletor"].value_counts().to_dict()
        linhas.append({"Data": atual, **cont})
    return pd.DataFrame(linhas).fillna(0).set_index("Data") if linhas else pd.DataFrame()
