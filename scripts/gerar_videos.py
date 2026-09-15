"""Corta um trecho curto em loop de cada video dos 100 dias para a colagem do site.

Para cada arquivo "diaNN-...mp4" da pasta de origem:
- trecho de alguns segundos, sem audio, reduzido para 640px no lado maior e comprimido
  (fica em poucas centenas de KB: a colagem mostra varios ao mesmo tempo, inclusive no celular);
- capa .jpg do primeiro quadro do trecho, que aparece enquanto o video carrega;
- o formato original e mantido (vertical ou horizontal): cortar um video horizontal para
  vertical perderia a maior parte do edit.

O ponto de inicio e sorteado em qualquer parte de cada video (semente fixa, para refazer igual):
a colagem mistura trechos da abertura, com voce falando, e trechos do edit. Com --inicio, todos
comecam na mesma fracao da duracao.

Gera public/videos/dia-NN.mp4, public/videos/dia-NN.jpg e public/data/videos.json.

Uso:
    python scripts/gerar_videos.py
    python scripts/gerar_videos.py --inicio 0.35 --duracao 5
    python scripts/gerar_videos.py --so dia-99     # refaz so um
"""

import argparse
import io
import json
import os
import random
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
ORIGEM = os.path.normpath(os.path.join(RAIZ, "..", "videos-100-dias"))
FFMPEG_TXT = os.path.normpath(os.path.join(RAIZ, "..", "tiktok-comments-scraper", ".ffmpeg-path.txt"))


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--origem", default=ORIGEM)
    p.add_argument("--publico", default=os.path.join(RAIZ, "public"))
    p.add_argument("--inicio", type=float, default=None,
                   help="onde o trecho comeca, em fracao da duracao (padrao: sorteado por video)")
    p.add_argument("--semente", type=int, default=100)
    p.add_argument("--duracao", type=float, default=4.0, help="segundos do trecho")
    p.add_argument("--lado", type=int, default=640, help="tamanho do lado maior, em px")
    p.add_argument("--crf", type=int, default=30, help="qualidade x264 (maior = menor e pior)")
    p.add_argument("--paralelo", type=int, default=3)
    p.add_argument("--so", default="", help="processar so este arquivo de saida, ex.: dia-99")
    p.add_argument("--ffmpeg", default="")
    return p.parse_args()


def achar_ffmpeg(caminho):
    if caminho:
        return caminho
    if os.path.exists(FFMPEG_TXT):
        return io.open(FFMPEG_TXT, encoding="utf-8").read().strip()
    return "ffmpeg"


def sondar(ffprobe, arquivo):
    """Duracao e dimensoes ja considerando rotacao (video de celular costuma vir girado)."""
    saida = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:stream_side_data=rotation:format=duration",
         "-of", "json", arquivo],
        capture_output=True, text=True, check=True,
    ).stdout
    d = json.loads(saida)
    s = d["streams"][0]
    w, h = int(s["width"]), int(s["height"])
    rot = next((int(x.get("rotation", 0)) for x in s.get("side_data_list", []) if "rotation" in x), 0)
    if abs(rot) in (90, 270):
        w, h = h, w
    return float(d["format"]["duration"]), w, h


def processar(ffmpeg, ffprobe, origem, destino_dir, dia, args):
    duracao, w, h = sondar(ffprobe, origem)
    vertical = h > w
    # lado maior = args.lado; dimensoes pares (exigencia do yuv420p)
    if vertical:
        largura, altura = round(args.lado * w / h / 2) * 2, args.lado
    else:
        largura, altura = args.lado, round(args.lado * h / w / 2) * 2
    trecho = min(args.duracao, max(1.0, duracao - 0.5))
    limite = max(0.0, duracao - trecho - 0.2)
    if args.inicio is None:
        # uma semente por dia: refazer um video isolado (--so) sorteia o mesmo trecho de antes
        inicio = random.Random(args.semente * 1000 + dia).uniform(0.0, limite)
    else:
        inicio = min(max(0.0, duracao * args.inicio), limite)

    nome = f"dia-{dia:02d}"
    mp4 = os.path.join(destino_dir, nome + ".mp4")
    jpg = os.path.join(destino_dir, nome + ".jpg")
    escala = f"scale={largura}:{altura}:flags=lanczos"

    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-ss", f"{inicio:.2f}", "-t", f"{trecho:.2f}", "-i", origem,
         "-vf", f"{escala},fps=30", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf),
         "-profile:v", "high", "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4],
        check=True,
    )
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-ss", f"{inicio:.2f}", "-i", origem,
         "-frames:v", "1", "-vf", escala, "-q:v", "5", jpg],
        check=True,
    )
    return {
        "dia": dia,
        "src": f"/videos/{nome}.mp4",
        "poster": f"/videos/{nome}.jpg",
        "formato": "vertical" if vertical else "horizontal",
        "_kb": os.path.getsize(mp4) / 1024,
    }


def main():
    args = parse_args()
    ffmpeg = achar_ffmpeg(args.ffmpeg)
    ffprobe = ffmpeg[: -len("ffmpeg.exe")] + "ffprobe.exe" if ffmpeg.endswith("ffmpeg.exe") else "ffprobe"

    if not os.path.isdir(args.origem):
        sys.exit(f"Pasta de origem nao encontrada: {args.origem}")

    arquivos = {}
    for f in sorted(os.listdir(args.origem)):
        m = re.match(r"dia\s*(\d+)", f, re.IGNORECASE)
        if m and f.lower().endswith(".mp4"):
            dia = int(m.group(1))
            if dia in arquivos:
                print(f"  aviso: mais de um video para o dia {dia}; usando {arquivos[dia]}")
                continue
            arquivos[dia] = f

    destino_dir = os.path.join(args.publico, "videos")
    os.makedirs(destino_dir, exist_ok=True)

    alvos = {d: f for d, f in arquivos.items() if not args.so or args.so == f"dia-{d:02d}"}
    ponto = "sorteado" if args.inicio is None else f"em {args.inicio:.0%}"
    print(f"{len(arquivos)} videos na origem | processando {len(alvos)} | trecho de {args.duracao}s, inicio {ponto}")

    resultados, falhas = [], []

    def tarefa(item):
        dia, f = item
        try:
            return processar(ffmpeg, ffprobe, os.path.join(args.origem, f), destino_dir, dia, args)
        except Exception as e:  # noqa: BLE001 - um video ruim nao pode derrubar os outros 98
            falhas.append((dia, f, str(e)[:120]))
            return None

    with ThreadPoolExecutor(max_workers=args.paralelo) as ex:
        for i, r in enumerate(ex.map(tarefa, sorted(alvos.items())), 1):
            if r:
                resultados.append(r)
            if i % 10 == 0 or i == len(alvos):
                print(f"  {i}/{len(alvos)}")

    # videos.json lista tudo que existe em public/videos (inclusive o que nao foi refeito agora)
    json_path = os.path.join(args.publico, "data", "videos.json")
    anteriores = {}
    if os.path.exists(json_path):
        for v in json.load(io.open(json_path, encoding="utf-8")):
            anteriores[v["dia"]] = v
    for r in resultados:
        anteriores[r["dia"]] = {k: v for k, v in r.items() if not k.startswith("_")}
    lista = [
        v for _, v in sorted(anteriores.items())
        if os.path.exists(os.path.join(destino_dir, os.path.basename(v["src"])))
    ]
    with io.open(json_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(lista, fh, ensure_ascii=False, indent=1)

    if resultados:
        kbs = [r["_kb"] for r in resultados]
        print(f"\nfeitos: {len(resultados)} | tamanho: media {sum(kbs)/len(kbs):.0f} KB, maior {max(kbs):.0f} KB, total {sum(kbs)/1024:.1f} MB")
    print(f"videos.json: {len(lista)} videos "
          f"({sum(1 for v in lista if v['formato'] == 'vertical')} verticais, "
          f"{sum(1 for v in lista if v['formato'] == 'horizontal')} horizontais)")
    faltando = sorted(set(range(1, 100)) - set(arquivos))
    if faltando:
        print(f"dias sem video na origem: {faltando}")
    for dia, f, erro in falhas:
        print(f"  FALHOU dia {dia} ({f}): {erro}")


if __name__ == "__main__":
    main()
