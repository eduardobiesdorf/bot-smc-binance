# -*- coding: utf-8 -*-
import time
import requests

ATIVOS = [
    'UNIUSDT', 'SHIBUSDT', 'NEARUSDT', 'BTCUSDT', 
    'POLUSDT', 'BCHUSDT', 'ADAUSDT', 'DOTUSDT', 'LINKUSDT'
]

def identificar_swing_points(candles, lookback=12):
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]
    return max(highs[-lookback:]), min(lows[-lookback:])

def buscar_candles(base_url, simbolo, interval='4h', total_velas=100):
    params = {'symbol': simbolo, 'interval': interval, 'limit': total_velas}
    r = requests.get(f"{base_url}/klines", params=params, timeout=15)
    if r.ok:
        return r.json()
    return []

def executar_backtest_7_dias():
    print("=== BACKTEST RECENTE (7 DIAS | CESTA DE ELITE 9 ATIVOS) ===")
    base_url = "https://data-api.binance.vision/api/v3"
    
    total_sinais = 0
    total_ativados = 0
    total_wins = 0
    total_loss = 0
    soma_rr = 0

    for simbolo_par in ATIVOS:
        simbolo_fmt = simbolo_par.replace('USDT', '/USDT')
        try:
            candles = buscar_candles(base_url, simbolo_par, interval='4h', total_velas=100)
            if not candles or len(candles) < 50:
                continue

            sinais_ativo = 0
            ativados_ativo = 0
            wins_ativo = 0
            loss_ativo = 0
            soma_rr_ativo = 0

            # Analisa apenas as últimas ~42 velas (equivalente a 7 dias em H4)
            inicio_analise = max(35, len(candles) - 45)

            for i in range(inicio_analise, len(candles) - 1):
                vela = candles[i]
                t_open = float(vela[1])
                t_high = float(vela[2])
                t_low = float(vela[3])
                t_close = float(vela[4])

                corpo = abs(t_close - t_open)
                tamanho_total = t_high - t_low
                
                if tamanho_total == 0 or (corpo / tamanho_total) <= 0.4:
                    continue
                    
                is_bullish = t_close > t_open
                is_bearish = t_close < t_open

                sub_candles = candles[i-12:i]
                macro_high, macro_low = identificar_swing_points(sub_candles, lookback=12)
                
                is_choch_bullish = is_bullish and t_close > macro_high
                is_choch_bearish = is_bearish and t_close < macro_low

                if not (is_choch_bullish or is_choch_bearish):
                    continue

                sinais_ativo += 1
                total_sinais += 1

                ob_vela = None
                for k in range(i-1, max(0, i-8), -1):
                    c_op = float(candles[k][1])
                    c_cl = float(candles[k][4])
                    if is_choch_bullish and c_cl < c_op:
                        ob_vela = candles[k]
                        break
                    elif is_choch_bearish and c_cl > c_op:
                        ob_vela = candles[k]
                        break
                
                if ob_vela is None:
                    ob_vela = vela

                ob_high = float(ob_vela[2])
                ob_low = float(ob_vela[3])

                if is_choch_bullish:
                    entrada = ob_low
                    stop_loss = ob_low - (ob_high - ob_low) * 1.05
                    take_profit = macro_high
                    is_buy = True
                else:
                    entrada = ob_high
                    stop_loss = ob_high + (ob_high - ob_low) * 1.05
                    take_profit = macro_low
                    is_buy = False

                if is_buy and t_close >= take_profit:
                    continue
                if not is_buy and t_close <= take_profit:
                    continue

                risco = abs(entrada - stop_loss)
                retorno = abs(take_profit - entrada)
                rr = retorno / risco if risco > 0 else 0

                if rr < 1.20:
                    continue

                ativado = False
                desfecho = None

                for j in range(i + 1, len(candles)):
                    fut_high = float(candles[j][2])
                    fut_low = float(candles[j][3])

                    if not ativado:
                        if is_buy and fut_low <= entrada:
                            ativado = True
                        elif not is_buy and fut_high >= entrada:
                            ativado = True

                    if ativado:
                        if is_buy:
                            if fut_low <= stop_loss:
                                desfecho = 'loss'
                                break
                            elif fut_high >= take_profit:
                                desfecho = 'win'
                                break
                        else:
                            if fut_high >= stop_loss:
                                desfecho = 'loss'
                                break
                            elif fut_low <= take_profit:
                                desfecho = 'win'
                                break

                if ativado:
                    ativados_ativo += 1
                    total_ativados += 1
                    soma_rr_ativo += rr
                    soma_rr += rr
                    if desfecho == 'win':
                        wins_ativo += 1
                        total_wins += 1
                    elif desfecho == 'loss':
                        loss_ativo += 1
                        total_loss += 1

            win_rate = (wins_ativo / ativados_ativo * 100) if ativados_ativo > 0 else 0
            rr_medio = (soma_rr_ativo / ativados_ativo) if ativados_ativo > 0 else 0
            print(f"[{simbolo_fmt}] Sinais: {sinais_ativo} | Ativados: {ativados_ativo} | Wins: {wins_ativo} | Loss: {loss_ativo} | Win Rate: {win_rate:.1f}% | R:R: 1:{rr_medio:.2f}")
            time.sleep(0.05)

        except Exception as e:
            print(f"Erro em {simbolo_par}: {e}")

    print("\n=== RESUMO DOS ÚLTIMOS 7 DIAS ===")
    print(f"Sinais Identificados: {total_sinais} | Ordens Ativadas: {total_ativados}")
    if total_ativados > 0:
        wr_global = (total_wins / total_ativados) * 100
        rr_global = soma_rr / total_ativados
        print(f"Wins: {total_wins} | Losses: {total_loss} | Win Rate Global: {wr_global:.2f}% | R:R Médio: 1:{rr_global:.2f}")

if __name__ == "__main__":
    executar_backtest_7_dias()
