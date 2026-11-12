"""Reversao no H8, entrada refinada no H4.

O padrao e o mesmo: o preco vinha caindo e uma vela unica de 8h rompe o
ultimo topo. O que muda e a ENTRADA: em vez de comprar na primeira vela
que fecha de volta para fora do order block, espera uma confirmacao.

Confirmacoes testadas (todas medidas em velas de 4h, depois do encosto):
  direta        a primeira vela que fecha de volta para fora (o de hoje)
  volume        essa vela precisa de volume acima da media
  reclama       fecha acima do TOPO do order block, nao so da base
  duas velas    duas fechadas seguidas do lado de fora
  rompe a vela  fecha acima da maxima da vela que encostou
  fundo mais alto  so entra depois de o H4 deixar um fundo acima do
                fundo do encosto -- estrutura virando

O criterio: 2026 e o ano fora da amostra desta ideia (2025 deu +75 por
operacao, 2026 deu -38). Uma confirmacao so presta se deixar os DOIS
anos positivos.

Uso:  python3 reversao_confirma.py <pasta> [--faixas 4]
"""
import argparse
import glob
import itertools
import os
import random
import statistics
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explosao8 as exp8
from explosao import ler, juntar, curva, RISCO, TAXA, FUND8
from explosao_reversao import ultimo_topo as _ut_base

BRT = dt.timezone(dt.timedelta(hours=-3))

# As janelas valem em HORAS, nao em velas. Os valores sao os que o H8
# usava (20, 30 e 30 velas de 8h), para que o mesmo setup em H4, H2 e H1
# continue exigindo o MESMO tempo de calendario. Sem isso, "vinha
# caindo nas ultimas 20 velas" virava 20 horas no H1 -- nao e tendencia,
# e ruido, e o teste media outro setup.
BASE = dict(sigma=2.5, vol=1.5, ob_busca=6,
            pivo_h=16,        # 2 velas de 8h de cada lado do pivo
            topo_h=240,       # 30 velas de 8h procurando o ultimo topo
            tend_h=160,       # 20 velas de 8h medindo a queda
            espera_h=240,     # 30 velas de 8h esperando o encosto
            tend_atr=2.0, perto_do_fundo=0.35,
            # a volatilidade de uma vela de 8h vale 1,46x a de H4, 2,10x
            # a de H2 e 3,05x a de H1 (medido em 142 moedas). Com
            # sigma_abs, a explosao precisa ter o MESMO tamanho absoluto
            # em qualquer tempo grafico -- e o mesmo evento, pego antes,
            # em vez de um evento tres vezes menor.
            sigma_abs=False,
            # A queda de 160h e a MESMA queda de preco em qualquer tempo
            # grafico. Medi-la em volatilidades da propria vela torna a
            # exigencia 3x menor no H1 -- era isso que fazia o H1
            # disparar 794 vezes em coisa que nao era tendencia.
            # Com tend_abs, a queda exigida e a mesma em preco.
            tend_abs=False,
            gat_h4=12,        # velas de 4h para a confirmacao aparecer
            furo_max=1.0, rr_min=1.2, stop_folga=0.10, est_min=0.5,
            alvo_proj=0.9, modo='direta', vol_min=0.0, tfp=8)


def explosoes(h8, cfg):
    """As velas de explosao de reversao, com o order block e o alvo."""
    a, mv = exp8.atr(h8, 14), exp8.medvol(h8, 20)
    tfp = cfg['tfp']
    esc = {8: 1.0, 4: 1.46, 2: 2.10, 1: 3.05}.get(tfp, (8/tfp)**0.5)
    sig = cfg['sigma'] * (esc if cfg.get('sigma_abs') else 1.0)
    tnd = cfg['tend_atr'] * (esc if cfg.get('tend_abs') else 1.0)
    # as janelas, convertidas de horas para velas deste tempo grafico
    pv = max(1, round(cfg['pivo_h']/tfp))
    bt = max(5, round(cfg['topo_h']/tfp))
    tj = max(5, round(cfg['tend_h']/tfp))
    cfg = dict(cfg, pivo=pv, busca_topo=bt)
    fora = []
    for i in range(max(tj, bt, 21) + 1, len(h8) - 2):
        o, hi, lo, cl, vol = h8[i][1], h8[i][2], h8[i][3], h8[i][4], h8[i][5]
        rng = hi - lo
        if rng <= 0 or a[i-1] <= 0 or mv[i-1] <= 0 \
                or rng < sig*a[i-1] or abs(cl-o)/rng < 0.5 \
                or vol < cfg['vol']*mv[i-1]:
            continue
        alta = cl > o
        jan = h8[i-tj:i]
        queda = (h8[i-tj][4] - h8[i-1][4]) / a[i-1] if alta \
            else (h8[i-1][4] - h8[i-tj][4]) / a[i-1]
        if queda < tnd:
            continue
        tmax = max(x[2] for x in jan); tmin = min(x[3] for x in jan)
        if tmax > tmin and cfg['perto_do_fundo']:
            pos_ = (lo-tmin)/(tmax-tmin) if alta else (tmax-hi)/(tmax-tmin)
            if pos_ > cfg['perto_do_fundo']:
                continue
        topo_ant, _ = _ut_base(h8, i, alta, cfg)
        if topo_ant is None or ((cl <= topo_ant) if alta else (cl >= topo_ant)):
            continue
        ob_base = ob_topo = None
        j = i - 1
        while j >= max(0, i - cfg['ob_busca']):
            if (h8[j][4] > h8[j][1]) != alta:
                ob_base, ob_topo = h8[j][3], h8[j][2]
                break
            j -= 1
        if ob_base is None:
            continue
        fora.append(dict(i=i, alta=alta, ob_base=ob_base, ob_topo=ob_topo,
                         atr=a[i], topo=hi if alta else lo,
                         tam=hi-lo, fim_ms=h8[i][0] + cfg['tfp']*3600_000,
                         queda=queda))
    return fora


def entrada_h4(h4, mv4, e, cfg, pos4, tfe=4, tfp=8):
    """Do fim da explosao ate a confirmacao, em velas de 4h."""
    alta = e['alta']
    k0 = pos4.get(e['fim_ms'])
    if k0 is None:
        return None
    borda = e['ob_topo'] if alta else e['ob_base']
    volta = borda
    morte = (e['ob_base'] - e['atr']*cfg['furo_max']) if alta else \
            (e['ob_topo'] + e['atr']*cfg['furo_max'])
    pico = e['topo']
    tocou = extremo = seguidas = None
    seguidas = 0
    # as janelas valem em HORAS, para H4 e H1 esperarem o mesmo tempo
    lim = min(k0 + int(cfg['espera_h']/tfe), len(h4))
    gat = max(1, int(cfg['gat_h4']*4/tfe))
    for k in range(k0, lim):
        hi, lo, o, cl = h4[k][2], h4[k][3], h4[k][1], h4[k][4]
        if tocou is None:
            pico = max(pico, hi) if alta else min(pico, lo)
            if (lo <= borda) if alta else (hi >= borda):
                tocou, extremo = k, (lo if alta else hi)
                alto_toque, baixo_toque = hi, lo
            else:
                continue
        else:
            extremo = min(extremo, lo) if alta else max(extremo, hi)
        if (extremo < morte) if alta else (extremo > morte):
            return None
        if k - tocou > gat:
            return None
        if (hi >= pico) if alta else (lo <= pico):
            return None
        rng = hi - lo
        dentro = (cl > volta) if alta else (cl < volta)
        favor = (cl > o) if alta else (cl < o)
        if rng <= 0 or not dentro or not favor:
            seguidas = 0
            continue
        corpo = abs(cl - o)/rng
        pav = ((min(o, cl)-lo) if alta else (hi-max(o, cl)))/rng
        if not (corpo >= 0.5 or pav >= 0.5):
            seguidas = 0
            continue
        seguidas += 1
        # --- as confirmacoes
        if cfg['modo'] == 'duas' and seguidas < 2:
            continue
        if cfg['vol_min'] and mv4[k] > 0 and h4[k][5] < cfg['vol_min']*mv4[k]:
            continue
        if cfg['modo'] in ('raso', 'raso_rompe'):
            # o encosto nao pode ter afundado no order block
            meio = (e['ob_base'] + e['ob_topo'])/2
            if (extremo < meio) if alta else (extremo > meio):
                return None
        if cfg['modo'] in ('rompe_vela', 'raso_rompe'):
            if (cl <= alto_toque) if alta else (cl >= baixo_toque):
                continue
        if cfg['modo'] == 'fundo_alto':
            # precisa de um fundo de H4 acima do fundo do encosto
            if k <= tocou + 1:
                continue
            fundos = [h4[x][3] for x in range(tocou, k)] if alta else \
                     [h4[x][2] for x in range(tocou, k)]
            if alta and min(fundos[1:] or [fundos[0]]) <= extremo:
                continue
            if not alta and max(fundos[1:] or [fundos[0]]) >= extremo:
                continue
        return dict(idx=k, ent=cl, pico=pico, tocou=tocou)
    return None


def rodar(cru, cfg, faixa, tfe=4, tfp=8):
    ops = []
    for sim, h1, _ in cru:
        h8, h4 = juntar(h1, tfp), juntar(h1, tfe)
        if len(h8) < 80 or len(h4) < 160:
            continue
        mv4 = exp8.medvol(h4, 20)
        pos4 = {v[0]: k for k, v in enumerate(h4)}
        for e in explosoes(h8, cfg):
            r = entrada_h4(h4, mv4, e, cfg, pos4, tfe, tfp)
            if not r:
                continue
            alta = e['alta']
            if abs(r['pico'] - (e['topo'] - (e['tam'] if alta else -e['tam'])
                                )) < 0:
                pass
            ent = r['ent']
            stop = (e['ob_base'] - e['atr']*cfg['stop_folga']) if alta else \
                   (e['ob_topo'] + e['atr']*cfg['stop_folga'])
            risco = abs(ent - stop)
            if risco <= 0:
                continue
            ate_topo = (r['pico'] - ent) if alta else (ent - r['pico'])
            if ate_topo <= 0 or ate_topo/risco < cfg['rr_min']:
                continue
            if abs(r['pico'] - e['topo'])/e['atr'] < 0 or \
                    abs(e['topo'] - 0) == 0:
                pass
            est = abs(r['pico'] - e['topo'])/e['atr'] if e['atr'] else 0
            alvo = (e['topo'] + cfg['alvo_proj']*e['tam']) if alta else \
                   (e['topo'] - cfg['alvo_proj']*e['tam'])
            dist = (alvo - ent) if alta else (ent - alvo)
            if dist <= 0:
                continue
            fim = saida = None
            for m in range(r['idx']+1,
                           min(r['idx']+1+int(960/tfe), len(h4))):
                hi, lo = h4[m][2], h4[m][3]
                if alta:
                    if lo <= stop: fim, saida = 'stop', stop; break
                    if hi >= alvo: fim, saida = 'alvo', alvo; break
                else:
                    if hi >= stop: fim, saida = 'stop', stop; break
                    if lo <= alvo: fim, saida = 'alvo', alvo; break
            if fim is None:
                continue
            pos = RISCO/(risco/ent*100/100)
            mov = (saida-ent)/ent*(1 if alta else -1)
            horas = (m-r['idx'])*tfe
            q = dt.datetime.fromtimestamp(h4[r['idx']][0]/1000, BRT)
            ops.append(dict(sim=sim, liq=pos*mov - pos*TAXA*2 -
                            pos*(horas/8)*FUND8, ano=q.year, q=q,
                            faixa=faixa[sim], rr=dist/risco,
                            risco_pct=risco/ent*100,
                            mes=q.strftime('%Y-%m')))
    ops.sort(key=lambda o: o['q'])
    return ops


def ps(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def painel(rot, sel, larg=26):
    if not sel:
        print(f"{rot:<{larg}}{'—':>5}"); return
    v = [o['liq'] for o in sel]
    g = [x for x in v if x > 0]
    tot, dd = curva(v)
    anos = sorted({o['ano'] for o in sel})
    porano, bons = [], 0
    for y in anos:
        vy = [o['liq'] for o in sel if o['ano'] == y]
        m = statistics.mean(vy)
        if m > 0:
            bons += 1
        porano.append(f"{str(y)[2:]}:{m:+.0f}({len(vy)})")
    ok = '✓' if bons == len(anos) and len(anos) >= 2 else f'{bons}/{len(anos)}'
    z = ''
    if len(v) >= 25:
        random.seed(3)
        nu = [statistics.mean([x if random.random() < .5 else -x for x in v])
              for _ in range(300)]
        z = f"{(statistics.mean(v)-statistics.mean(nu))/(statistics.pstdev(nu) or 1e-9):+.2f}"
    print(f"{rot:<{larg}}{len(v):>5}{len(g)/len(v)*100:>8.1f}%"
          f"{statistics.mean(o['rr'] for o in sel):>7.2f}"
          f"{statistics.mean(v):>+10.1f}{tot:>+9.0f}{dd:>8.0f}{ps(v):>5}"
          f"{z:>8}{ok:>6}  {' '.join(porano)}")


def cab(larg=26):
    print(f"{'':<{larg}}{'n':>5}{'acerto':>9}{'R:R':>7}{'méd/op':>10}"
          f"{'total':>9}{'rb':>8}{'seq':>5}{'z':>8}{'anos+':>6}"
          f"  por ano: méd/op (n)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--corte', type=float, default=0.0)
    ap.add_argument('--faixas', type=int, default=1)
    ap.add_argument('--blocos', default='',
                    help='cortes do ranking de volume, ex 50,100,150,200')
    ap.add_argument('--padrao', default='8',
                    help='tempos gráficos do padrão, em horas')
    ap.add_argument('--entrada', default='4',
                    help='tempos gráficos da entrada, em horas')
    a = ap.parse_args()
    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) < 400:
            continue
        vm = statistics.median(v[4]*v[5] for v in h)
        if vm >= a.corte*1e6:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h, vm))
    cru.sort(key=lambda x: -x[2])
    nf = max(1, len(cru)//a.faixas)
    faixa = {s: min(k//nf, a.faixas-1) for k, (s, _, _) in enumerate(cru)}
    rot_f = []
    for i_ in range(a.faixas):
        vs = [vm for k, (s, _, vm) in enumerate(cru) if faixa[s] == i_]
        rot_f.append(f"faixa {i_+1}: {len(vs)} moedas, "
                     f"{min(vs)/1e6:,.2f} a {max(vs)/1e6:,.0f} M USD/h")
    print(f"{len(cru)} moedas · padrão em H8, entrada em "
          f"{', '.join('H'+x for x in a.entrada.split(','))}")
    for r_ in rot_f:
        print("  " + r_)

    VAR = [
        ('direta (como está hoje)', dict(BASE)),
        ('volume ≥ 1,2x', dict(BASE, vol_min=1.2)),
        ('volume ≥ 1,5x', dict(BASE, vol_min=1.5)),
        ('encosto raso no OB', dict(BASE, modo='raso')),
        ('duas velas seguidas', dict(BASE, modo='duas')),
        ('rompe a vela do encosto', dict(BASE, modo='rompe_vela')),
        ('raso + volume ≥1,2x', dict(BASE, modo='raso', vol_min=1.2)),
        ('raso + rompe a vela', dict(BASE, modo='raso_rompe')),
        ('QUEDA REAL: direta', dict(BASE, tend_abs=True)),
        ('QUEDA REAL: raso', dict(BASE, tend_abs=True, modo='raso')),
        ('QUEDA REAL: raso+volume', dict(BASE, tend_abs=True, modo='raso',
                                         vol_min=1.2)),
        ('QUEDA REAL: raso+duas velas', dict(BASE, tend_abs=True,
                                             modo='raso', vol_min=0.0)),
        ('fundo mais alto', dict(BASE, modo='fundo_alto')),
        ('espera só 6 velas de 4h', dict(BASE, gat_h4=6)),
        ('espera até 24 velas de 4h', dict(BASE, gat_h4=24)),
    ]
    # entrada igual ao padrao e valido: o encosto e o gatilho sao lidos
    # na propria vela do padrao, como no setup que ja roda no bot
    pares_tf = [(p_, e_) for p_ in [int(x) for x in a.padrao.split(',')]
                for e_ in [int(x) for x in a.entrada.split(',')] if e_ <= p_]
    for tfp, tfe in pares_tf:
        guardado = {}
        print(f"\n{'#'*120}\n#  PADRÃO EM H{tfp}, ENTRADA EM H{tfe}\n"
              f"{'#'*120}")
        print(f"\n{'='*120}\n  TODAS AS MOEDAS\n{'='*120}")
        cab()
        for rot, cfg in VAR:
            ops = rodar(cru, dict(cfg, tfp=tfp), faixa, tfe, tfp)
            guardado[rot] = ops
            painel(rot, ops)
        if a.faixas > 1:
            for i_ in range(a.faixas):
                print(f"\n  {rot_f[i_].upper()}")
                cab()
                for rot, _ in VAR:
                    painel(rot, [o for o in guardado[rot]
                                 if o['faixa'] == i_])
        if a.blocos:
            cortes = [int(x) for x in a.blocos.split(',')]
            print(f"\n{'~'*120}\n  POR BLOCO DO RANKING DE VOLUME "
                  f"(exclusivos)\n{'~'*120}")
            ant = 0
            for c in cortes + [len(cru)]:
                nomes = {s for s, _, _ in cru[ant:c]}
                if nomes:
                    print(f"\n  posições {ant+1} a {min(c, len(cru))} "
                          f"({len(nomes)} moedas)")
                    cab()
                    for rot, _ in VAR:
                        painel(rot, [o for o in guardado[rot]
                                     if o['sim'] in nomes])
                ant = c
            print(f"\n{'~'*120}\n  ACUMULADO: AS N MAIORES\n{'~'*120}")
            for c in cortes + [len(cru)]:
                nomes = {s for s, _, _ in cru[:c]}
                print(f"\n  as {min(c, len(cru))} maiores")
                cab()
                for rot, _ in VAR:
                    painel(rot, [o for o in guardado[rot]
                                 if o['sim'] in nomes])


if __name__ == '__main__':
    main()
