"""O MAPA: o que prevê o retorno das proximas horas?

Isto NAO e caca a estrategia. Procurar regra no mesmo dado onde ja se
garimpou o dia inteiro produz falso positivo com certeza. Aqui as
variaveis sao fixadas ANTES, todas as celulas sao reportadas (nao so
as boas), e o retorno e DESCONTADO DA MEDIA DO MERCADO no mesmo
instante -- sem isso, num periodo em que cripto subiu, qualquer coisa
parece funcionar.

O que sobra depois de descontar a mare e leitura de verdade.

VARIAVEIS (fixadas antes de olhar):
  funding    a taxa cobrada, em percentil dentro da historia da moeda
  ret 8h / 24h / 7d   momentum ou reversao, em tres escalas
  volume     a vela contra a media de 20
  faixa      onde o fechamento esta na faixa das ultimas 20 velas
  hora       a hora UTC em que a vela de 8h fecha (0, 8, 16)
  vol        a volatilidade recente, em percentil

PARA FRENTE: retorno em 8h, 24h e 72h, cross-sectionalmente descontado.

Uso:  python3 mapa.py <klines> <funding>
"""
import argparse, bisect, csv, glob, math, os, statistics, sys
import datetime as dt
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8
from explosao import ler

H = 3600_000


def pct_rank(v, hist):
    """percentil de v dentro de hist (lista ordenada)."""
    if not hist:
        return 0.5
    return bisect.bisect_left(hist, v) / len(hist)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('klines')
    ap.add_argument('funding')
    ap.add_argument('--n', type=int, default=150)
    a = ap.parse_args()

    # ---- carrega
    series, fund, tempos = {}, {}, {}
    for p in sorted(glob.glob(os.path.join(a.klines, '*_1h.csv'))):
        s = os.path.basename(p).replace('_1h.csv', '')
        h = ler(p)
        if len(h) < 600:
            continue
        series[s] = rev.juntar(h, 8)
        f = []
        try:
            with open(os.path.join(a.funding, f'{s}_funding.csv')) as fh:
                for r in csv.DictReader(fh):
                    f.append((int(r['tempo_ms']), float(r['taxa'])))
        except Exception:
            pass
        f.sort()
        fund[s] = f
        tempos[s] = [x[0] for x in f]
    print(f"{len(series)} pares com klines e funding\n", flush=True)

    # ---- monta as observacoes
    obs = []
    for s, h in series.items():
        if len(h) < 60:
            continue
        a8 = e8.atr(h, 14)
        mv = e8.medvol(h, 20)
        taxas_vistas = []
        for i in range(25, len(h) - 10):
            cl = h[i][4]
            if cl <= 0 or a8[i] <= 0 or mv[i] <= 0:
                continue
            # funding vigente
            tx = None
            if tempos[s]:
                k = bisect.bisect_right(tempos[s], h[i][0] + 8*H) - 1
                if k >= 0:
                    tx = fund[s][k][1]
            faixa = h[i-20:i]
            tmax = max(x[2] for x in faixa)
            tmin = min(x[3] for x in faixa)
            pos_faixa = (cl - tmin)/(tmax - tmin) if tmax > tmin else .5
            o = dict(
                s=s, t=h[i][0],
                hora=dt.datetime.fromtimestamp(
                    (h[i][0] + 8*H)/1000, dt.timezone.utc).hour,
                ret8=(cl - h[i-1][4])/h[i-1][4],
                ret24=(cl - h[i-3][4])/h[i-3][4],
                ret7d=(cl - h[i-21][4])/h[i-21][4],
                vol_x=h[i][5]/mv[i],
                faixa=pos_faixa,
                volat=a8[i]/cl,
                tx=tx,
                f8=(h[i+1][4]-cl)/cl,
                f24=(h[i+3][4]-cl)/cl,
                f72=(h[i+9][4]-cl)/cl)
            if tx is not None:
                taxas_vistas.append(tx)
                o['tx_pct'] = pct_rank(tx, sorted(taxas_vistas))
            obs.append(o)
    print(f"{len(obs):,} observações de 8h\n", flush=True)

    # ---- desconta a media do mercado em cada instante
    por_t = defaultdict(list)
    for o in obs:
        por_t[o['t']].append(o)
    for t, grupo in por_t.items():
        if len(grupo) < 5:
            for o in grupo:
                o['viva'] = False
            continue
        for campo in ('f8', 'f24', 'f72'):
            m = statistics.median(x[campo] for x in grupo)
            for o in grupo:
                o[campo + 'd'] = o[campo] - m
        for o in grupo:
            o['viva'] = True
    obs = [o for o in obs if o.get('viva')]
    print(f"{len(obs):,} depois de exigir 5+ moedas no mesmo instante\n",
          flush=True)

    def mostra(nome, chave, cortes, rot=None):
        print(f"{'='*104}\n  {nome}\n{'='*104}")
        print(f"{'faixa':<26}{'n':>9}"
              + ''.join(f"{f'{c} à frente':>22}" for c in ('8h', '24h', '72h')))
        sel = [o for o in obs if o.get(chave) is not None]
        if not sel:
            print("  sem dado"); return
        baldes = defaultdict(list)
        for o in sel:
            v = o[chave]
            k = sum(1 for c in cortes if v >= c)
            baldes[k].append(o)
        for k in sorted(baldes):
            g = baldes[k]
            lo = f"{cortes[k-1]:g}" if k > 0 else "-inf"
            hi = f"{cortes[k]:g}" if k < len(cortes) else "+inf"
            nome_b = rot[k] if rot else f"{lo} a {hi}"
            linha = f"{nome_b:<26}{len(g):>9,}"
            for campo in ('f8d', 'f24d', 'f72d'):
                v = [x[campo] for x in g]
                m = statistics.mean(v)*100
                e = (statistics.pstdev(v)/len(v)**.5)*100 if len(v) > 1 else 0
                t = m/e if e else 0
                linha += f"{m:>+12.3f}% {f'({t:+.1f})':>8}"
            print(linha)
        print(f"\n  (entre parênteses, em quantos desvios o número está de "
              f"zero;\n   acima de 3 em módulo começa a significar algo neste "
              f"tamanho de amostra)\n")

    mostra("A TAXA DE FUNDING (percentil na história da própria moeda)",
           'tx_pct', [.1, .25, .5, .75, .9],
           ['os 10% mais negativos', '10-25%', '25-50%', '50-75%',
            '75-90%', 'os 10% mais positivos'])
    mostra("A TAXA DE FUNDING (valor bruto, por cobrança de 8h)",
           'tx', [-0.0005, -0.0001, 0.0001, 0.0005, 0.001],
           ['abaixo de -0,05%', '-0,05% a -0,01%', '-0,01% a +0,01%',
            '+0,01% a +0,05%', '+0,05% a +0,10%', 'acima de +0,10%'])
    mostra("O RETORNO DAS ÚLTIMAS 8 HORAS", 'ret8',
           [-.10, -.04, -.01, .01, .04, .10])
    mostra("O RETORNO DAS ÚLTIMAS 24 HORAS", 'ret24',
           [-.15, -.06, -.02, .02, .06, .15])
    mostra("O RETORNO DOS ÚLTIMOS 7 DIAS", 'ret7d',
           [-.30, -.12, -.04, .04, .12, .30])
    mostra("O VOLUME DA VELA, vezes a média de 20", 'vol_x',
           [.5, .8, 1.2, 2, 4])
    mostra("ONDE O FECHAMENTO ESTÁ NA FAIXA DE 20 VELAS", 'faixa',
           [.1, .3, .5, .7, .9],
           ['nos 10% do fundo', '10-30%', '30-50%', '50-70%', '70-90%',
            'nos 10% do topo'])
    mostra("A HORA UTC EM QUE A VELA DE 8H FECHA", 'hora',
           [8, 16], ['fecha às 00:00', 'fecha às 08:00', 'fecha às 16:00'])
    mostra("A VOLATILIDADE RECENTE (ATR sobre o preço)", 'volat',
           [.01, .02, .04, .08, .15])


if __name__ == '__main__':
    main()
