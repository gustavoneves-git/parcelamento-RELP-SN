from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.services.relp_sn import (
    RelpSnErroValidacao,
    enviar_emissao_onvio,
    gerar_relp_sn,
    gerar_e_salvar_relp_sn_ap_facilities,
    listar_emissoes_relp_sn,
    listar_parcelas_emissao,
)


relp_sn_bp = Blueprint("relp_sn", __name__, url_prefix="/relp-sn")


@relp_sn_bp.route("/")
def index():
    emissoes = listar_emissoes_relp_sn()
    parcelas_por_emissao = {
        emissao["id"]: listar_parcelas_emissao(emissao["id"])
        for emissao in emissoes
    }
    return render_template(
        "relp_sn.html",
        emissoes=emissoes,
        parcelas_por_emissao=parcelas_por_emissao,
    )


@relp_sn_bp.route("/generate", methods=["POST"])
def generate():
    try:
        exportacao = gerar_relp_sn(request.get_json(silent=True) or {})
    except RelpSnErroValidacao as exc:
        return jsonify({"erro": str(exc)}), 400

    return jsonify(
        {
            "mensagem": "RELP-SN gerado com sucesso.",
            "exportacao": exportacao.as_dict(),
        }
    )


@relp_sn_bp.route("/a-p-facilities/generate", methods=["POST"])
def generate_ap_facilities():
    emissao = gerar_e_salvar_relp_sn_ap_facilities()
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify(
            {
                "mensagem": "RELP-SN da A & P Facilities gerado com sucesso.",
                "emissao": dict(emissao),
            }
        )

    flash("RELP-SN da A & P Facilities gerado com sucesso.", "success")
    return redirect(url_for("relp_sn.index"))


@relp_sn_bp.route("/<int:emissao_id>/enviar-onvio", methods=["POST"])
def enviar_onvio(emissao_id):
    resultado = enviar_emissao_onvio(emissao_id)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify(resultado), 200 if resultado["categoria"] == "success" else 400

    flash(resultado["mensagem"], resultado["categoria"])
    return redirect(url_for("relp_sn.index"))


@relp_sn_bp.route("/a-p-facilities/generate-json", methods=["POST"])
def generate_ap_facilities_json():
    emissao = gerar_e_salvar_relp_sn_ap_facilities()
    return jsonify(
        {
            "mensagem": "RELP-SN da A & P Facilities gerado com sucesso.",
            "emissao": dict(emissao),
        }
    )
