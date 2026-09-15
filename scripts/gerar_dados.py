"""Gera os dados publicados em public/data a partir da coleta do tiktok-comments-scraper.

O que sai:
- comentarios/shard-NNN.json: comentarios em ordem cronologica, em blocos de 100, com avatar
  e figurinha embutidos como WebP pequeno (data URI). Assim cada bloco e uma unica requisicao
  e o site nao depende das URLs do TikTok, que expiram em ~1 dia.
- busca.json: [id, usuario, nome normalizado, shard, posicao no shard]
- meta.json: totais, para o site saber quantos blocos existem
- videos.json: lista montada a partir do que existir em public/videos (dia-NN.mp4 / dia-NN.jpg)

dias.json nao e gerado aqui: e editado a mao em public/data/dias.json.

Por padrao ficam de fora os comentarios que so aparecem no TikTok Studio (source == "studio"):
o TikTok os esconde do publico por algum motivo que nao sabemos, e o site e publico.

Uso:
    python scripts/gerar_dados.py
    python scripts/gerar_dados.py --incluir-studio
"""

import argparse
import base64
import io
import json
import os
import re
import sys
import unicodedata

from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SCRAPER = os.path.normpath(os.path.join(RAIZ, "..", "tiktok-comments-scraper"))
MARATONA_KM = 42.195


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--scraper", default=SCRAPER, help="pasta do tiktok-comments-scraper")
    p.add_argument("--publico", default=os.path.join(RAIZ, "public"))
    p.add_argument("--tamanho-shard", type=int, default=100)
    p.add_argument("--avatar-px", type=int, default=64)
    p.add_argument("--figurinha-px", type=int, default=240)
    p.add_argument("--incluir-studio", action="store_true")
    return p.parse_args()


def normalizar(s):
    """Espelha normalizar() de src/lib/dia100.ts no site: a busca compara os dois lados."""
    s = unicodedata.normalize("NFKC", s)
    s = unicodedata.normalize("NFD", s)
    s = re.sub("[̀-ͯ]", "", s)
    s = s.lower()
    s = re.sub(r"^@", "", s)
    return s.strip()


def data_uri(caminho, max_px, qualidade):
    try:
        im = Image.open(caminho)
        im.load()
    except Exception:
        return None
    im = im.convert("RGBA") if im.mode in ("P", "LA", "RGBA") else im.convert("RGB")
    im.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=qualidade, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def gravar_json(caminho, dados):
    with io.open(caminho, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))


def main():
    a = parse_args()
    jsonl = os.path.join(a.scraper, "output", "data", "comments.jsonl")
    mapa_path = os.path.join(a.scraper, "output", "assets", "map.json")
    dir_avatares = os.path.join(a.scraper, "output", "assets", "avatars")
    dir_figurinhas = os.path.join(a.scraper, "output", "assets", "stickers")
    for p in (jsonl, mapa_path):
        if not os.path.exists(p):
            sys.exit(f"Nao encontrei {p}")

    mapa = json.load(io.open(mapa_path, encoding="utf-8"))
    avatares = mapa.get("avatars", {})
    figurinhas_map = mapa.get("stickers", {})

    comentarios, vistos, fora_studio = [], set(), 0
    for linha in io.open(jsonl, encoding="utf-8"):
        linha = linha.strip()
        if not linha:
            continue
        try:
            c = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if c.get("cid") in vistos:
            continue
        vistos.add(c.get("cid"))
        if c.get("source") == "studio" and not a.incluir_studio:
            fora_studio += 1
            continue
        comentarios.append(c)

    # Ordem cronologica: e ela que define o "km" de cada comentario na maratona.
    comentarios.sort(key=lambda c: (c.get("create_time") or 0, c.get("cid")))
    total = len(comentarios)

    dir_dados = os.path.join(a.publico, "data")
    dir_shards = os.path.join(dir_dados, "comentarios")
    os.makedirs(dir_shards, exist_ok=True)
    for f in os.listdir(dir_shards):  # a quantidade de blocos pode diminuir entre rodadas
        if f.startswith("shard-") and f.endswith(".json"):
            os.remove(os.path.join(dir_shards, f))

    cache_avatar = {}
    busca, bloco = [], []
    n_shard = sem_avatar = com_figurinha = 0
    maior_shard = 0

    def fechar_bloco():
        nonlocal n_shard, bloco, maior_shard
        caminho = os.path.join(dir_shards, f"shard-{n_shard:03d}.json")
        gravar_json(caminho, bloco)
        maior_shard = max(maior_shard, os.path.getsize(caminho))
        n_shard += 1
        bloco = []

    for i, c in enumerate(comentarios):
        u = c.get("user") or {}

        avatar = None
        arq = avatares.get(u.get("avatar_url") or "")
        if arq:
            if arq not in cache_avatar:
                cache_avatar[arq] = data_uri(os.path.join(dir_avatares, arq), a.avatar_px, 70)
            avatar = cache_avatar[arq]
        if not avatar:
            sem_avatar += 1

        figurinha = None
        if c.get("sticker_url"):
            arq_fig = figurinhas_map.get(c["sticker_url"])
            if arq_fig:
                figurinha = data_uri(os.path.join(dir_figurinhas, arq_fig), a.figurinha_px, 72)
        if figurinha:
            com_figurinha += 1

        texto = c.get("text") or ""
        if not texto.strip() and not figurinha:
            texto = "[figurinha]"

        item = {
            "id": str(c.get("cid")),
            "usuario": u.get("unique_id") or "",
            "nome": u.get("nickname") or u.get("unique_id") or "",
            "texto": texto,
            "curtidas": int(c.get("digg_count") or 0),
            "respostas": int(c.get("reply_count") or 0),
            "data": int(c.get("create_time") or 0),
            "avatar": avatar,
            "figurinha": figurinha,
            "km": round((i + 1) / total * MARATONA_KM, 2),
        }
        busca.append([item["id"], item["usuario"], normalizar(item["nome"]), n_shard, len(bloco)])
        bloco.append(item)
        if len(bloco) == a.tamanho_shard:
            fechar_bloco()
    if bloco:
        fechar_bloco()

    gravar_json(os.path.join(dir_dados, "busca.json"), busca)
    gravar_json(
        os.path.join(dir_dados, "meta.json"),
        {"totalComentarios": total, "totalShards": n_shard, "tamanhoShard": a.tamanho_shard},
    )

    # videos.json reflete o que estiver de fato em public/videos.
    dir_videos = os.path.join(a.publico, "videos")
    videos = []
    if os.path.isdir(dir_videos):
        for f in sorted(os.listdir(dir_videos)):
            m = re.fullmatch(r"dia-(\d+)\.mp4", f)
            if not m:
                continue
            dia = int(m.group(1))
            poster = f"dia-{m.group(1)}.jpg"
            videos.append({
                "dia": dia,
                "src": f"/videos/{f}",
                "poster": f"/videos/{poster}" if os.path.exists(os.path.join(dir_videos, poster)) else "",
            })
    gravar_json(os.path.join(dir_dados, "videos.json"), videos)

    tamanho_total = sum(
        os.path.getsize(os.path.join(raiz, f)) for raiz, _, fs in os.walk(dir_dados) for f in fs
    )
    print(f"comentarios publicados: {total} (fora, so do Studio: {fora_studio})")
    print(f"blocos: {n_shard} | maior bloco: {maior_shard / 1024:.0f} KB | total em data/: {tamanho_total / 1e6:.1f} MB")
    print(f"sem avatar: {sem_avatar} | com figurinha: {com_figurinha} | videos: {len(videos)}")
    print(f"busca.json: {os.path.getsize(os.path.join(dir_dados, 'busca.json')) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
