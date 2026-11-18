# -*- coding: utf-8 -*-
"""Desenha os setups 3 e 5 e manda a imagem no Telegram.

O setup 1 ja tinha gráfico desde o inicio (grafico_varredura.py). Estes
dois mandavam so texto, e o Eduardo pediu os tres iguais: ver o desenho e
decidir, em vez de ler numero e ter de abrir o grafico para conferir.

Reaproveita o desenho de velas, as cores e o envio do modulo do setup 1,
para os tres alertas sairem com a mesma cara.

  desenhar_rev8    setup 3: explosao de 8h, order block, encosto, gatilho
  desenhar_falha5  setup 5: faixa lateral, ida, vela de forca, falha

As duas funcoes aceitam TANTO o dicionario do gatilho quanto o do aviso
(encosto / contexto) -- o que faltar, nao e desenhado.
"""
import datetime as _dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from grafico_varredura import (_velas, enviar_foto, BRT,
                               VERDE, VERM, ROXO, AZUL, LARANJA)

__all__ = ['desenhar_rev8', 'desenhar_falha5', 'enviar_foto']


def _idx_por_ms(h, ms):
    """Posicao da vela que comeca em `ms`, ou None."""
    if not ms:
        return None
    for k in range(len(h) - 1, -1, -1):
        if h[k][0] == ms:
            return k
    return None


def _rotulos(ax, n, itens, alt):
    """Escreve os rotulos da direita SEM deixar um por cima do outro.

    18/11/2026 -- no primeiro desenho o "stop" saiu em cima do "cancela" e
    o "dispara" em cima da "entrada": ilegivel justamente nos numeros que
    importam. Aqui eles sao ordenados por preco e afastados o minimo
    necessario, so no texto -- a linha continua no preco certo.
    """
    itens = sorted((v for v in itens if v[0] is not None), key=lambda x: x[0])
    minimo = alt * .035
    y = []
    for val, _, _, _ in itens:
        if y and val - y[-1] < minimo:
            y.append(y[-1] + minimo)
        else:
            y.append(val)
    # se empurrou demais para cima, desce o bloco inteiro
    if y and itens and y[-1] > itens[-1][0] + minimo:
        desce = y[-1] - itens[-1][0] - minimo
        y = [v - desce for v in y]
    for (val, cor, rot, estilo), yt in zip(itens, y):
        ax.axhline(val, color=cor, lw=1.4, ls=estilo, zorder=3)
        ax.text(n + .6, yt, f" {rot} {val:.6g}", color=cor,
                fontsize=9.5, fontweight='bold', va='center')


def _niveis(ax, g, n, compra, extras=()):
    """Entrada, stop e alvo na direita, no padrao do setup 1."""
    ent = g.get('entrada') or g.get('ref')
    itens = [(ent, '#111', 'entrada', '-'),
             (g.get('stop'), VERM, 'stop', '--'),
             (g.get('alvo'), VERDE, 'alvo', '--')]
    itens += list(extras)
    vals = [v[0] for v in itens if v[0] is not None]
    alt = (max(vals) - min(vals)) if len(vals) > 1 else 1.0
    _rotulos(ax, n, itens, alt)


def _fechar(ax, jan, baixo, alto, alt, titulo, cor, caminho, folga=None):
    # proporcional: 22 velas de folga nao bastam num grafico de 130
    if folga is None:
        folga = max(14, len(jan) * .22)
    ax.set_title(titulo, fontsize=12.5, fontweight='bold', color=cor,
                 loc='left', pad=12)
    ax.set_xlim(-1.5, len(jan) + folga)
    ax.set_ylim(baixo - alt * .07, alto + alt * .12)
    ax.grid(alpha=.14, lw=.6)
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_xlabel("velas de 1 hora")
    plt.tight_layout()
    plt.savefig(caminho, dpi=120)
    plt.close()
    return True


# ------------------------------------------------------- setup 3
def desenhar_rev8(sim, h1, g, caminho):
    """Setup 3: a explosão de 8h, o order block dela e a reversão."""
    k_exp = _idx_por_ms(h1, g.get('exp_ms'))
    k_toq = _idx_por_ms(h1, g.get('toque_ms'))
    k_gat = g.get('idx')
    marcos = [k for k in (k_exp, k_toq, k_gat) if k is not None]
    if not marcos:
        return False

    # A explosao pode ser de SEMANAS antes: o order block dela fica de pe e
    # o preco so volta nele muito depois. Mostrar tudo dava 368 velas
    # espremidas, ilegivel. Entao a janela e limitada e, quando a explosao
    # fica de fora, ela vira uma nota no canto em vez de esticar o grafico.
    TETO = 130
    fim_m = max(marcos)
    perto = [k for k in marcos if fim_m - k <= TETO - 12]
    # minimo de 70 velas de contexto: com 14 nao se ve a aproximacao
    a0 = max(0, min((min(perto) if perto else fim_m) - 12, fim_m - 70))
    jan = h1[a0:]
    if len(jan) < 10:
        return False
    exp_fora = k_exp is not None and k_exp < a0
    compra = g['lado'] == 'compra'

    fig, ax = plt.subplots(figsize=(14, 7.4))
    alto = max(x[2] for x in jan)
    baixo = min(x[3] for x in jan)
    base_ob, topo_ob = g.get('ob_base'), g.get('ob_topo')
    if base_ob is not None and topo_ob is not None:
        alto, baixo = max(alto, topo_ob), min(baixo, base_ob)
    for v in (g.get('stop'), g.get('alvo')):
        if v is not None:
            alto, baixo = max(alto, v), min(baixo, v)
    alt = max(alto - baixo, 1e-12)

    # a zona do order block, esticada até o fim
    if base_ob is not None and topo_ob is not None and k_exp is not None:
        x0 = max(-.5, k_exp - a0 - .5)
        ax.add_patch(Rectangle((x0, base_ob), len(jan) + .5 - x0,
                               topo_ob - base_ob, facecolor=AZUL, alpha=.15,
                               edgecolor=AZUL, lw=1.5, zorder=1))
        ax.annotate("order block da explosão",
                    (max(0, k_exp - a0), topo_ob if compra else base_ob),
                    xytext=(max(0, k_exp - a0) + 2,
                            baixo + alt * (.92 if compra else .08)),
                    color=AZUL, fontsize=10, fontweight='bold',
                    arrowprops=dict(arrowstyle='->', color=AZUL, lw=1.3))

    _velas(ax, jan, {k - a0 for k in marcos if k >= a0})

    if k_exp is not None:
        q = _dt.datetime.fromtimestamp(h1[k_exp][0] / 1000, BRT)
        if exp_fora:
            horas = len(h1) - 1 - k_exp
            ax.text(.2, alto, f"explosão de 8h em {q:%d/%m %H:%M} "
                              f"({horas}h atrás, fora do gráfico)",
                    color=ROXO, fontsize=10, fontweight='bold',
                    ha='left', va='bottom')
        else:
            ax.axvline(k_exp - a0, color=ROXO, lw=1.2, ls=':', zorder=2)
            ax.annotate(f"explosão de 8h · {q:%d/%m %H:%M}",
                        (k_exp - a0, alto), color=ROXO, fontsize=10,
                        fontweight='bold', ha='left', va='bottom',
                        xytext=(k_exp - a0 + .3, alto + alt * .02))
    if k_toq is not None:
        ax.annotate("encostou", (k_toq - a0, h1[k_toq][3 if compra else 2]),
                    xytext=(k_toq - a0, baixo + alt * (.04 if compra else .96)),
                    color=LARANJA, fontsize=10, fontweight='bold',
                    ha='center',
                    arrowprops=dict(arrowstyle='->', color=LARANJA, lw=1.3))

    _niveis(ax, g, len(jan), compra)

    if k_gat is not None:
        titulo = (f"{sim.replace('USDT','/USDT')} — REVERSÃO 8h · "
                  f"{g['lado'].upper()}  ·  R:R 1:{g['rr']:.2f}  ·  "
                  f"risco {g['risco_pct']:.2f}%")
        cor = VERDE if compra else VERM
    else:
        titulo = (f"{sim.replace('USDT','/USDT')} — encosto 8h · de olho  ·  "
                  f"{g['lado']}  ·  R:R 1:{g.get('rr', 0):.2f}  ·  "
                  f"faltam {g.get('falta', 0)}h")
        cor = '#333'
    return _fechar(ax, jan, baixo, alto, alt, titulo, cor, caminho)


# ------------------------------------------------------- setup 5
def desenhar_falha5(sim, h1, g, caminho):
    """Setup 5: a faixa lateral, a ida para fora, a força e a falha."""
    i = g.get('i')
    k_forca = g.get('k_forca')
    if i is None or k_forca is None:
        return False
    lat = g.get('lat_jan', 60)
    k_gat = g.get('idx') if g.get('entrada') else None

    a0 = max(0, i - lat - 4)
    jan = h1[a0:]
    if len(jan) < 10:
        return False
    venda = g['lado'] == 'venda'

    fig, ax = plt.subplots(figsize=(14, 7.4))
    alto = max(x[2] for x in jan)
    baixo = min(x[3] for x in jan)
    for v in (g.get('stop'), g.get('alvo'), g.get('topo'), g.get('base')):
        if v is not None:
            alto, baixo = max(alto, v), min(baixo, v)
    alt = max(alto - baixo, 1e-12)

    # a faixa lateral: do começo dela até a vela que rompeu
    x0, x1 = i - lat - a0 - .5, i - a0 + .5
    ax.add_patch(Rectangle((x0, g['base']), x1 - x0, g['topo'] - g['base'],
                           facecolor=AZUL, alpha=.13, edgecolor=AZUL,
                           lw=1.5, zorder=1))
    ax.annotate(f"faixa de {lat} velas", ((x0 + x1) / 2, g['topo']),
                color=AZUL, fontsize=10, fontweight='bold', ha='center',
                va='bottom', xytext=((x0 + x1) / 2, g['topo'] + alt * .02))

    # a ida: do rompimento até a vela de força
    ax.axvspan(i - a0 - .5, k_forca - a0 + .5, color=ROXO, alpha=.12, zorder=0)
    ax.annotate(f"ida ({g.get('vol_x', 0):.1f}x o volume da faixa)",
                (i - a0 - 1.5, alto - alt * .11),
                color=ROXO, fontsize=10, fontweight='bold', ha='right',
                va='center')

    marcos = {k - a0 for k in (i, k_forca, g.get('k_ext'), k_gat)
              if k is not None and k >= a0}
    _velas(ax, jan, marcos)

    # a vela de força e o preço que dispara
    q = _dt.datetime.fromtimestamp(h1[k_forca][0] / 1000, BRT)
    ax.annotate(f"força contrária · {q:%d/%m %H:%M}",
                (k_forca - a0, h1[k_forca][2]),
                xytext=(k_forca - a0 - 7, alto - alt * .04),
                color=LARANJA, fontsize=10, fontweight='bold', ha='right',
                arrowprops=dict(arrowstyle='->', color=LARANJA, lw=1.4))
    _niveis(ax, g, len(jan), not venda,
            extras=[(g.get('forca_lim'), LARANJA, 'dispara', ':'),
                    (g.get('ext'), '#888', 'cancela', ':')])

    if k_gat is not None:
        titulo = (f"{sim.replace('USDT','/USDT')} — ROMPIMENTO FALSO · "
                  f"{g['lado'].upper()}  ·  R:R 1:{g['rr']:.2f}  ·  "
                  f"risco {g['risco_pct']:.2f}%")
        cor = VERM if venda else VERDE
    else:
        titulo = (f"{sim.replace('USDT','/USDT')} — força armada · de olho  "
                  f"·  {g['lado']}  ·  faltam {g.get('falta', 0)} velas")
        cor = '#333'
    return _fechar(ax, jan, baixo, alto, alt, titulo, cor, caminho)
