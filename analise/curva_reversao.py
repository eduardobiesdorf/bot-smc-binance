"""Desenha a curva da reversao ao longo do tempo, com o rebaixamento.

Le operacoes_reversao.csv (gerado por lista_operacoes.py) e desenha o
ganho acumulado com risco fixo, marcando cada alvo em verde e cada stop
em vermelho, com o pior rebaixamento destacado. Embaixo, o rebaixamento
em cada momento.

O que a curva mostra e a media esconde:
  - os primeiros 2 anos e meio sao quase planos (0 -> $36 ate out/2022)
  - o pior rebaixamento (-$67, 2o semestre de 2025) vem LOGO ANTES do
    melhor momento (+$245 no 1o semestre de 2026)
  - 48% do lucro de 7 anos saiu de um semestre so

Uso:  python3 curva_reversao.py [--csv operacoes_reversao.csv]
                                [--risco 10] [--saida curva_reversao.png]
"""
import argparse
import csv
import datetime as dt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default='operacoes_reversao.csv')
    ap.add_argument('--risco', type=float, default=10.0)
    ap.add_argument('--saida', default='curva_reversao.png')
    a = ap.parse_args()
    esc = a.risco / 100.0

    r = list(csv.DictReader(open(a.csv)))
    for x in r:
        x['d'] = dt.datetime.strptime(x['data_brasilia'], '%Y-%m-%d %H:%M')
        x['v'] = float(x['result_risco100']) * esc
    r.sort(key=lambda x: x['d'])

    xs, ys, dds = [r[0]['d'] - dt.timedelta(days=30)], [0.0], [0.0]
    ac = pico = 0.0
    pg, ps = [], []
    for x in r:
        ac += x['v']
        pico = max(pico, ac)
        xs.append(x['d']); ys.append(ac); dds.append(ac - pico)
        (pg if x['desfecho'] == 'alvo' else ps).append((x['d'], ac))

    g = sum(1 for x in r if x['desfecho'] == 'alvo')
    med = sum(x['v'] for x in r)/len(r)

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(15, 8.6), sharex=True,
                                  gridspec_kw={'height_ratios': [3, 1]},
                                  facecolor='#13161b')
    for A in (ax, ax2):
        A.set_facecolor('#13161b')
        A.tick_params(colors='#6b7280', labelsize=9)
        for s in A.spines.values():
            s.set_color('#2a2f38')
        A.grid(color='#1e232b', linewidth=.6)

    ax.plot(xs, ys, color='#26a69a', linewidth=2.0, zorder=5)
    ax.fill_between(xs, 0, ys, color='#26a69a', alpha=.10, zorder=1)
    ax.axhline(0, color='#6b7280', linewidth=.8, alpha=.6)
    ax.scatter([p[0] for p in pg], [p[1] for p in pg], s=13,
               color='#26a69a', zorder=6, linewidths=0)
    ax.scatter([p[0] for p in ps], [p[1] for p in ps], s=13,
               color='#ef5350', zorder=6, linewidths=0)

    i = dds.index(min(dds))
    j = max(k for k in range(i+1) if dds[k] == 0)
    ax.axvspan(xs[j], xs[i], color='#ef5350', alpha=.08, zorder=0)
    ax.annotate(f"pior rebaixamento\n−${-min(dds):.0f}",
                (xs[j] + (xs[i]-xs[j])/2, max(ys)*0.30), color='#ef9a9a',
                fontsize=10, ha='center')
    for ano in range(xs[0].year + 1, xs[-1].year + 1):
        ax.axvline(dt.datetime(ano, 1, 1), color='#2a2f38', linewidth=.8,
                   linestyle=':', zorder=0)

    ax.set_title(
        f"Reversão de 8h · risco fixo de ${a.risco:.0f} por operação · "
        f"{len(r)} operações\n{g/len(r)*100:.0f}% de acerto · "
        f"{med:+.2f} por operação · {sum(x['v'] for x in r):+.0f} no total · "
        f"pior rebaixamento ${-min(dds):.0f}",
        color='#e8eaed', fontsize=13, pad=16)
    ax.set_ylabel('ganho acumulado, em dólares', color='#9aa3ae', fontsize=10)

    ax2.fill_between(xs, 0, dds, color='#ef5350', alpha=.35, zorder=2)
    ax2.plot(xs, dds, color='#ef5350', linewidth=1.0, zorder=3)
    ax2.set_ylabel('rebaixamento', color='#9aa3ae', fontsize=10)
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))

    fig.tight_layout()
    fig.savefig(a.saida, dpi=115, facecolor='#13161b')
    print(a.saida)

    print("\nsemestre a semestre:")
    ac = 0.0
    for ano in range(xs[0].year, xs[-1].year + 1):
        for sem, (m0, m1) in enumerate(((1, 6), (7, 12)), 1):
            s = [x for x in r if x['d'].year == ano and m0 <= x['d'].month <= m1]
            if not s:
                continue
            al = sum(1 for x in s if x['desfecho'] == 'alvo')
            ac += sum(x['v'] for x in s)
            print(f"  {ano} S{sem}:  {sum(x['v'] for x in s):>+8.2f}   "
                  f"({al}/{len(s)})   acumulado {ac:>+8.2f}")


if __name__ == '__main__':
    main()
