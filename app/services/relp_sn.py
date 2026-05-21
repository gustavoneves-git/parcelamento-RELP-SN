import csv
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.database import get_db
from app.services.empresa_service import buscar_empresa, buscar_empresa_por_cnpj, criar_empresa
from app.services.onvio_log_service import registrar_onvio_log
from app.services.onvio_selenium_service import (
    OnvioAutomacaoErro,
    OnvioConfiguracaoErro,
    subir_pdf_onvio_selenium,
)
from app.services.serpro_service import (
    SerproErro,
    SerproNaoConfigurado,
    consultar_parcelas_disponiveis_relp_sn,
    consultar_pedidos_relp_sn,
)


CSV_HEADERS = (
    "numero_parcela",
    "competencia",
    "vencimento",
    "valor_principal",
    "valor_juros",
    "valor_multa",
    "valor_total",
    "status",
)


AP_FACILITIES_PAYLOAD = {
    "cnpj": "34243018000136",
    "nome_empresa": "A & P Facilities e Servicos LTDA",
    "numero_parcelamento": "RELP-SN-A-P-FACILITIES",
    "data_consolidacao": "",
    "valor_consolidado": "30024,28",
    "entrada": "0,00",
    "saldo_remanescente": "30024,28",
    "parcelas": [
        {
            "numero_parcela": 1,
            "competencia": "01/2026",
            "vencimento": "",
            "valor_total": "7489,52",
            "status": "ABERTA",
        },
        {
            "numero_parcela": 2,
            "competencia": "02/2026",
            "vencimento": "",
            "valor_total": "7551,48",
            "status": "ABERTA",
        },
        {
            "numero_parcela": 3,
            "competencia": "03/2026",
            "vencimento": "",
            "valor_total": "7604,88",
            "status": "ABERTA",
        },
        {
            "numero_parcela": 4,
            "competencia": "04/2026",
            "vencimento": "",
            "valor_total": "7378,40",
            "status": "ABERTA",
        },
    ],
}


AP_FACILITIES_CNPJ = "34243018000136"


class RelpSnErroValidacao(ValueError):
    pass


@dataclass
class RelpSnExportacao:
    pasta: Path
    csv_path: Path
    pdf_path: Path
    total_parcelas: int
    valor_total: Decimal

    def as_dict(self):
        return {
            "pasta": str(self.pasta),
            "csv": str(self.csv_path),
            "pdf": str(self.pdf_path),
            "total_parcelas": self.total_parcelas,
            "valor_total": float(self.valor_total),
        }


def gerar_relp_sn(dados):
    relatorio = _normalizar_payload(dados)
    pasta = _criar_pasta_exportacao(relatorio)
    csv_path = pasta / "relp-sn.csv"
    pdf_path = pasta / "relp-sn.pdf"

    _gerar_csv(csv_path, relatorio)
    _gerar_pdf(pdf_path, relatorio)

    return RelpSnExportacao(
        pasta=pasta,
        csv_path=csv_path,
        pdf_path=pdf_path,
        total_parcelas=len(relatorio["parcelas"]),
        valor_total=sum((p["valor_total"] for p in relatorio["parcelas"]), Decimal("0")),
    )


def gerar_relp_sn_ap_facilities():
    return gerar_relp_sn(AP_FACILITIES_PAYLOAD)


def gerar_e_salvar_relp_sn_ap_facilities():
    empresa = garantir_empresa_ap_facilities()
    exportacao = gerar_relp_sn(AP_FACILITIES_PAYLOAD)
    emissao_id = _salvar_emissao(empresa["id"], AP_FACILITIES_PAYLOAD, exportacao)
    return buscar_emissao(emissao_id)


def consultar_e_salvar_relp_sn_serpro_ap_facilities():
    empresa = garantir_empresa_ap_facilities()
    try:
        pedidos = consultar_pedidos_relp_sn(empresa)
        parcelas = consultar_parcelas_disponiveis_relp_sn(empresa)
    except SerproNaoConfigurado as exc:
        return _resultado(str(exc), "warning")
    except SerproErro as exc:
        return _resultado(str(exc), "error")

    payload = _payload_relp_sn_serpro(empresa, pedidos, parcelas)
    exportacao = gerar_relp_sn(payload)
    emissao_id = _salvar_emissao(empresa["id"], payload, exportacao)
    emissao = buscar_emissao(emissao_id)
    return {
        "mensagem": "RELP-SN consultado no SERPRO e salvo com sucesso.",
        "categoria": "success",
        "emissao": emissao,
        "pedidos": pedidos,
        "parcelas": parcelas,
    }


def garantir_empresa_ap_facilities():
    empresa = buscar_empresa_por_cnpj(AP_FACILITIES_CNPJ)
    if empresa is not None:
        return empresa

    empresa_id, erros = criar_empresa(
        {
            "cnpj": AP_FACILITIES_CNPJ,
            "nome_empresa": AP_FACILITIES_PAYLOAD["nome_empresa"],
            "nome_onvio": AP_FACILITIES_PAYLOAD["nome_empresa"],
            "pasta_onvio": "",
            "status_empresa": "ATIVA",
            "observacao": "Empresa inicial do sistema RELP-SN.",
        }
    )
    if erros:
        raise RelpSnErroValidacao("; ".join(erros))
    return buscar_empresa(empresa_id)


def listar_emissoes_relp_sn():
    return get_db().execute(
        """
        SELECT
            relp_sn_emissoes.*,
            empresas.cnpj,
            empresas.nome_empresa,
            empresas.nome_onvio,
            empresas.pasta_onvio
        FROM relp_sn_emissoes
        JOIN empresas ON empresas.id = relp_sn_emissoes.empresa_id
        ORDER BY relp_sn_emissoes.data_emissao DESC, relp_sn_emissoes.id DESC
        """
    ).fetchall()


def buscar_emissao(emissao_id):
    return get_db().execute(
        """
        SELECT
            relp_sn_emissoes.*,
            empresas.cnpj,
            empresas.nome_empresa,
            empresas.nome_onvio,
            empresas.pasta_onvio
        FROM relp_sn_emissoes
        JOIN empresas ON empresas.id = relp_sn_emissoes.empresa_id
        WHERE relp_sn_emissoes.id = ?
        """,
        (emissao_id,),
    ).fetchone()


def listar_parcelas_emissao(emissao_id):
    return get_db().execute(
        """
        SELECT *
        FROM relp_sn_parcelas
        WHERE emissao_id = ?
        ORDER BY numero_parcela
        """,
        (emissao_id,),
    ).fetchall()


def enviar_emissao_onvio(emissao_id):
    emissao = buscar_emissao(emissao_id)
    if emissao is None:
        return _resultado("Emissao RELP-SN nao encontrada.", "error")
    if emissao["status_onvio"] == "ENVIADO":
        return _resultado("RELP-SN ja enviado ao Onvio.", "warning")
    if not emissao["caminho_pdf"]:
        return _resultado("Emissao RELP-SN nao possui PDF salvo.", "error")

    caminho_pdf = Path(emissao["caminho_pdf"])
    if not caminho_pdf.exists():
        _marcar_onvio(emissao_id, "ERRO_ONVIO", "PDF RELP-SN nao encontrado no disco.")
        return _resultado("PDF RELP-SN nao encontrado no disco.", "error")

    modo = current_app.config["ONVIO_UPLOAD_MODE"].lower()
    empresa = _empresa_para_onvio(emissao)

    if modo == "pasta":
        destino = _copiar_pdf_onvio(emissao, caminho_pdf)
        mensagem = f"PDF RELP-SN copiado para o destino Onvio: {destino}"
        registrar_onvio_log(
            acao="relp_sn_onvio_pasta",
            empresa_id=emissao["empresa_id"],
            status="SUCESSO",
            mensagem=mensagem,
            detalhe_tecnico=json.dumps(
                {
                    "emissao_id": emissao_id,
                    "caminho_pdf": str(caminho_pdf),
                    "destino": str(destino),
                    "modo": "pasta",
                },
                ensure_ascii=True,
            ),
        )
        _marcar_onvio(emissao_id, "ENVIADO", mensagem)
        return _resultado("RELP-SN enviado ao Onvio por pasta.", "success")

    if modo == "selenium":
        try:
            mensagem = subir_pdf_onvio_selenium(empresa, {"id": None}, caminho_pdf)
        except OnvioConfiguracaoErro as exc:
            _marcar_onvio(emissao_id, "ERRO_ONVIO", str(exc))
            return _resultado(str(exc), "warning")
        except OnvioAutomacaoErro as exc:
            _marcar_onvio(emissao_id, "ERRO_ONVIO", str(exc))
            return _resultado(str(exc), "error")
        _marcar_onvio(emissao_id, "ENVIADO", mensagem)
        return _resultado(mensagem, "success")

    return _resultado("ONVIO_UPLOAD_MODE invalido. Use pasta ou selenium.", "error")


def _normalizar_payload(dados):
    if not isinstance(dados, dict):
        raise RelpSnErroValidacao("Informe um JSON com os dados do RELP-SN.")

    parcelas = dados.get("parcelas")
    if not isinstance(parcelas, list) or not parcelas:
        raise RelpSnErroValidacao("Informe ao menos uma parcela em 'parcelas'.")

    relatorio = {
        "cnpj": _somente_digitos(dados.get("cnpj")),
        "nome_empresa": _texto_obrigatorio(dados, "nome_empresa"),
        "numero_parcelamento": _texto_obrigatorio(dados, "numero_parcelamento"),
        "data_consolidacao": str(dados.get("data_consolidacao") or ""),
        "valor_consolidado": _decimal(dados.get("valor_consolidado")),
        "entrada": _decimal(dados.get("entrada")),
        "saldo_remanescente": _decimal(dados.get("saldo_remanescente")),
        "parcelas": [_normalizar_parcela(item, index + 1) for index, item in enumerate(parcelas)],
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }

    if len(relatorio["cnpj"]) != 14:
        raise RelpSnErroValidacao("Informe um CNPJ com 14 digitos.")

    return relatorio


def _normalizar_parcela(item, numero_padrao):
    if not isinstance(item, dict):
        raise RelpSnErroValidacao("Cada parcela deve ser um objeto JSON.")

    valor_principal = _decimal(item.get("valor_principal"))
    valor_juros = _decimal(item.get("valor_juros"))
    valor_multa = _decimal(item.get("valor_multa"))
    valor_total = _decimal(item.get("valor_total"))
    if valor_total == Decimal("0"):
        valor_total = valor_principal + valor_juros + valor_multa

    return {
        "numero_parcela": item.get("numero_parcela") or numero_padrao,
        "competencia": str(item.get("competencia") or ""),
        "vencimento": str(item.get("vencimento") or ""),
        "valor_principal": valor_principal,
        "valor_juros": valor_juros,
        "valor_multa": valor_multa,
        "valor_total": valor_total,
        "status": str(item.get("status") or "ABERTA").upper(),
    }


def _criar_pasta_exportacao(relatorio):
    raiz = Path(current_app.config["RELP_SN_EXPORTS_PATH"])
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    pasta = raiz / relatorio["cnpj"] / timestamp
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _gerar_csv(caminho, relatorio):
    with caminho.open("w", newline="", encoding="utf-8") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=CSV_HEADERS, delimiter=";")
        writer.writeheader()
        for parcela in relatorio["parcelas"]:
            writer.writerow({chave: _formatar_csv(parcela[chave]) for chave in CSV_HEADERS})


def _gerar_pdf(caminho, relatorio):
    doc = SimpleDocTemplate(
        str(caminho),
        pagesize=A4,
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
    )
    styles = getSampleStyleSheet()
    elementos = [
        Paragraph("RELP-SN - Relatorio de Parcelamento", styles["Title"]),
        Spacer(1, 0.35 * cm),
        _tabela_resumo(relatorio),
        Spacer(1, 0.45 * cm),
        Paragraph("Parcelas", styles["Heading2"]),
        _tabela_parcelas(relatorio["parcelas"]),
    ]
    doc.build(elementos)


def _tabela_resumo(relatorio):
    linhas = [
        ["Empresa", relatorio["nome_empresa"]],
        ["CNPJ", _formatar_cnpj(relatorio["cnpj"])],
        ["Numero do parcelamento", relatorio["numero_parcelamento"]],
        ["Data de consolidacao", relatorio["data_consolidacao"] or "-"],
        ["Valor consolidado", _moeda(relatorio["valor_consolidado"])],
        ["Entrada", _moeda(relatorio["entrada"])],
        ["Saldo remanescente", _moeda(relatorio["saldo_remanescente"])],
        ["Gerado em", relatorio["gerado_em"]],
    ]
    tabela = Table(linhas, colWidths=[5.0 * cm, 12.0 * cm])
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8eef7")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c2d0")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return tabela


def _tabela_parcelas(parcelas):
    linhas = [["Parc.", "Compet.", "Vencimento", "Principal", "Juros", "Multa", "Total", "Status"]]
    for parcela in parcelas:
        linhas.append(
            [
                parcela["numero_parcela"],
                parcela["competencia"],
                parcela["vencimento"],
                _moeda(parcela["valor_principal"]),
                _moeda(parcela["valor_juros"]),
                _moeda(parcela["valor_multa"]),
                _moeda(parcela["valor_total"]),
                parcela["status"],
            ]
        )

    tabela = Table(linhas, repeatRows=1)
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#20364f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c2d0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (3, 1), (6, -1), "RIGHT"),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return tabela


def _texto_obrigatorio(dados, chave):
    valor = str(dados.get(chave) or "").strip()
    if not valor:
        raise RelpSnErroValidacao(f"Informe o campo obrigatorio '{chave}'.")
    return valor


def _decimal(valor):
    if valor in (None, ""):
        return Decimal("0")
    if isinstance(valor, Decimal):
        return valor
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise RelpSnErroValidacao(f"Valor monetario invalido: {valor}")


def _formatar_csv(valor):
    if isinstance(valor, Decimal):
        return f"{valor:.2f}".replace(".", ",")
    return valor


def _moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _somente_digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def _formatar_cnpj(cnpj):
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}"


def _payload_relp_sn_serpro(empresa, pedidos_resposta, parcelas_resposta):
    pedidos = _json_dados(pedidos_resposta).get("parcelamentos") or []
    parcelas = _json_dados(parcelas_resposta).get("listaParcelas") or []
    numero_parcelamento = str(pedidos[0].get("numero")) if pedidos else "RELP-SN-SERPRO"
    parcelas_payload = []
    for index, parcela in enumerate(parcelas, start=1):
        parcela_aaaamm = str(parcela.get("parcela") or "")
        parcelas_payload.append(
            {
                "numero_parcela": index,
                "competencia": _competencia_de_aaaamm(parcela_aaaamm),
                "vencimento": "",
                "valor_total": parcela.get("valor") or "0,00",
                "status": "DISPONIVEL",
            }
        )

    if not parcelas_payload:
        raise RelpSnErroValidacao("SERPRO nao retornou parcelas RELP-SN disponiveis.")

    valor_total = sum((_decimal(parcela["valor_total"]) for parcela in parcelas_payload), Decimal("0"))
    return {
        "cnpj": empresa["cnpj"],
        "nome_empresa": empresa["nome_empresa"],
        "numero_parcelamento": numero_parcelamento,
        "data_consolidacao": "",
        "valor_consolidado": valor_total,
        "entrada": "0,00",
        "saldo_remanescente": valor_total,
        "parcelas": parcelas_payload,
    }


def _json_dados(resposta):
    if not isinstance(resposta, dict):
        return {}
    dados = resposta.get("dados")
    if isinstance(dados, dict):
        return dados
    if not isinstance(dados, str) or not dados.strip():
        return {}
    try:
        return json.loads(dados)
    except json.JSONDecodeError:
        return {}


def _competencia_de_aaaamm(parcela_aaaamm):
    if len(parcela_aaaamm) != 6:
        return ""
    return f"{parcela_aaaamm[4:6]}/{parcela_aaaamm[:4]}"


def _salvar_emissao(empresa_id, payload, exportacao):
    cursor = get_db().execute(
        """
        INSERT INTO relp_sn_emissoes (
            empresa_id,
            numero_parcelamento,
            valor_total,
            total_parcelas,
            caminho_csv,
            caminho_pdf,
            status_emissao,
            status_onvio,
            mensagem
        ) VALUES (?, ?, ?, ?, ?, ?, 'GERADA', 'PRONTO_PARA_SUBIR', ?)
        """,
        (
            empresa_id,
            payload["numero_parcelamento"],
            float(exportacao.valor_total),
            exportacao.total_parcelas,
            str(exportacao.csv_path),
            str(exportacao.pdf_path),
            "RELP-SN gerado e pronto para envio ao Onvio.",
        ),
    )
    emissao_id = cursor.lastrowid

    for parcela in _normalizar_payload(payload)["parcelas"]:
        get_db().execute(
            """
            INSERT INTO relp_sn_parcelas (
                emissao_id,
                numero_parcela,
                competencia,
                vencimento,
                valor_principal,
                valor_juros,
                valor_multa,
                valor_total,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                emissao_id,
                parcela["numero_parcela"],
                parcela["competencia"],
                parcela["vencimento"],
                float(parcela["valor_principal"]),
                float(parcela["valor_juros"]),
                float(parcela["valor_multa"]),
                float(parcela["valor_total"]),
                parcela["status"],
            ),
        )
    get_db().commit()
    return emissao_id


def _copiar_pdf_onvio(emissao, caminho_pdf):
    destino_dir = _destino_onvio(emissao)
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / caminho_pdf.name
    shutil.copy2(caminho_pdf, destino)
    return destino


def _destino_onvio(emissao):
    if emissao["pasta_onvio"]:
        return Path(emissao["pasta_onvio"])
    return Path(current_app.config["ONVIO_SAIDA_PADRAO"]) / emissao["cnpj"] / "RELP-SN"


def _marcar_onvio(emissao_id, status, mensagem):
    get_db().execute(
        """
        UPDATE relp_sn_emissoes
        SET status_onvio = ?,
            mensagem = ?,
            data_envio_onvio = CASE WHEN ? = 'ENVIADO' THEN CURRENT_TIMESTAMP ELSE data_envio_onvio END,
            data_atualizacao = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, mensagem, status, emissao_id),
    )
    get_db().commit()


def _empresa_para_onvio(emissao):
    return {
        "id": emissao["empresa_id"],
        "cnpj": emissao["cnpj"],
        "nome_empresa": emissao["nome_empresa"],
        "nome_onvio": emissao["nome_onvio"],
        "pasta_onvio": emissao["pasta_onvio"],
    }


def _resultado(mensagem, categoria):
    return {"mensagem": mensagem, "categoria": categoria}
