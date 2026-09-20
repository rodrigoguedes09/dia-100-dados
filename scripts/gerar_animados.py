"""Gera um WebP animado por dia, a partir dos trechos em mp4.

Para que serve: o link da bio do TikTok abre num navegador embutido que, no iPhone, não
deixa vídeo tocar dentro da página — o iOS ignora o `playsinline` e joga tudo para tela
cheia. Nesse caso o site troca os <video> por estas animações, que são imagem e não passam
pelo reprodutor do sistema. Em navegador normal nada muda: continua usando o mp4.

Uso:
    python scripts/gerar_animados.py                 # todos os que faltam
    python scripts/gerar_animados.py --refazer       # refaz todos
    python scripts/gerar_animados.py --so dia-12     # só um
"""

import argparse
import json
import pathlib
import subprocess
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
VIDEOS = BASE / "public" / "videos"
JSON_VIDEOS = BASE / "public" / "data" / "videos.json"
FFMPEG = pathlib.Path(
    (BASE.parent / "tiktok-comments-scraper" / ".ffmpeg-path.txt").read_text().strip()
)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--largura", type=int, default=360)
    p.add_argument("--fps", type=int, default=12)
    p.add_argument("--qualidade", type=int, default=45, help="0-100, maior = melhor e mais pesado")
    p.add_argument("--refazer", action="store_true")
    p.add_argument("--so", default="", help="nome do arquivo sem extensão, ex: dia-12")
    return p.parse_args()


def main():
    args = parse_args()
    fontes = sorted(VIDEOS.glob("*.mp4"))
    if args.so:
        fontes = [f for f in fontes if f.stem == args.so]
    if not fontes:
        raise SystemExit("nenhum mp4 encontrado")

    feitos, pulados, falhas = 0, 0, []
    for i, mp4 in enumerate(fontes, 1):
        saida = mp4.with_suffix(".webp")
        if saida.exists() and not args.refazer:
            pulados += 1
            continue
        r = subprocess.run(
            [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp4),
             "-vf", f"fps={args.fps},scale={args.largura}:-2:flags=lanczos",
             "-c:v", "libwebp_anim", "-lossless", "0", "-q:v", str(args.qualidade),
             "-compression_level", "5", "-loop", "0", "-an", str(saida)],
            capture_output=True, text=True,
        )
        if r.returncode != 0 or not saida.exists():
            falhas.append((mp4.name, r.stderr.strip()[:160]))
        else:
            feitos += 1
        if i % 20 == 0:
            print(f"  {i}/{len(fontes)}", flush=True)

    # videos.json ganha o caminho da animação; o site só usa quando precisa.
    dados = json.loads(JSON_VIDEOS.read_text(encoding="utf-8"))
    for v in dados:
        animado = VIDEOS / f"dia-{v['dia']:02d}.webp"
        if animado.exists():
            v["animado"] = f"/videos/{animado.name}"
    JSON_VIDEOS.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")

    total = sum(f.stat().st_size for f in VIDEOS.glob("*.webp"))
    print(f"\ngerados agora: {feitos} | já existiam: {pulados} | falhas: {len(falhas)}")
    print(f"{len(list(VIDEOS.glob('*.webp')))} animações, {total / 2**20:.1f} MB")
    print(f"videos.json atualizado: {sum(1 for v in dados if v.get('animado'))} com animação")
    if falhas:
        print("falhas:", falhas[:5])
        sys.exit(1)


if __name__ == "__main__":
    main()
