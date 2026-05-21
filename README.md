# RELP-SN

Sistema local para gerar relatorios CSV/PDF do RELP-SN e preparar a integracao com SERPRO / Integra Contador.

Esta versao nasceu a partir da base PSN Onvio porque ela ja tinha arquitetura funcional para Flask, SERPRO, logs e emissao de arquivos. O dominio operacional deste projeto, porem, e RELP-SN.

- Empresa inicial: `34243018000136 - A & P Facilities e Servicos LTDA`
- Parcelas iniciais: janeiro a abril de 2026
- Geracao RELP-SN em CSV/PDF

## RELP-SN

Endpoint inicial:

```text
POST /relp-sn/generate
Content-Type: application/json
```

Endpoint rapido para a empresa atual:

```text
POST /relp-sn/a-p-facilities/generate
```

Endpoint interno para consultar o RELP-SN real no SERPRO e salvar a emissao retornada:

```text
POST /relp-sn/a-p-facilities/consultar-serpro-json
```

Catalogo SERPRO validado neste ambiente:

```text
RELPSN/PEDIDOSPARC193
RELPSN/PARCELASPARAGERAR192
```

Esse endpoint tambem salva a emissao no banco e deixa o PDF pronto para envio ao Onvio. A tela operacional fica em:

```text
GET /relp-sn/
```

Payload minimo:

```json
{
  "cnpj": "34243018000136",
  "nome_empresa": "A & P Facilities e Servicos LTDA",
  "numero_parcelamento": "RELP-SN-A-P-FACILITIES",
  "valor_consolidado": "30024,28",
  "saldo_remanescente": "30024,28",
  "parcelas": [
    {
      "numero_parcela": 1,
      "competencia": "01/2026",
      "valor_total": "7489,52",
      "status": "ABERTA"
    }
  ]
}
```

Os arquivos sao gravados em:

```text
storage/relp_sn/<cnpj>/<data-hora>/relp-sn.csv
storage/relp_sn/<cnpj>/<data-hora>/relp-sn.pdf
```

Para gerar um exemplo local:

```bash
python scripts/generate_sample.py
```

## Login

O sistema exige login antes de acessar as telas internas.

Configure no `.env`:

```text
APP_LOGIN_USER=
APP_LOGIN_PASSWORD_HASH=
APP_SESSION_HOURS=8
APP_SESSION_COOKIE_SECURE=0
```

Para gerar o hash da senha:

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('sua-senha'))"
```

Em producao com HTTPS, use:

```text
APP_SESSION_COOKIE_SECURE=1
```

## Fluxo

1. Gerar a base local RELP-SN da A & P Facilities.
2. Emitir CSV/PDF com as parcelas de janeiro a abril.
3. Salvar a emissao e parcelas nas tabelas `relp_sn_emissoes` e `relp_sn_parcelas`.
4. Enviar o PDF ao Onvio por pasta quando `ONVIO_UPLOAD_MODE=pasta`.
5. Substituir o mock local pela consulta SERPRO especifica de RELP-SN quando os identificadores oficiais estiverem disponiveis.

No modo `pasta`, se a empresa nao tiver caminho Onvio cadastrado, o destino padrao e:

```text
storage/onvio_saida/<cnpj>/RELP-SN
```

## SERPRO

A automacao por navegador foi removida. O ponto de integracao herdado fica em:

```text
app/services/serpro_service.py
```

O servico atual ainda esta preparado para PARCSN, que era o Parcelamento do Simples Nacional. Para RELP-SN, o proximo passo e trocar os identificadores/payloads pelos servicos corretos da API SERPRO desse parcelamento.

Variaveis previstas:

```text
SERPRO_CONSUMER_KEY
SERPRO_CONSUMER_SECRET
SERPRO_CERT_PATH
SERPRO_CERT_PASSWORD
SERPRO_TOKEN_URL
SERPRO_API_URL
```

Servicos PARCSN herdados da base:

- `PARCELASPARAGERAR162`: Consultar Parcelas Disponiveis para Impressao.
- `GERARDAS161`: Emitir Documento de Arrecadacao.
- `OBTERPARC164`: Consultar Parcelamento.

O cliente HTTP central registra logs tecnicos na tabela `serpro_logs`, sem gravar consumer secret.
As disponibilidades consultadas ficam na tabela `psn_disponibilidades`, incluindo casos em que a API informa que nao ha parcela liberada.
Em producao, os eventos SERPRO tambem sao gravados em `logs/serpro.log`.

## Erros internos

Avisos normais da API SERPRO, como parcela indisponivel ou nenhuma parcela liberada, sao tratados como avisos operacionais.

Erros internos reais do sistema recebem:

- codigo unico de ocorrencia;
- tela amigavel para o usuario;
- log tecnico completo na tabela `erros_internos`;
- tentativa opcional de envio de e-mail para suporte.

Em producao, erros internos tambem sao gravados em `logs/psn.log`, com stack trace completo e codigo de ocorrencia.

Configuracao opcional de e-mail:

```text
ERROR_EMAIL_ENABLED=1
ERROR_EMAIL_TO=gustavo.neves@consistecontabilidade.com
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_USE_TLS=1
```

## Onvio

O envio ao Onvio tem dois modos:

- `pasta`: copia o PDF para uma pasta local/sincronizada.
- `selenium`: abre o Onvio no navegador, autentica quando necessario e faz upload na pasta do cliente.

Cada empresa pode ter uma `Pasta Onvio` cadastrada. Se esse campo ficar vazio e o modo for `pasta`, o sistema usa:

```text
storage/onvio_saida/<cnpj>
```

Configuracao do modo Selenium:

```text
ONVIO_UPLOAD_MODE=selenium
ONVIO_URL=https://onvio.com.br/staff/#/documents/client
ONVIO_EMAIL=
ONVIO_PASSWORD=
ONVIO_BROWSER=chrome
ONVIO_HEADLESS=0
ONVIO_USER_DATA_DIR=storage/onvio_browser
ONVIO_WAIT_SECONDS=25
```

O fluxo Selenium considera estes cenarios:

- sessao Onvio ja autenticada;
- sessao expirada, com login simples por e-mail e senha.
- validacao por codigo enviado ao e-mail, usando Microsoft Graph para ler o codigo no Outlook e continuar o login automaticamente.

Para o modo Selenium, rode preferencialmente pelo `run.bat` no Windows, pois ele controla o navegador do desktop.

Configuracao opcional do Microsoft Graph para codigo Onvio:

```text
MICROSOFT_GRAPH_TENANT_ID=
MICROSOFT_GRAPH_CLIENT_ID=
MICROSOFT_GRAPH_CLIENT_SECRET=
MICROSOFT_GRAPH_USER_EMAIL=
MICROSOFT_GRAPH_LOOKBACK_MINUTES=10
MICROSOFT_GRAPH_POLL_SECONDS=45
```

O app Microsoft deve ter permissao para ler e-mails da caixa configurada, por exemplo `Mail.Read` com consentimento administrativo quando usado em fluxo de aplicativo.

Os eventos do Onvio tambem sao gravados em `logs/onvio.log`. Quando uma etapa Selenium falha, o sistema pode salvar automaticamente:

- screenshot da tela em `logs/screenshots`;
- HTML da pagina em `logs/html`.

Esses arquivos ajudam a diagnosticar erro real em servidor ou em outro computador sem depender da memoria do usuario.

## Logs e producao Oracle

Variaveis recomendadas para servidor:

```text
LOG_DIR=logs
LOG_LEVEL=INFO
LOG_MAX_BYTES=5242880
LOG_BACKUP_COUNT=5
ONVIO_HEADLESS=1
ONVIO_SAVE_ERROR_SCREENSHOT=1
ONVIO_SAVE_ERROR_HTML=1
```

Arquivos principais de diagnostico:

```text
logs/psn.log
logs/serpro.log
logs/onvio.log
logs/screenshots/
logs/html/
```

Os arquivos de log, PDFs, certificados e `.env` ficam fora do Git. No servidor, configure o `.env` diretamente na maquina ou por variaveis de ambiente.

Entrada WSGI para servidor:

```text
wsgi:app
```

Exemplo Linux/Oracle:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
gunicorn -w 2 -b 0.0.0.0:5050 wsgi:app
```

## Como rodar

No Windows:

```bat
run.bat
```

Ou manualmente:

```bat
.venv\Scripts\activate
python -m app.main
```

Acesse:

```text
http://127.0.0.1:5050
```
