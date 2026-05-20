import csv
import re
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
