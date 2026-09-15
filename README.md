# dia-100-dados

Dados estáticos do site Dia 100 (comentários, índice de busca, dias e vídeos), publicados pela
Cloudflare Pages. O site no Lovable lê daqui via `VITE_DADOS_URL`.

Tudo o que é publicado fica em `public/`. Não há build: a Cloudflare publica a pasta como está.

- `public/data/` — `meta.json`, `dias.json`, `busca.json`, `comentarios/shard-NNN.json`, `videos.json`
- `public/videos/` — trechos curtos em loop (`dia-NN.mp4`) e capas (`dia-NN.jpg`)
- `public/_headers` — libera o acesso do site (CORS), define cache e bloqueia indexação

Este repositório é privado de propósito: são comentários de pessoas reais, com foto.
