"""Quem na fila do bot NAO e cripto 24/7?

A amostra do terceiro alerta veio em BMNRBUSDT e o negocia_sempre() deixou
passar. Antes de mexer no filtro, MEDE: para cada par da fila, quanto da
semana ele fica parado, por tres sinais diferentes.

  mortas   velas sem volume OU sem amplitude (o filtro de hoje)
  fds      fatia do volume que acontece no sabado e no domingo
           (cripto 24/7 fica perto de 2/7 = 28,6%; acao fica perto de 0%)
  noite    fatia do volume fora de 13h-21h UTC, que e o pregao de NY
           (cripto fica perto de 2/3; acao fica perto de 0%)

Uso:  python3 conferir_24x7.py [--n 150]
"""
import argparse, os, sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot_varredura as bot


def medidas(h):
    ult = h[-300:]
    mortas = sum(1 for c in ult if c[5] <= 0 or c[2] <= c[3]) / len(ult)
    vol_fds = vol_tot = vol_noite = 0.0
    for c in h:
        q = dt.datetime.fromtimestamp(c[0]/1000, dt.timezone.utc)
        vol_tot += c[5]
        if q.weekday() >= 5:
            vol_fds += c[5]
        if not (13 <= q.hour < 21):
            vol_noite += c[5]
    if vol_tot <= 0:
        return mortas, 0.0, 0.0
    return mortas, vol_fds/vol_tot, vol_noite/vol_tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=150)
    a = ap.parse_args()

    fila = bot.candidatos(a.n)
    print(f"{len(fila)} pares na fila do bot\n")
    print(f"{'par':<16}{'mortas':>9}{'fds':>8}{'noite':>8}"
          f"{'filtro de hoje':>17}   suspeita")
    print('-'*74)
    linhas = []
    for sim in fila:
        try:
            h = bot.buscar(sim, '1h', 1300)
        except Exception as e:
            print(f"{sim:<16}  erro: {e}")
            continue
        if len(h) < 500:
            continue
        m, f, n = medidas(h)
        passa = bot.negocia_sempre(h)
        # acao tokenizada: quase nada de volume no fim de semana E quase
        # nada fora do pregao de Nova York
        susp = f < 0.12 or n < 0.35
        linhas.append((f, sim, m, n, passa, susp))
    linhas.sort()
    for f, sim, m, n, passa, susp in linhas:
        print(f"{sim:<16}{m*100:>8.1f}%{f*100:>7.1f}%{n*100:>7.1f}%"
              f"{'passa' if passa else 'CORTA':>17}"
              f"   {'<<< NÃO É CRIPTO' if susp else ''}")
    ruins = [x for x in linhas if x[5]]
    furos = [x for x in ruins if x[4]]
    print(f"\n  suspeitos de não ser cripto: {len(ruins)}")
    print(f"  deles, o filtro de hoje DEIXA PASSAR: {len(furos)}"
          + (f" — {', '.join(x[1] for x in furos)}" if furos else ""))
    if ruins:
        print(f"\n  fds dos suspeitos: até {max(x[0] for x in ruins)*100:.1f}%")
    bons = [x for x in linhas if not x[5]]
    if bons:
        print(f"  fds dos normais:   a partir de "
              f"{min(x[0] for x in bons)*100:.1f}%")


if __name__ == '__main__':
    main()
