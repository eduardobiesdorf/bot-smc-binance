# -*- coding: utf-8 -*-
"""Desenha o setup da varredura e manda a imagem no Telegram.

E o mesmo desenho que eu uso para analisar: faixa do impulso, zona do
order block, a vela que varreu, a vela de reversao e as linhas de
entrada, stop e alvo.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
from matplotlib.patches import Rectangle

import datetime as _dt
BRT = _dt.timezone(_dt.timedelta(hours=-3))
VERDE, VERM, ROXO, AZUL, LARANJA = "#2e9e5b", "#d64545", "#7c3aed", "#2563eb", "#ea7317"


def _velas(ax, dados, destaques):
    for k, c in enumerate(dados):
        o, hi, lo, cl = c[1], c[2], c[3], c[4]
        cor = VERDE if cl >= o else VERM
        d = k in destaques
        ax.plot([k, k], [lo, hi], color=cor, lw=1.5, zorder=4)
        ax.add_patch(Rectangle((k - .32, min(o, cl)), .64,
                               max(abs(cl - o), 1e-12), facecolor=cor,
                               edgecolor='black' if d else cor,
                               lw=1.8 if d else 1, zorder=5))


def desenhar(sim, h, e, caminho):
    """e = o dict devolvido por seguir(). Funciona para gatilho e cenario."""
    imp = e['imp']
    ini, fim, ob = imp['ini'], imp['fim'], imp['ob']
    base, topo = imp['ob_base'], imp['ob_topo']
    compra = e['lado'] == 'compra'
    kv = e.get('varredura')
    kg = e.get('idx')

    a0 = max(0, ob - 14)
    b0 = len(h)
    jan = h[a0:b0]
    if len(jan) < 10:
        return False

    fig, ax = plt.subplots(figsize=(14, 7.4))
    alto = max(x[2] for x in jan)
    baixo = min(x[3] for x in jan)
    alt = alto - baixo

    # zona do order block, estendida
    ax.add_patch(Rectangle((ob - a0 - .5, base), len(jan) + .5 - (ob - a0 - .5),
                           topo - base, facecolor=AZUL, alpha=.15,
                           edgecolor=AZUL, lw=1.5, zorder=1))
    ax.axvspan(ini - a0 - .5, fim - a0 + .5, color=ROXO, alpha=.12, zorder=0)

    dest = {x - a0 for x in (ob, kv, kg) if x is not None and x >= a0}
    _velas(ax, jan, dest)

    ax.annotate(f"impulso de {'alta' if imp['alta'] else 'baixa'}",
                ((ini + fim) / 2 - a0, alto), color=ROXO, fontsize=10,
                fontweight='bold', ha='center', va='bottom',
                xytext=((ini + fim) / 2 - a0, alto + alt * .02))
    ax.annotate("order block", (ob - a0, base if compra else topo),
                xytext=(ob - a0 - 3, baixo + alt * (.05 if compra else .95)),
                color=AZUL, fontsize=10, fontweight='bold', ha='center',
                arrowprops=dict(arrowstyle='->', color=AZUL, lw=1.3))

    if kv is not None and kv >= a0:
        yv = h[kv][3] if compra else h[kv][2]
        ax.plot([kv - a0], [yv], marker='v' if compra else '^', ms=13,
                color=LARANJA, mec='white', mew=1.4, zorder=10)
        rot_v = ("varredura" if not e.get('vol_varr')
                 else f"varredura · {e['vol_varr']:.1f}x o volume médio")
        ax.annotate(rot_v, (kv - a0, yv),
                    xytext=(kv - a0 - 5,
                            baixo + alt * (.03 if compra else .97)),
                    color=LARANJA, fontsize=10, fontweight='bold',
                    ha='center', va='bottom' if compra else 'top',
                    arrowprops=dict(arrowstyle='->', color=LARANJA, lw=1.3))

    if e['fase'] == 'gatilho':
        for y, t_, c_ in [(e['alvo'], f"alvo {e['alvo']:.6g}", VERDE),
                          (e['entrada'], f"entrada {e['entrada']:.6g}", ROXO),
                          (e['stop'], f"stop {e['stop']:.6g}  "
                                      f"({e['risco_pct']:.2f}%)", VERM)]:
            ax.axhline(y, color=c_, lw=1.7, zorder=3)
            ax.text(len(jan) + .4, y, f" {t_}", color=c_, fontsize=9.5,
                    fontweight='bold', va='center')
        # as setas de R ficam na margem, fora das velas
        xr = len(jan) + 7.2
        ax.annotate("", (xr, e['entrada']), (xr, e['stop']),
                    arrowprops=dict(arrowstyle='<->', color=VERM, lw=1.7))
        ax.text(xr + .3, (e['entrada'] + e['stop']) / 2, "1R",
                color=VERM, fontsize=10, fontweight='bold', va='center')
        ax.annotate("", (xr + 2.2, e['entrada']), (xr + 2.2, e['alvo']),
                    arrowprops=dict(arrowstyle='<->', color=VERDE, lw=1.7))
        ax.text(xr + 2.5, (e['entrada'] + e['alvo']) / 2,
                f"{e['rr']:.1f}R", color=VERDE, fontsize=10,
                fontweight='bold', va='center')
        titulo = (f"{sim.replace('USDT','/USDT')} — {e['lado'].upper()}  ·  "
                  f"R:R 1:{e['rr']:.2f}  ·  risco {e['risco_pct']:.2f}%"
                  + ("" if e.get('nucleo', True) else "   ·  FORA DO NÚCLEO"))
        cor = VERDE if compra else VERM
        lim_dir = len(jan) + 12
    else:
        ax.axhline(e['alvo'], color=VERDE, lw=1.5, ls='--', zorder=3)
        ax.text(len(jan) + .4, e['alvo'], f" alvo {e['alvo']:.6g}",
                color=VERDE, fontsize=9.5, fontweight='bold', va='center')
        ax.axhline(e['preco'], color='#444', lw=1.2, zorder=3)
        ax.text(len(jan) + .4, e['preco'], f" agora {e['preco']:.6g}",
                color='#444', fontsize=9.5, fontweight='bold', va='center')
        titulo = (f"{sim.replace('USDT','/USDT')} — de olho  ·  "
                  f"{e['lado']}  ·  {e['nota']}")
        cor = '#333'
        lim_dir = len(jan) + 10

    ax.set_title(titulo, fontsize=12.5, fontweight='bold', color=cor,
                 loc='left', pad=12)
    ax.set_xlim(-1.5, lim_dir)
    ax.set_ylim(baixo - alt * .07, alto + alt * .12)
    ax.grid(alpha=.14, lw=.6)
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_xlabel("velas de 1 hora")
    plt.tight_layout()
    plt.savefig(caminho, dpi=120)
    plt.close()
    return True


def enviar_foto(caminho, legenda):
    tok = os.getenv("TELEGRAM_TOKEN") or os.getenv("TOKEN_TELEGRAM")
    chat = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID_TELEGRAM")
    if not tok or not chat:
        return False
    # o Telegram corta legenda de foto em 1024 caracteres
    legenda = legenda[:1000]
    try:
        with open(caminho, 'rb') as f:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendPhoto",
                              data={'chat_id': chat, 'caption': legenda,
                                    'parse_mode': 'HTML'},
                              files={'photo': f}, timeout=60)
        print(f"sendPhoto HTTP {r.status_code}: {r.text[:160]}", flush=True)
        return r.ok
    except Exception as ex:
        print(f"sendPhoto erro: {ex}", flush=True)
        return False
