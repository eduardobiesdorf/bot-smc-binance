# -*- coding: utf-8 -*-
import time
import requests
from datetime import datetime, timezone, timedelta

# Os 8 ativos selecionados para o foco cirúrgico
ATIVOS_SELECIONADOS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT',
    'LINKUSDT', 'AVAXUSDT', 'DOGEUSDT', 'NEARUSDT'
]

def identificar_swing_points(candles, lookback=32):
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]
    return max(highs[-lookback:]), min(lows[-lookback:])

def buscar_candles_historicos(base_url, simbolo, interval='1h', total_velas=2160):
    candles = []
    end_time = None
    
    while len(candles) < total_velas:
        params = {'symbol': simbolo, 'interval': interval, 'limit': 1000}
        if end_time:
            params['endTime'] = end_time
            
        r = requests.get(f"{base_url}/klines", params=params, timeout=15)
        if not r.ok:
            break
        
        lote = r.json()
        if not lote:
            break
            
        candles = lote + candles
        end_time = lote[0][0] - 1
        time.sleep(0.05)
        
    return candles[-total_velas:]

def executar_backtest_8_ativos():
    print("=== BACKTEST H1 (3 MESES - 8 ATIVOS | FILTRO: 08H ÀS 20H) ===")
    base_url = "https://data-api.binance.vision/api/v3"
    
    t_sinais, t_ativados, t_wins, t_losses, t_soma_rr = 0, 0, 0, 0, 0

    for idx, simbolo_par in enumerate(ATIVOS_SELECIONADOS, 1):
        simbolo_fmt = simbolo_par.replace('USDT', '/USDT')
        candles = buscar_candles_historicos(base_url, simbolo_par, interval='1h', total_velas=2160)
        
        if not candles or len(candles) < 100:
            print(f"{idx:02d}. [{simbolo_fmt}] Dados insuficientes.")
            continue

        sinais_ativo = 0
        ativados_ativo = 0
        wins_ativo = 0
        losses_ativo = 0
        soma_rr_ativo = 0

        for i in range(35, len(candles) - 1):
            subset = candles[:i+1]
            vela_fechada = subset[-2]
            
            # FILTRO DE HORÁRIO: Converte o timestamp da Binance para a hora (UTC ou ajuste local)
            # O timestamp da vela está em milissegundos no índice 0
            timestamp_ms = int(vela_fechada[0])
            dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
            
            # Se quiseres ajustar para o fuso horário de Brasília (UTC-3), descomenta a linha abaixo:
            dt_local = dt - timedelta(hours=3)
            hora_vela = dt_local.hour

            # Filtra estritamente entre 08:00 e 20:00 (8h às 20h)
            if not (8 <= hora_vela < 20):
                continue

            t_open = float(vela_fechada[1])
            t_high = float(vela_fechada[2])
            t_low = float(vela_fechada[3])
            t_close = float(vela_fechada[4])

            corpo = abs(t_close - t_open)
            tamanho_total = t_high - t_low
            
            if tamanho_total == 0 or (corpo / tamanho_total) <= 0.4:
                continue
                
            is_bullish = t_close > t_open
            is_bearish = t_close < t_open

            sub_candles = subset[-34:-2]
            macro_high, macro_low = identificar_swing_points(sub_candles, lookback=32)
            
            is_choch_bullish = is_bullish and t_close > macro_high
            is_choch_bearish = is_bearish and t_close < macro_low

            if not (is_choch_bullish or is_choch_bearish):
                continue

            # Localização exata do Order Block
            ob_vela = None
            for k in range(len(subset) - 3, max(0, len(subset) - 12), -1):
                c_op = float(subset[k][1])
                c_cl = float(subset[k][4])
                if is_choch_bullish and c_cl < c_op:
                    ob_vela = subset[k]
                    break
                elif is_choch_bearish and c_cl > c_op:
                    ob_vela = subset[k]
                    break
            
            if ob_vela is None:
                ob_vela = vela_fechada

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

            # Validação anti-alvos mortos
            if is_buy and t_close <= take_profit:
                continue
            if not is_buy and t_close >= take_profit:
                continue

            sinais_ativo += 1

            risco = abs(entrada - stop_loss)
            retorno = abs(take_profit - entrada)
            rr = retorno / risco if risco > 0 else 0

            # Filtro de sanidade de R:R (mínimo 1:1.30)
            if rr < 1.30:
                continue

            # Simulação do trade nas velas futuras (janela de até 48 horas)
            ativou = False
            venceu = False
            perdeu = False

            for f_idx in range(i + 1, min(len(candles), i + 49)):
                f_high = float(candles[f_idx][2])
                f_low = float(candles[f_idx][3])

                if not ativou:
                    if is_buy and f_low <= entrada:
                        ativou = True
                    elif not is_buy and f_high >= entrada:
                        ativou = True

                if ativou:
                    if is_buy:
                        if f_low <= stop_loss:
                            perdeu = True
                            break
                        if f_high >= take_profit:
                            venceu = True
                            break
                    else:
                        if f_high >= stop_loss:
                            perdeu = True
                            break
                        if f_low <= take_profit:
                            venceu = True
                            break

            if ativou:
                ativados_ativo += 1
                soma_rr_ativo += rr
                if venceu:
                    wins_ativo += 1
                else:
                    losses_ativo += 1

        t_sinais += sinais_ativo
        t_ativados += ativados_ativo
        t_wins += wins_ativo
        t_losses += losses_ativo
        t_soma_rr += soma_rr_ativo

        win_rate_ativo = (wins_ativo / ativados_ativo * 100) if ativados_ativo > 0 else 0
        media_rr_ativo = (soma_rr_ativo / ativados_ativo) if ativados_ativo > 0 else 0

        print(f"{idx:02d}. [{simbolo_fmt}] Sinais (8h-20h): {sinais_ativo} | Ativados: {ativados_ativo} | Wins: {wins_ativo}, Loss: {losses_ativo} | Win Rate: {win_rate_ativo:.1f}% | Média R:R: 1:{media_rr_ativo:.2f}")

    global_wr = (t_wins / t_ativados * 100) if t_ativados > 0 else 0
    global_rr = (t_soma_rr / t_ativados) if t_ativados > 0 else 1.0

    print("\n" + "="*50)
    print("=== RELATÓRIO FINAL (8 ATIVOS | 08H ÀS 20H) ===")
    print(f"Total de Sinais Identificados: {t_sinais}")
    print(f"Ordens Ativadas: {t_ativados}")
    print(f"Wins: {t_wins} | Losses: {t_losses}")
    print(f"Win Rate Global: {global_wr:.2f}%")
    print(f"Média R:R Global: 1:{global_rr:.2f}")
    print("="*50)

if __name__ == "__main__":
    executar_backtest_8_ativos()
