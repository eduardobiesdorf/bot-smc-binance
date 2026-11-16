# -*- coding: utf-8 -*-
"""
Desenha o setup de um par e manda a imagem no Telegram.

Serve para conferir visualmente o que o radar detectou, sem precisar
abrir a corretora.

Uso:
    python grafico_setup.py --ativo XLMUSDT
    python grafico_setup.py --ativo XLMUSDT --salvar grafico.png   # nao envia
"""
import argparse
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
from matplotlib.patches import Rectangle

import importlib.util
spec = importlib.util.spec_from_file_location("ba", "bot_alertas.py")
ba = importlib.util.module_from_spec(spec)
sys.modules["ba"] = ba
spec.loader.exec_module(ba)

VERDE, VERM, LARANJA, ROXO, CINZA = "#2e9e5b", "#d64545", "#ea7317", "#7c3aed", "#888888"


def desenhar(sim, h, m, cfg, caminho):
    """Reencontra a ancora e o CHOCH mais recentes e desenha tudo."""
    altas, baixas = ba.pivos(h, cfg['pivo_esq'], cfg['pivo_dir'])
    a = ba.atr(h, cfg['atr_periodo'])
    sh = sl = None
    tend = 'indefinida'
    ultimo = None
    for i in range(len(h) - 1):
        for k, p in altas.get(i, []):
            if sh is None or k > sh[0]:
                sh = (k, p)
        for k, p in baixas.get(i, []):
            if sl is None or k > sl[0]:
                sl = (k, p)
        c = h[i][4]
        lado = None
        if sh is not None and c > sh[1]:
            ev = 'choch' if tend == 'baixa' else 'bos'
            lado, ref = 'compra', sh
            tend, sh = 'alta', None
        elif sl is not None and c < sl[1]:
            ev = 'choch' if tend == 'alta' else 'bos'
            lado, ref = 'venda', sl
            tend, sl = 'baixa', None
        if lado is None or ev != 'choch':
            continue
        compra = lado == 'compra'
        jan = range(max(0, ref[0]), i + 1)
        anc = min(jan, key=lambda k: h[k][3]) if compra else \
              max(jan, key=lambda k: h[k][2])
        ultimo = (i, anc, compra)
    if not ultimo:
        return None
    i, anc, compra_orig = ultimo

    # o grafico e para CONFERIR, nao para filtrar: desliga o rr_min para que
    # um setup reprovado por geometria ruim ainda apareca desenhado.
    cfg_ver = dict(cfg, rr_min=0.0)
    est = ba.analisar(h, m, cfg_ver)
    gat = next((e for e in est if e['fase'] == 'gatilho'), None)

    fig, ax = plt.subplots(figsize=(14, 7.5))
    a0 = max(0, anc - 12)
    b0 = len(h)
    jan = h[a0:b0]
    for k, c in enumerate(jan):
        o, hi, lo, cl = c[1], c[2], c[3], c[4]
        cor = VERDE if cl >= o else VERM
        ax.plot([k, k], [lo, hi], color=cor, lw=1.1, zorder=2)
        ax.add_patch(Rectangle((k - .34, min(o, cl)), .68,
                               max(abs(cl - o), 1e-12),
                               facecolor=cor, edgecolor=cor, zorder=3))
    pv = vv = 0.0
    xs, ys = [], []
    for k in range(anc, b0):
        pv += ba.tipico(h[k]) * h[k][5]
        vv += h[k][5]
        xs.append(k - a0)
        ys.append(pv / max(vv, 1e-12))
    ax.plot(xs, ys, color=LARANJA, lw=2.5, zorder=5, label="VWAP ancorada")
    mk = 'v' if not compra_orig else '^'
    ypt = h[anc][2] if not compra_orig else h[anc][3]
    ax.plot([anc - a0], [ypt], marker=mk, ms=13, color=LARANJA,
            mec='white', mew=1.4, zorder=7)
    ax.annotate("âncora", (anc - a0, ypt), xytext=(anc - a0 - .5, ypt),
                color=LARANJA, fontsize=9.5, fontweight='bold')
    ax.axvline(i - a0, color=ROXO, ls='--', lw=1.7, zorder=1)
    ax.annotate(f"CHOCH de {'ALTA' if compra_orig else 'BAIXA'}",
                (i - a0, max(x[2] for x in jan)),
                xytext=(i - a0 + .4, max(x[2] for x in jan)),
                color=ROXO, fontsize=10, fontweight='bold')

    titulo = f"{sim.replace('USDT','/USDT')} — estrutura {cfg['tf_estrutura']}"
    if gat:
        ent, stp = gat['entrada'], gat['stop']
        alv, rr = gat['alvo_estrut'], gat['rr_estrut']
        ax.axhspan(min(ent, stp), max(ent, stp), color=VERM, alpha=.10, zorder=0)
        ax.axhspan(min(ent, alv), max(ent, alv), color=VERDE, alpha=.08, zorder=0)
        linhas = [(ent, f"entrada {ent:.6g}", ROXO),
                  (stp, f"stop {stp:.6g}   (risco 1R)", VERM),
                  (alv, f"alvo estrutural {alv:.6g}   R:R 1:{rr:.2f}", VERDE)]
        if 'alvo_fixo' in gat:
            linhas.append((gat['alvo_fixo'],
                           f"alvo fixo 1:{cfg['rr_fixo']:.0f}  {gat['alvo_fixo']:.6g}",
                           CINZA))
        for y, t_, c_ in linhas:
            ax.axhline(y, color=c_, lw=1.5,
                       ls='--' if c_ == CINZA else '-', zorder=4)
            ax.text(len(jan) - .5, y, f"  {t_}", color=c_, fontsize=9.5,
                    va='center', fontweight='bold')
        # a distancia entrada->stop e entrada->alvo, lado a lado
        ax.annotate("", (len(jan) + 1.5, ent), (len(jan) + 1.5, stp),
                    arrowprops=dict(arrowstyle='<->', color=VERM, lw=1.3))
        ax.annotate("", (len(jan) + 3.5, ent), (len(jan) + 3.5, alv),
                    arrowprops=dict(arrowstyle='<->', color=VERDE, lw=1.3))
        ax.text(len(jan) + 1.7, (ent + stp) / 2, "1R", color=VERM,
                fontsize=9, fontweight='bold')
        ax.text(len(jan) + 3.7, (ent + alv) / 2, f"{rr:.2f}R", color=VERDE,
                fontsize=9, fontweight='bold')
        lado = "VENDA" if gat['lado'] == 'venda' else "COMPRA"
        titulo += f" — GATILHO DE {lado} — R:R 1:{rr:.2f}"
        if rr < 1.2:
            titulo += "  (GEOMETRIA RUIM)"
    ax.set_title(titulo, fontsize=12.5, fontweight='bold')
    ax.set_xlabel(f"barras de {cfg['tf_estrutura']}")
    ax.grid(alpha=.18, lw=.5)
    ax.set_xlim(-1, len(jan) + 14)
    ax.spines[['top', 'right']].set_visible(False)
    ax.legend(loc='upper left', fontsize=10)
    plt.tight_layout()
    plt.savefig(caminho, dpi=135)
    plt.close()
    return gat


def resposta_limpa(r):
    """So o essencial da resposta do Telegram, sem dado pessoal.

    16/11/2026 -- a resposta do Telegram devolve o nome e o id do chat
    dentro de 'result'. Em repositorio publico o log do Actions e publico,
    entao o corpo inteiro nao pode mais ir para o log.
    """
    try:
        d = r.json()
    except Exception:
        return "resposta ilegivel"
    if d.get('ok'):
        return "ok"
    return f"erro: {str(d.get('description'))[:120]}"


def enviar_foto(caminho, legenda):
    tok = os.getenv("TELEGRAM_TOKEN") or os.getenv("TOKEN_TELEGRAM")
    chat = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID_TELEGRAM")
    if not tok or not chat:
        print("sem credenciais do Telegram")
        return False
    with open(caminho, 'rb') as f:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendPhoto",
                          data={'chat_id': chat, 'caption': legenda,
                                'parse_mode': 'HTML'},
                          files={'photo': f}, timeout=60)
    print(f"HTTP {r.status_code}: {resposta_limpa(r)}")
    return r.ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ativo', required=True)
    ap.add_argument('--tf-estrutura', default='30m')
    ap.add_argument('--tf-gatilho', default='15m')
    ap.add_argument('--salvar', default='', help='so salva o png, nao envia')
    a = ap.parse_args()

    cfg = dict(ba.CFG)
    cfg.update(tf_estrutura=a.tf_estrutura, tf_gatilho=a.tf_gatilho)
    sim = a.ativo.upper()
    h = ba.buscar(sim, a.tf_estrutura, 300)
    m = ba.buscar(sim, a.tf_gatilho, 500)
    caminho = a.salvar or f"/tmp/{sim}.png"
    gat = desenhar(sim, h, m, cfg, caminho)
    print(f"grafico em {caminho}")

    if a.salvar:
        return
    if gat:
        leg = (f"<b>{sim.replace('USDT','/USDT')}</b> — "
               f"{'VENDA' if gat['lado']=='venda' else 'COMPRA'}  |  "
               f"R:R estrutural <b>1:{gat['rr_estrut']:.2f}</b>")
        if gat['rr_estrut'] < ba.CFG['rr_min']:
            leg += (f"\n⚠️ <b>reprovado</b>: arrisca 1R para buscar "
                    f"{gat['rr_estrut']:.2f}R. A taxa ida+volta come ~0,1R, "
                    f"e com 1:1 você precisaria de mais de 50% de acerto só "
                    f"para empatar. O radar não manda mais este formato.")
    else:
        leg = f"<b>{sim.replace('USDT','/USDT')}</b> — estrutura atual (sem gatilho ativo)"
    enviar_foto(caminho, leg)


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        print("=== ERRO ===")
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
