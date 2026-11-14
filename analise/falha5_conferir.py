"""Confere que o MODULO AO VIVO (falha5.py) acha os mesmos gatilhos.

O bot rodou limpo e devolveu 0 gatilhos. Isso e plausivel com 3,6 por mes
em 150 moedas -- mas zero e tambem o que um detector quebrado devolve.

Aqui o falha5.py do bot roda contra o historico baixado e tem de reencontrar
as operacoes que o backtest achou, incluindo XLM 12/10/2026 08:00 e
LINK 12/10/2026 13:00. Se reencontrar, o silencio ao vivo e silencio de
verdade: nao tem montagem armada agora.

Uso:  python3 falha5_conferir.py <pasta> [--n 150]
"""
import argparse, glob, os, statistics, sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explosao8 as e8
import falha5
from explosao import ler

BRT = dt.timezone(dt.timedelta(hours=-3))


def ops_vivo(h, cfg):
    """Todas as entradas que o modulo do bot enxerga nesta serie."""
    a, mv = e8.atr(h, 14), e8.medvol(h, 20)
    out = []
    for m in falha5._montagens(h, cfg, a, mv, 0):
        alta = m['alta']
        for k in range(m['k_forca']+1,
                       min(m['k_forca']+1+cfg['falha_max'], len(h))):
            hk, lk, ck = h[k][2], h[k][3], h[k][4]
            if (hk > m['ext']) if alta else (lk < m['ext']):
                break
            if not ((ck < m['forca_lim']) if alta else (ck > m['forca_lim'])):
                continue
            n = falha5._numeros(h, m, k, a, cfg, ck)
            if n:
                out.append(dict(m, **n, idx=k, vela_ms=h[k][0]))
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=150)
    a = ap.parse_args()
    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 2000:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h,
                        statistics.median(v[4]*v[5] for v in h)))
    cru.sort(key=lambda x: -x[2])
    cru = cru[:a.n]
    fim = max(h[-1][0] for _, h, _ in cru)
    print(f"{len(cru)} moedas · a vela mais recente da base é de "
          f"{dt.datetime.fromtimestamp(fim/1000, BRT):%d/%m/%Y %H:%M} "
          f"(Brasília)\n")

    achados = []
    for sim, h, _ in cru:
        for g in ops_vivo(h, falha5.CFG):
            achados.append((sim, g))
    achados.sort(key=lambda x: x[1]['vela_ms'])
    meses = max(len(h) for _, h, _ in cru)/(24*30.4)
    print(f"o módulo DO BOT achou {len(achados)} entradas em "
          f"{meses:.0f} meses = {len(achados)/meses:.1f} por mês")
    print(f"  (o backtest, no mesmo universo fixo, achou 230 = 2.8/mês)\n")
    print("  as 8 últimas que o bot enxerga:\n")
    for sim, g in achados[-8:][::-1]:
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        print(f"    {sim:<12} {q:%d/%m/%Y %H:%M}  {g['lado']:<6} "
              f"entrada {g['entrada']:<12.8g} R:R 1:{g['rr']:.2f}  "
              f"risco {g['risco_pct']:.2f}%  ida {g['excur']:.2f}x  "
              f"contexto {g['ctx']}")

    print("\n  as duas que eu te mostrei em imagem:\n")
    for alvo_sim, alvo_dia in (('XLMUSDT', '12/10/2026 08:00'),
                               ('LINKUSDT', '12/10/2026 13:00')):
        bate = [(s, g) for s, g in achados if s == alvo_sim and
                f"{dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT):%d/%m/%Y %H:%M}"
                == alvo_dia]
        print(f"    {alvo_sim:<12} {alvo_dia}  "
              f"{'✓ ACHOU' if bate else '✗ NÃO ACHOU'}")

    # E a pergunta do Eduardo: ha quanto tempo foi o ultimo gatilho?
    if achados:
        ult = achados[-1]
        q = dt.datetime.fromtimestamp(ult[1]['vela_ms']/1000, BRT)
        dias = (dt.datetime.fromtimestamp(fim/1000, BRT) - q).days
        print(f"\n  último gatilho: {ult[0]} em {q:%d/%m/%Y %H:%M}, "
              f"{dias} dias antes do fim da base")


if __name__ == '__main__':
    main()
