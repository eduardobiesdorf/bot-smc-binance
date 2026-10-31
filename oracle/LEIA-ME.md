# Rodar o radar na Oracle Cloud

Por que sair do GitHub Actions: na conta gratuita o Actions atrasa de 25
a 45 minutos. Medido nos dados de 2026, entrar com 30 minutos de atraso
derruba o resultado de **+0,261R para +0,078R por operação**. Na Oracle o
cron dispara em segundos.

Tempo total: cerca de 40 minutos, a maior parte esperando o cadastro.

---

## 1. Criar a conta

1. Entre em **oracle.com/cloud/free** e clique em *Start for free*.
2. País: **Brasil**. Escolha a região **Brazil East (São Paulo)** ou
   **Brazil Southeast (Vinhedo)**.
   A região não muda depois, mas para esse uso não faz diferença.
3. Preencha os dados e confirme o e-mail.
4. **Cartão de crédito é obrigatório** — é só verificação de identidade.
   A Oracle faz uma autorização temporária de uns poucos reais, que o
   banco libera em 3 a 5 dias. Não vira cobrança.
   Cartão pré-pago, virtual ou de débito com senha **não** funciona.
5. O cadastro leva de 5 a 15 minutos para ser liberado.

> Depois de 30 dias o período de teste pago acaba, mas os recursos
> **Always Free** continuam funcionando. Não precisa fazer nada.

## 2. Criar a máquina

1. No menu (☰) vá em **Compute → Instances → Create instance**.
2. Nome: `radar`.
3. Em **Image and shape**, clique em *Edit*:
   - Imagem: **Canonical Ubuntu 24.04**
   - Shape: **VM.Standard.E2.1.Micro** (AMD) — procure a etiqueta
     **Always Free Eligible**.
   - A máquina ARM (Ampere A1) é mais potente, mas quase sempre está sem
     capacidade e o limite grátis caiu para 2 OCPU em agosto de 2026.
     A AMD basta: o script roda em menos de um minuto.
4. Em **Add SSH keys**, escolha **Generate a key pair for me** e clique
   em **Save private key**. Guarde esse arquivo — é a sua chave de
   acesso, não dá para baixar de novo.
5. Clique em **Create**. Em 1 ou 2 minutos aparece o **Public IP
   address**. Anote.

## 3. Conectar

No PowerShell do Windows, na pasta onde você salvou a chave:

```powershell
# só na primeira vez: trava as permissões da chave
icacls .\ssh-key.key /inheritance:r
icacls .\ssh-key.key /grant:r "$env:USERNAME:(R)"

ssh -i .\ssh-key.key ubuntu@SEU_IP_AQUI
```

Troque `ssh-key.key` pelo nome do arquivo e `SEU_IP_AQUI` pelo IP.
Na primeira conexão ele pergunta se confia na máquina: responda `yes`.

## 4. Instalar

Já conectado na máquina:

```bash
curl -sL https://raw.githubusercontent.com/eduardobiesdorf/bot-smc-binance/main/oracle/instalar.sh -o instalar.sh
bash instalar.sh
```

O script vai parar numa parte e mostrar uma chave começando com
`ssh-ed25519`. **Copie ela inteira** e cadastre no GitHub:

> github.com/eduardobiesdorf/bot-smc-binance
> → Settings → Deploy keys → Add deploy key
> Título: `oracle` — **não** marque *Allow write access*

Volte ao terminal e tecle ENTER. Ele pede o token e o chat ID do
Telegram, e termina sozinho.

> Se o repositório for privado, o `curl` acima não funciona. Nesse caso
> rode primeiro `nano instalar.sh`, cole o conteúdo do arquivo e salve
> com Ctrl+O, Enter, Ctrl+X.

## 5. Testar

```bash
~/bot-smc-binance/oracle/rodar.sh && tail -30 ~/radar.log
```

Deve listar os 20 pares e dizer quantos gatilhos achou. Para ver o
alerta chegando no Telegram mesmo sem gatilho novo:

```bash
source ~/.radar_env
cd ~/bot-smc-binance
.venv/bin/python bot_varredura.py --ping --exemplos 2
```

## 6. Desligar o GitHub Actions

Com a Oracle funcionando, o Actions só vai mandar alerta repetido.
No arquivo `.github/workflows/varredura.yml`, comente as três linhas de
cron:

```yaml
on:
  # schedule:
  #   - cron: '1 * * * *'
  #   - cron: '11 * * * *'
  #   - cron: '21 * * * *'
  workflow_dispatch:
```

O `workflow_dispatch` continua, então você ainda consegue rodar na mão
pelo site quando quiser.

---

## Manutenção

| o quê | comando |
|---|---|
| ver o log ao vivo | `tail -f ~/radar.log` |
| ver o agendamento | `crontab -l` |
| atualizar o código | `git -C ~/bot-smc-binance pull` |
| parar o radar | `crontab -r` |
| religar | `bash ~/bot-smc-binance/oracle/instalar.sh` |

**Não deixe a conta parada.** A Oracle considera abandonada uma conta
sem uso por 30 dias e pode suspender. Como o radar roda de hora em hora,
isso não acontece — mas se você desligar a máquina por um mês, ela pode
sumir.

**O estado fica na própria máquina**, em `varredura_enviados.json`. Não
há commit de volta no GitHub, então não existe conflito com o Actions.
