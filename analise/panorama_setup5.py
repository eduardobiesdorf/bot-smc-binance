"""Panorama do setup 5: a anatomia do padrao e o funil dos filtros."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

F = '#13161b'
fig = plt.figure(figsize=(16, 11.5), facecolor=F)
gs = fig.add_gridspec(3, 1, height_ratios=[3.1, 0.95, 1.5], hspace=0.42)
ax = fig.add_subplot(gs[0]); axv = fig.add_subplot(gs[1]); axf = fig.add_subplot(gs[2])
for A in (ax, axv, axf):
    A.set_facecolor(F)
    for s in A.spines.values():
        s.set_color('#2a2f38')
    A.tick_params(colors='#6b7280', labelsize=8)

# ---------------- velas idealizadas --------------------------------------
import random
random.seed(11)
base, topo = 100.0, 106.0
v, vol = [], []
for n in range(60):                                   # 1 a lateralidade
    o = random.uniform(base + .6, topo - .6)
    c = o + random.uniform(-1.6, 1.6)
    c = min(max(c, base + .4), topo - .4)
    v.append((o, max(o, c) + random.uniform(.1, .7), min(o, c) - random.uniform(.1, .7), c))
    vol.append(random.uniform(.55, 1.15))
p = topo - .5                                         # 2 a ida
for n, passo in enumerate((1.5, 2.1, 1.8, 1.4)):
    o = p; c = o + passo
    v.append((o, c + .45, o - .3, c)); vol.append(1.9 + n*.45); p = c
o = p; c = p - 3.4                                    # 3 a forca contraria
v.append((o, o + 1.5, c - .4, c)); vol.append(3.5); p = c
for n, passo in enumerate((1.2, -1.0, -1.5)):         # 4 a falha
    o = p; c = o + passo
    v.append((o, max(o, c) + .5, min(o, c) - .5, c)); vol.append(1.5 - n*.2); p = c
for passo in (-1.6, -1.1):                            # 5 a volta
    o = p; c = o + passo
    v.append((o, o + .4, c - .5, c)); vol.append(1.3); p = c
for passo in (-1.3, -1.8, -1.1, -1.6, -1.2, -0.9, -1.4, -1.0):
    o = p; c = o + passo                              # 6 busca a piscina
    v.append((o, o + .4, c - .6, c)); vol.append(1.1); p = c

i0, kf = 60, 64                      # inicio da ida, vela de forca
k_falha, k_volta = 67, 69
ext = max(x[1] for x in v[i0:kf+1])
piscina = 92.0

ax.add_patch(Rectangle((-0.5, base), len(v) + 7, topo - base,
                       facecolor='#42a5f5', alpha=.10, zorder=0))
ax.axhline(topo, color='#42a5f5', alpha=.5, lw=1); ax.axhline(base, color='#42a5f5', alpha=.5, lw=1)
ax.axvspan(i0 - .5, kf + .5, color='#ffd54f', alpha=.09, zorder=1)
ax.axvspan(kf - .5, kf + .5, color='#ab47bc', alpha=.30, zorder=2)

for n, (o, hi, lo, c) in enumerate(v):
    cor = '#26a69a' if c >= o else '#ef5350'
    ax.plot([n, n], [lo, hi], color=cor, lw=1.2, zorder=3)
    ax.add_patch(Rectangle((n - .34, min(o, c)), .68, max(abs(c - o), .06),
                           facecolor=cor, edgecolor=cor, zorder=4))
    axv.bar(n, vol[n], color=cor, width=.68, alpha=.85)
axv.axhline(sum(vol[:60]) / 60, color='#ffd54f', lw=1.3)
axv.set_ylabel('volume', color='#9aa3ae', fontsize=9)
axv.set_xlim(-1, len(v) + 7); axv.set_yticks([])
axv.annotate('a média da faixa', (3, sum(vol[:60]) / 60), color='#ffd54f',
             fontsize=8.5, xytext=(0, 6), textcoords='offset points')

pivo = 97.6
ax.plot([-0.5, len(v) + 6], [pivo, pivo], color='#78909c', lw=1.1, ls=':', zorder=2)
ax.annotate('o TOPO ANTERIOR que já foi rompido — a faixa está inteira acima dele.\n'
            'É o que faz o contexto ser comprador: +\\$32,66 por operação contra +\\$8,93 sem ele',
            (1, pivo), color='#b0bec5', fontsize=9.5, va='top',
            xytext=(0, -8), textcoords='offset points')

for y, cor, txt in ((ext + .35, '#ef5350', 'STOP  — acima da máxima da ida'),
                    (v[k_volta][3], '#ffffff', 'ENTRADA'),
                    (piscina, '#26a69a', 'ALVO — a piscina: o último fundo não '
                                         'consumido abaixo de TODA a faixa')):
    ax.plot([-0.5, len(v) + 6], [y, y], color=cor, lw=1.3, alpha=.9, zorder=6)
    ax.annotate(txt, (len(v) + 6, y), color=cor, fontsize=10, va='bottom',
                ha='right', xytext=(0, 5), textcoords='offset points', zorder=9)

passos = [
    (28, topo + 1.0, '1 · A LATERALIDADE\n60 velas de H1, estreita e oscilando', '#64b5f6'),
    (62, ext + 1.2, '2 · A IDA\nfecha pra fora, volume subindo', '#ffd54f'),
    (kf, v[kf][2] - 1.6, '3 · A FORÇA CONTRÁRIA\no alerta', '#ce93d8'),
    (k_falha + .5, v[k_falha][1] + 1.2, '4 · A FALHA\nnão faz nova máxima', '#ffffff'),
    (k_volta + 1.5, base - 1.8, '5 · O GATILHO\ncom confirmação', '#ffffff'),
    (80, piscina + 1.6, '6 · BUSCA A PISCINA', '#26a69a')]
for x, y, t, c in passos:
    ax.annotate(t, (x, y), color=c, fontsize=10.5, ha='center',
                va='center', fontweight='bold', zorder=8)
ax.add_patch(FancyArrowPatch((k_volta + 1, base - .6), (78, piscina + .8),
                             arrowstyle='-|>', mutation_scale=16,
                             color='#26a69a', lw=1.4, alpha=.75, zorder=7))
ax.set_xlim(-1, len(v) + 7)
ax.set_ylim(piscina - 3, ext + 4.2)
ax.set_yticks([]); ax.set_xticks([])
ax.set_title('SETUP 5  ·  rompimento falso e volta à faixa  ·  velas de 1 hora  ·  '
             'a anatomia do padrão', color='#e8eaed', fontsize=14.5, pad=16)

# ---------------- o funil -------------------------------------------------
linhas = [
    ('sem filtro de contexto',          517, 40.0,  8.93, '#546e7a'),
    ('só exige que exista contexto',    481, 40.3, 10.19, '#546e7a'),
    ('CONTRA o contexto  (controle)',   297, 36.0, -4.19, '#ef5350'),
    ('A FAVOR do contexto',             185, 47.0, 32.66, '#26a69a'),
    ('a favor + pivô de 20 velas',      148, 51.4, 45.92, '#26a69a')]
y = range(len(linhas))
axf.barh(list(y), [l[3] for l in linhas], color=[l[4] for l in linhas],
         height=.62, alpha=.9)
axf.axvline(0, color='#6b7280', lw=1)
for n, (nome, op, ac, dol, _) in enumerate(linhas):
    axf.annotate(f'{nome}', (0, n), color='#e8eaed', fontsize=10.5, va='center',
                 ha='right' if dol > 0 else 'left',
                 xytext=(-10 if dol > 0 else 10, 0), textcoords='offset points')
    axf.annotate(f'\\${dol:+.2f} por operação     ·     {op} ops, {op/83:.1f} por mês'
                 f'     ·     {ac:.1f}% de acerto',
                 (dol, n), color='#9aa3ae', fontsize=9.5, va='center',
                 ha='left' if dol > 0 else 'right',
                 xytext=(8 if dol > 0 else -8, 0), textcoords='offset points')
axf.set_yticks([]); axf.set_ylim(-.7, len(linhas) - .3)
axf.set_xlim(-30, 78)
axf.set_xticks([])
axf.set_title('O QUE O CONTEXTO FAZ  ·  83 meses, 150 maiores, risco fixo de $100 '
              'por operação  ·  a barra vermelha é o controle: o mesmo padrão '
              'contra o contexto PERDE',
              color='#e8eaed', fontsize=12, pad=12)

fig.savefig('/home/claude/bot-smc-binance/panorama_setup5.png', dpi=115,
            facecolor=F, bbox_inches='tight')
print('ok')
