"""SETUP 5 -- rompimento falso com retorno a lateralidade. Em H1.

A configuracao que o Eduardo descreveu:

  1. LATERALIDADE  -- faixa estreita por ~30 velas de H1
  2. A IDA         -- fecha para fora da faixa e segue algumas velas,
                      com o VOLUME SUBINDO
  3. FORCA CONTRARIA -- uma vela grande CONTRA o movimento. O alerta
  4. FALHA DE CONTINUIDADE -- tenta retomar e NAO faz nova maxima
  5. A VOLTA       -- fecha de volta para DENTRO da faixa. A entrada
  6. O ALVO        -- o outro lado da faixa, o ultimo fundo/topo deixado
                      Stop acima da maxima da ida.

No caso de alta: rompe para cima, falha, volta -> VENDE buscando o
fundo da faixa. O espelho para baixo.

Uso:  python3 setup5_falha.py <pasta> [--tf 1] [--desenhar 3]
"""
import argparse, glob, os, statistics, sys
import datetime as dt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8
import bot_varredura as bot
from explosao import ler, RISCO, TAXA, FUND8

BRT = dt.timezone(dt.timedelta(hours=-3))

CFG5 = dict(
    lat_jan=60,        # velas da lateralidade. 150 velas (6 dias) perdeu nas OITO
                       # combinacoes testadas, de -18 a -26 por operacao; 30 velas
                       # nao e faixa, e ruido. O ponto doce e 60 velas = 2,5 dias
    aperto=0.70,       # o quanto a faixa e mais estreita que o normal.
                       # Uma janela de L velas anda ~raiz(L) volatilidades por
                       # natureza: 5.5 em 30 velas, 12.2 em 150. Entao o limite e
                       # aperto*raiz(L) volatilidades -- escala sozinho com a
                       # janela. Medir em volatilidades fixas nao funciona: 2.5
                       # deixou passar 1 ocorrencia em 83 meses, 5.0 nao filtrou nada
    deriva_max=0.35,   # a deriva da faixa (10 primeiros fechamentos x 10 ultimos),
                       # medida na altura dela. Sem isto, TENDENCIA entra como faixa
    toques_div=18,     # cruzamentos minimos do meio da faixa = L/18, no minimo 3.
                       # Faixa de verdade oscila; tendencia atravessa uma vez so
    ida_max=24,        # ate quantas velas a ida pode durar
    ida_min=2,         # e pelo menos quantas
    ida_min_alt=0.25,  # o quanto a ida tem de ANDAR para fora da faixa, medido
                       # na altura dela. Sem isto, um pavio de 3 velas vira sweep
    vol_sobe=1.3,      # volume medio da ida / volume medio da lateralidade
    forca_sigma=2.0,   # a vela contraria, em volatilidades
    forca_corpo=0.5,
    forca_apos=99,     # quantas velas a forca contraria pode chegar DEPOIS da
                       # maxima da ida. No CELO ela veio 2 velas depois do topo
                       # (risco 3.98%); no ZEN, 25 velas depois, quando o
                       # movimento ja tinha falhado sozinho e o stop ficou la em
                       # cima (risco 5.80%). Ela e o ALERTA: tem de avisar na
                       # hora. 99 = sem trava, como estava
    falha_max=16,      # velas para a falha e a volta acontecerem
    entrada_em='volta',# ONDE entrar. O Eduardo: 'quero uma minima confirmacao
                       # que o preco esta revertendo'. Quatro gatilhos com
                       # confirmacao, mais um controle sem nenhuma:
                       #   'volta'     fecha de volta dentro da faixa (original;
                       #               no ZEN entrou na metade, R:R 1:1.34)
                       #   'falha'     perde o extremo da propria vela de forca
                       #   'impulso'   vem uma SEGUNDA vela de forca contraria
                       #   'estrutura' fecha alem da minima da IDA inteira
                       #   'forca'     sem confirmacao -- so controle
    stop_em='extremo', # 'extremo' = acima da maxima da IDA INTEIRA; 'forca' = so
                       # acima da VELA DE FORCA. Eu previ que 'forca' era a chave:
                       # dobrou as operacoes e subiu o R:R de 1:1.85 para 1:2.49,
                       # mas CORTOU o dinheiro por operacao pela metade
                       # (+8.93 -> +3.28). Errei; fica no extremo
    alvo_em='piscina', # 'piscina' = o ultimo topo/fundo NAO CONSUMIDO acima
                       # (ou abaixo) de TODA a faixa antiga, que e o alvo que o
                       # Eduardo descreveu e nao tem parametro meu nenhum dentro.
                       # 'frac' usa alvo_frac abaixo
    alvo_frac=1.0,     # so com alvo_em='frac': quanto da faixa o alvo atravessa.
                       # 1.0 = a borda oposta, 0.5 = o meio da faixa
    pre_jan=300,       # velas de historico ANTES da faixa, onde se procura o topo
                       # ou fundo anterior que a faixa rompeu
    pre_pivo=10,       # quantas velas de cada lado definem o pivo. 'Mais
                       # expressivo' e isto -- um topo que e o mais alto de 21
                       # velas --, nao a maxima absoluta da janela
    pre_folga=0.0,     # o quanto a faixa tem de estar LIMPA do nivel rompido,
                       # medido na altura dela. 0.0 = so nao pode encostar
    pre_modo='off',    # o contexto, pedido pelo Eduardo: a faixa aconteceu DEPOIS
                       # de romper um topo/fundo anterior mais expressivo?
                       #   'off'       -- sem filtro
                       #   'qualquer'  -- exige contexto, de qualquer lado
                       #   'alinhado'  -- faixa acima de topo rompido (contexto
                       #                  comprador) e o rompimento falso e para
                       #                  BAIXO, entao a compra vem A FAVOR dele.
                       #                  E o espelho
                       #   'contra'    -- o inverso, para servir de controle
    stop_folga=0.15,
    rr_min=1.2,
)


def achar(h, cfg=None, a=None, mv=None):
    cfg = cfg or CFG5
    L = cfg['lat_jan']
    if len(h) < L + 60:
        return []
    if a is None:
        a, mv = e8.atr(h, 14), e8.medvol(h, 20)
    # a faixa tem de ser mais estreita que o passeio normal de L velas
    teto = cfg['aperto'] * (L ** 0.5)
    cruz_min = max(3, round(L / cfg['toques_div']))
    out, i = [], L + 20
    while i < len(h) - 4:
        if a[i-1] <= 0 or mv[i-1] <= 0:
            i += 1; continue
        faixa = h[i-L:i]
        topo = max(x[2] for x in faixa)
        base = min(x[3] for x in faixa)
        alt = topo - base
        # 1) a lateralidade tem de ser ESTREITA, SEM DERIVA e OSCILANTE
        if alt <= 0 or alt > teto*a[i-1]:
            i += 1; continue
        ini = statistics.mean(x[4] for x in faixa[:10])
        fim_ = statistics.mean(x[4] for x in faixa[-10:])
        if abs(fim_ - ini)/alt > cfg['deriva_max']:
            i += 1; continue           # isto aqui e tendencia, nao faixa
        meio = (topo + base)/2
        cruz = sum(1 for n in range(1, L)
                   if (faixa[n-1][4] - meio)*(faixa[n][4] - meio) < 0)
        if cruz < cruz_min:
            i += 1; continue           # atravessou uma vez so: tendencia
        # 1b) O CONTEXTO: a faixa esta em cima de um topo rompido, ou embaixo
        # de um fundo rompido? Olha o historico ANTES da faixa e exige que ela
        # esteja inteira do outro lado do nivel, limpa dele.
        # Tem de ser um PIVO, nao o extremo da janela: exigir que a faixa fique
        # acima da maxima absoluta de 300 velas nunca acontece, e foi por isso
        # que a primeira versao deste filtro deu zero ocorrencia em 83 meses.
        ctx = None
        q = cfg['pre_pivo']
        p0, p1 = max(q, i - L - cfg['pre_jan']), i - L - q
        if p1 > p0 + 20:
            for k in range(p0, p1):
                if ctx:
                    break
                alto = all(h[k][2] >= h[k-m][2] and h[k][2] >= h[k+m][2]
                           for m in range(1, q+1))
                if alto and base > h[k][2] + cfg['pre_folga']*alt:
                    ctx = 'alta'       # acumulando acima de resistencia virada
                    continue
                baixo = all(h[k][3] <= h[k-m][3] and h[k][3] <= h[k+m][3]
                            for m in range(1, q+1))
                if baixo and topo < h[k][3] - cfg['pre_folga']*alt:
                    ctx = 'baixa'      # distribuindo abaixo de suporte perdido
        if cfg['pre_modo'] != 'off' and ctx is None:
            i += 1; continue
        cl = h[i][4]
        # 2) a ida: fecha para fora da faixa
        if cl > topo:
            alta = True
        elif cl < base:
            alta = False
        else:
            i += 1; continue
        # faixa acima de topo rompido + rompimento falso para BAIXO = a compra
        # vem a favor do contexto. 'alta' aqui e a direcao da IDA, e o trade e
        # o contrario dela
        alinhado = (ctx == 'alta' and not alta) or (ctx == 'baixa' and alta)
        if cfg['pre_modo'] == 'alinhado' and not alinhado:
            i += 1; continue
        if cfg['pre_modo'] == 'contra' and alinhado:
            i += 1; continue
        vol_lat = statistics.mean(x[5] for x in faixa)
        # segue a ida ate a vela de forca contraria
        ext = h[i][2] if alta else h[i][3]
        k_ext = i
        k_forca = None
        for k in range(i+1, min(i+1+cfg['ida_max'], len(h))):
            hk, lk, ok, ck = h[k][2], h[k][3], h[k][1], h[k][4]
            rk = hk - lk
            if (hk > ext) if alta else (lk < ext):
                ext, k_ext = (hk if alta else lk), k
            if k - i < cfg['ida_min']:
                continue
            # 3) a vela de forca CONTRARIA
            if rk > 0 and rk >= cfg['forca_sigma']*a[k-1] \
                    and abs(ck-ok)/rk >= cfg['forca_corpo'] \
                    and ((ck < ok) if alta else (ck > ok)) \
                    and k - k_ext <= cfg['forca_apos']:
                k_forca = k
                break
        if k_forca is None:
            i += 1; continue
        # 2b) a ida tem de ANDAR para fora da faixa, nao ser um pavio
        excur = (ext - topo) if alta else (base - ext)
        if excur/alt < cfg['ida_min_alt']:
            i += 1; continue
        vol_ida = statistics.mean(x[5] for x in h[i:k_forca+1])
        # 2b) o volume da ida tem de ser MAIOR que o da lateralidade
        if vol_lat <= 0 or vol_ida/vol_lat < cfg['vol_sobe']:
            i += 1; continue
        # 4) a falha de continuidade, e ONDE entrar nela. Todos os modos abaixo
        # exigem pelo menos UMA confirmacao de que o preco virou, menos 'forca',
        # que fica so como controle para mostrar que sem confirmacao e pior:
        #   'volta'      -- fecha de volta DENTRO da faixa. O original; no ZEN
        #                   entrou com metade do movimento ja andado
        #   'falha'      -- perde o extremo da PROPRIA vela de forca
        #   'impulso'    -- vem uma SEGUNDA vela de forca contra o movimento.
        #                   O gatilho de impulsao
        #   'estrutura'  -- fecha abaixo da MINIMA DA IDA inteira: o movimento
        #                   perdeu a propria estrutura. A confirmacao mais dura
        #   'forca'      -- no fechamento da vela de forca, sem confirmacao
        # Nos quatro primeiros a maxima da ida nao pode ser superada: se superar,
        # nao houve falha e a operacao nao existe.
        modo = cfg['entrada_em']
        estr = min(x[3] for x in h[i:k_forca+1]) if alta else \
               max(x[2] for x in h[i:k_forca+1])
        ent_k = None
        if modo == 'forca':
            ent_k = k_forca
        else:
            for k in range(k_forca+1, min(k_forca+1+cfg['falha_max'], len(h))):
                ok, hk, lk, ck = h[k][1], h[k][2], h[k][3], h[k][4]
                if (hk > ext) if alta else (lk < ext):
                    break                  # retomou: nao houve falha
                if modo == 'falha':
                    if (ck < h[k_forca][3]) if alta else (ck > h[k_forca][2]):
                        ent_k = k          # perdeu o extremo da vela de forca
                        break
                elif modo == 'impulso':
                    rk = hk - lk
                    if rk > 0 and rk >= cfg['forca_sigma']*a[k-1] \
                            and abs(ck-ok)/rk >= cfg['forca_corpo'] \
                            and ((ck < ok) if alta else (ck > ok)):
                        ent_k = k          # segunda forca: impulsao confirmada
                        break
                elif modo == 'estrutura':
                    if (ck < estr) if alta else (ck > estr):
                        ent_k = k          # perdeu a estrutura da propria ida
                        break
                elif (ck < topo) if alta else (ck > base):
                    ent_k = k              # voltou para dentro da faixa
                    break
        if ent_k is None:
            i += 1; continue
        ent = h[ent_k][4]
        # o STOP: no extremo da ida inteira, ou so no extremo da VELA DE FORCA.
        # A vela de forca E o alerta -- medir nela e o equivalente ao furo raso
        # do setup 1: a estrutura que disparou, nao a perna toda
        base_stop = ext if cfg['stop_em'] == 'extremo' else \
                    (h[k_forca][2] if alta else h[k_forca][3])
        stop = base_stop + a[ent_k]*cfg['stop_folga'] if alta else \
               base_stop - a[ent_k]*cfg['stop_folga']
        if (stop <= ent) if alta else (stop >= ent):
            i += 1; continue               # a forca ja fechou abaixo da entrada
        # o ALVO. 'piscina' e o que o Eduardo pediu: numa compra, o ultimo
        # topo nao consumido ACIMA DE TODA a faixa antiga -- medido a partir
        # da BORDA da faixa, nao da entrada, para garantir que fique acima da
        # lateralidade inteira. Zero parametro meu para escolher.
        if cfg['alvo_em'] == 'piscina':
            borda = base if alta else topo
            d = bot.piscina(h, ent_k, alta, borda, min(len(h), L*2))
            if d is None:
                i += 1; continue           # sem liquidez parada: sem alvo
            alvo = borda - d if alta else borda + d
        else:
            f = cfg['alvo_frac']
            alvo = (topo - f*alt) if alta else (base + f*alt)
        risco = abs(ent-stop)
        dist = (ent-alvo) if alta else (alvo-ent)
        if risco <= 0 or dist <= 0 or dist/risco < cfg['rr_min']:
            i += 1; continue
        out.append(dict(lado='venda' if alta else 'compra', i=i,
                        topo=topo, base=base, ext=ext, k_forca=k_forca,
                        idx=ent_k, entrada=ent, stop=stop, alvo=alvo,
                        rr=dist/risco, risco_pct=risco/ent*100,
                        vol_x=vol_ida/vol_lat, vela_ms=h[ent_k][0],
                        apos=k_forca-k_ext,
                        lat_atr=alt/a[i-1], excur=excur/alt, cruz=cruz,
                        ctx=ctx, alinhado=alinhado))
        i = ent_k + 1
    return out


def resolver(h, g, tf, limite=240):
    """Leva a operacao ate o alvo ou o stop. Risco fixo de $100 na conta."""
    venda = g['lado'] == 'venda'
    k = g['idx']
    for m in range(k+1, min(k+1+limite, len(h))):
        hi, lo = h[m][2], h[m][3]
        bate_stop = (hi >= g['stop']) if venda else (lo <= g['stop'])
        bate_alvo = (lo <= g['alvo']) if venda else (hi >= g['alvo'])
        if bate_stop and bate_alvo:
            bate_alvo = False               # o pior caso: assume o stop
        if bate_stop or bate_alvo:
            saida = g['stop'] if bate_stop else g['alvo']
            pos = RISCO / (g['risco_pct']/100)      # tamanho da posicao em $
            mov = (g['entrada'] - saida)/g['entrada'] if venda else \
                  (saida - g['entrada'])/g['entrada']
            bruto = pos * mov
            horas = (m - k) * tf
            custo = pos*TAXA*2 + pos*FUND8*(horas/8)
            return dict(fim='alvo' if bate_alvo else 'stop', bruto=bruto,
                        liq=bruto-custo, horas=horas, k_fim=m)
    return None


def desenhar(sim, h, g, tf, caminho):
    cfg = CFG5
    venda = g['lado'] == 'venda'
    i, kf, k = g['i'], g['k_forca'], g['idx']
    fim = None
    for m in range(k+1, min(k+1+120, len(h))):
        hi, lo = h[m][2], h[m][3]
        if venda:
            if hi >= g['stop']: fim = ('stop', m); break
            if lo <= g['alvo']: fim = ('alvo', m); break
        else:
            if lo <= g['stop']: fim = ('stop', m); break
            if hi >= g['alvo']: fim = ('alvo', m); break
    m_fim = fim[1] if fim else min(k+30, len(h)-1)
    a0 = max(0, i - cfg['lat_jan'] - 4)
    a1 = min(len(h), m_fim + 5)
    vel = h[a0:a1]
    d = lambda x: x - a0
    t = f"{g['entrada']:.10f}".rstrip('0')
    c = max(2, min(len(t.split('.')[1]) if '.' in t else 0, 8))

    fig, (ax, axv) = plt.subplots(2, 1, figsize=(15, 9), sharex=True,
                                  gridspec_kw={'height_ratios': [4, 1]},
                                  facecolor='#13161b')
    for A in (ax, axv):
        A.set_facecolor('#13161b')
        A.tick_params(colors='#6b7280', labelsize=8)
        for s_ in A.spines.values():
            s_.set_color('#2a2f38')
        A.grid(color='#1e232b', linewidth=.6)

    ax.add_patch(Rectangle((d(i-cfg['lat_jan'])-0.5, g['base']),
                           a1-a0-d(i-cfg['lat_jan']), g['topo']-g['base'],
                           facecolor='#42a5f5', alpha=.10, zorder=0))
    ax.annotate(f"a lateralidade ({g['lat_atr']:.1f} volatilidades de altura)",
                ((d(i-cfg['lat_jan'])+d(i))/2, g['topo']),
                color='#64b5f6', fontsize=10, ha='center',
                xytext=(0, 8), textcoords='offset points')
    for n, v in enumerate(vel):
        o, hi, lo, cl = v[1], v[2], v[3], v[4]
        cor = '#26a69a' if cl >= o else '#ef5350'
        ax.plot([n, n], [lo, hi], color=cor, linewidth=1.1, zorder=3)
        ax.add_patch(Rectangle((n-0.34, min(o, cl)), 0.68,
                               max(abs(cl-o), (hi-lo)*0.004),
                               facecolor=cor, edgecolor=cor, zorder=4))
        axv.bar(n, v[5], color=cor, width=0.68, alpha=.85)
    mvv = e8.medvol(h, 20)
    axv.plot(range(len(vel)), [mvv[a0+n] for n in range(len(vel))],
             color='#ffd54f', linewidth=1.2)
    axv.set_ylabel('volume', color='#9aa3ae', fontsize=9)

    ax.axvspan(d(i)-0.5, d(kf)+0.5, color='#ffd54f', alpha=.10, zorder=1)
    ax.annotate(f"a ida ({g['vol_x']:.1f}x o volume da faixa)",
                ((d(i)+d(kf))/2, g['ext']), color='#ffd54f', fontsize=10,
                ha='center', xytext=(0, 14 if venda else -24),
                textcoords='offset points')
    ax.axvspan(d(kf)-0.5, d(kf)+0.5, color='#ab47bc', alpha=.28, zorder=2)
    ax.annotate('a força contrária', (d(kf), h[kf][3] if venda else h[kf][2]),
                color='#ce93d8', fontsize=10, ha='center',
                xytext=(0, -24 if venda else 16), textcoords='offset points')
    ax.axvline(d(k), color='#ffffff', linewidth=1.0, alpha=.35,
               linestyle='--', zorder=2)
    ax.annotate('a volta: entrada', (d(k), g['entrada']), color='#ffffff',
                fontsize=9.5, ha='center', xytext=(0, 14),
                textcoords='offset points')
    for y, cor, rot in (
            (g['entrada'], '#ffffff', f"entrada  {g['entrada']:,.{c}f}"),
            (g['stop'], '#ef5350', f"stop  {g['stop']:,.{c}f}   "
                                   f"({g['risco_pct']:.2f}% de risco)"),
            (g['alvo'], '#26a69a',
             f"alvo  {g['alvo']:,.{c}f}   "
             f"(a piscina: o último {'fundo' if venda else 'topo'} não "
             f"consumido {'abaixo' if venda else 'acima'} de toda a faixa)"
             if CFG5['alvo_em'] == 'piscina' else
             f"alvo  {g['alvo']:,.{c}f}   "
             f"(o {'fundo' if venda else 'topo'} da faixa)")):
        ax.axhline(y, color=cor, linewidth=1.2, alpha=.92, zorder=6)
        ax.annotate(rot, (len(vel)-1, y), color=cor, fontsize=9,
                    xytext=(8, 0), textcoords='offset points', va='center')

    cara = {'alvo': '✓ bateu o alvo', 'stop': '✗ bateu o stop'}.get(
        fim[0] if fim else '', '• não resolveu')
    q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
    ax.set_title(f"{sim.replace('USDT','')}  ·  rompimento falso e volta à "
                 f"faixa  ·  velas de {tf}h  ·  {q:%d/%m/%Y %H:%M} "
                 f"(Brasília)  ·  {g['lado']}  ·  R:R 1:{g['rr']:.2f}  ·  "
                 f"{cara}", color='#e8eaed', fontsize=12.5, pad=14)
    ax.set_xlim(-1, len(vel) + 20)
    fig.tight_layout()
    fig.savefig(caminho, dpi=115, facecolor='#13161b')
    plt.close(fig)
    return fim[0] if fim else 'aberta'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--tf', type=int, default=1)
    ap.add_argument('--n', type=int, default=150)
    ap.add_argument('--desenhar', type=int, default=3)
    ap.add_argument('--varrer', type=int, default=1)
    ap.add_argument('--resultado', default='qualquer',
                    choices=['qualquer', 'alvo', 'stop'])
    a = ap.parse_args()
    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 2000:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h,
                        statistics.median(v[4]*v[5] for v in h)))
    cru.sort(key=lambda x: -x[2])
    cru = cru[:a.n]
    # o atr e o medvol sao a parte cara: calcula UMA vez por moeda
    pre = []
    for sim, h1, _ in cru:
        h = rev.juntar(h1, a.tf) if a.tf > 1 else h1
        pre.append((sim, h, e8.atr(h, 14), e8.medvol(h, 20)))
    meses = max(len(h) for _, h, _, _ in pre) / (24*30.4/a.tf)

    def rodar(cfg):
        ach = []
        for sim, h, at, mv in pre:
            for g in achar(h, cfg, at, mv):
                ach.append((sim, g, h))
        ach.sort(key=lambda x: x[1]['vela_ms'])
        return ach

    def resumo(ach, rotulo):
        res = [(s, g, resolver(h, g, a.tf)) for s, g, h in ach]
        res = [(s, g, r) for s, g, r in res if r]
        if not res:
            print(f"  {rotulo:<16} {len(ach):>5} ocorrências — nenhuma resolvida")
            return None
        alvo = sum(1 for _, _, r in res if r['fim'] == 'alvo')
        liq = sum(r['liq'] for _, _, r in res)
        bruto = sum(r['bruto'] for _, _, r in res)
        rrm = statistics.mean(g['rr'] for _, g, _ in res)
        hs = statistics.median(r['horas'] for _, _, r in res)
        pior, pico, atual, seq, pseq = 0, 0, 0, 0, 0
        for _, _, r in res:
            atual += r['liq']; pico = max(pico, atual)
            pior = min(pior, atual - pico)
            seq = seq + 1 if r['fim'] == 'stop' else 0
            pseq = max(pseq, seq)
        print(f"  {rotulo:<16} {len(res):>5} op {len(res)/meses:>5.1f}/mês "
              f"acerto {alvo/len(res)*100:>5.1f}%  R:R 1:{rrm:<4.2f} "
              f"{hs:>4.0f}h  bruto ${bruto:>9,.0f}  líquido ${liq:>9,.0f} "
              f"(${liq/len(res):>+7.2f}/op)  rebaix ${pior:>8,.0f}  "
              f"{pseq:>2} stops seguidos")
        return res

    if a.varrer:
        print(f"{len(cru)} maiores · velas de {a.tf}h · {meses:.0f} meses · "
              f"$100 de risco por operação\n")
        print("  JANELA DA LATERALIDADE (velas), com o aperto em "
              f"{CFG5['aperto']:.2f}x o passeio normal\n")
        for L in (30, 60, 100, 150, 200, 300):
            resumo(rodar(dict(CFG5, lat_jan=L)), f"{L} velas")
        print(f"\n  APERTO DA FAIXA, com a janela em {CFG5['lat_jan']} velas\n")
        for ap in (0.45, 0.55, 0.70, 0.85, 1.00):
            resumo(rodar(dict(CFG5, aperto=ap)),
                   f"{ap:.2f}x ({ap*CFG5['lat_jan']**0.5:.1f} vol)")
        print("\n  O CONTEXTO: a faixa veio DEPOIS de romper topo/fundo"
              " anterior?\n")
        for L in (60, 100):
            for pm in ('off', 'qualquer', 'alinhado', 'contra'):
                resumo(rodar(dict(CFG5, lat_jan=L, pre_modo=pm)),
                       f"{L}v {pm}")
        print("\n  TAMANHO DO PIVÔ anterior (velas de cada lado), alinhado\n")
        for pv in (5, 10, 20, 40):
            resumo(rodar(dict(CFG5, pre_modo='alinhado', pre_pivo=pv)),
                   f"pivô de {pv}")
        print("\n  FOLGA do nível rompido, alinhado\n")
        for pf in (0.0, 0.5, 1.0):
            resumo(rodar(dict(CFG5, pre_modo='alinhado', pre_folga=pf)),
                   f"folga {pf:.1f}x")
        print("\n  A FORÇA tem de chegar COLADA na máxima da ida?\n")
        for fa in (1, 2, 3, 5, 8, 99):
            resumo(rodar(dict(CFG5, forca_apos=fa)),
                   f"até {fa} velas depois" if fa < 99 else "sem trava")
        print("\n  O GATILHO DE ENTRADA  (o ZEN entrou na metade do"
              " movimento)\n")
        for me in ('volta', 'falha', 'impulso', 'estrutura', 'forca'):
            for fa in (3, 99):
                resumo(rodar(dict(CFG5, entrada_em=me, forca_apos=fa)),
                       f"{me} / força {fa}" if fa < 99 else f"{me} / livre")
        print()
    achados = rodar(CFG5)
    print(f"\nCONFIGURAÇÃO ESCOLHIDA: {CFG5['lat_jan']} velas de lateralidade, "
          f"aperto {CFG5['aperto']:.2f}")
    resumo(achados, 'escolhida')
    print()
    # desenha as ultimas que terminaram do jeito pedido (alvo, stop ou tanto faz)
    fila = []
    for sim, g, h in achados:
        if a.resultado != 'qualquer':
            r = resolver(h, g, a.tf)
            if not r or r['fim'] != a.resultado:
                continue
        fila.append((sim, g, h))
    print(f"  as {min(a.desenhar, len(fila))} últimas que terminaram em "
          f"{a.resultado} ({len(fila)} no total)\n")
    for k, (sim, g, h) in enumerate(fila[-a.desenhar:][::-1], 1):
        nome = f"setup5_{a.resultado}{k}_{sim}.png"
        r = desenhar(sim, h, g, a.tf, nome)
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        print(f"  {k}. {sim:<13} {q:%d/%m/%Y %H:%M}  {g['lado']:<6} "
              f"R:R 1:{g['rr']:.2f}  risco {g['risco_pct']:.2f}%  "
              f"faixa {g['lat_atr']:.1f} vol ({g['cruz']} cruz)  "
              f"volume {g['vol_x']:.1f}x  ida {g['excur']:.2f}x  "
              f"força {g['apos']} velas após a máxima  "
              f"→ {r}   ({nome})")


if __name__ == '__main__':
    main()
