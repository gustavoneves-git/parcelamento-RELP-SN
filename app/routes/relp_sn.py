from flask import Blueprint, flash, jsonify, redirect, request, url_for

from app.services.relp_sn import (
    RelpSnErroValidacao,
    consultar_e_salvar_relp_sn_serpro_ap_facilities,
    emitir_e_salvar_das_relp_sn_ap_facilities,
    enviar_emissao_onvio,
    gerar_relp_sn,
    gerar_e_salvar_relp_sn_ap_facilities,
)


relp_sn_bp = Blueprint("relp_sn", __name__, url_prefix="/relp-sn")


@relp_sn_bp.route("/")
def index():
    return redirect(url_for("historico.mensal"))


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
    return redirect(url_for("historico.mensal"))


@relp_sn_bp.route("/<int:emissao_id>/enviar-onvio", methods=["POST"])
def enviar_onvio(emissao_id):
    resultado = enviar_emissao_onvio(emissao_id)
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify(resultado), 200 if resultado["categoria"] == "success" else 400

    flash(resultado["mensagem"], resultado["categoria"])
    return redirect(url_for("historico.mensal"))


@relp_sn_bp.route("/a-p-facilities/generate-json", methods=["POST"])
def generate_ap_facilities_json():
    emissao = gerar_e_salvar_relp_sn_ap_facilities()
    return jsonify(
        {
            "mensagem": "RELP-SN da A & P Facilities gerado com sucesso.",
            "emissao": dict(emissao),
        }
    )


@relp_sn_bp.route("/a-p-facilities/consultar-serpro-json", methods=["POST"])
def consultar_serpro_ap_facilities_json():
    resultado = consultar_e_salvar_relp_sn_serpro_ap_facilities()
    status = 200 if resultado["categoria"] == "success" else 400
    resposta = {
        "mensagem": resultado["mensagem"],
        "categoria": resultado["categoria"],
    }
    if resultado.get("emissao") is not None:
        resposta["emissao"] = dict(resultado["emissao"])
    return jsonify(resposta), status


@relp_sn_bp.route("/a-p-facilities/consultar-serpro", methods=["POST"])
def consultar_serpro_ap_facilities():
    resultado = consultar_e_salvar_relp_sn_serpro_ap_facilities()
    flash(resultado["mensagem"], resultado["categoria"])
    return redirect(url_for("historico.mensal"))


@relp_sn_bp.route("/a-p-facilities/emitir-das-json", methods=["POST"])
def emitir_das_ap_facilities_json():
    parcela = (request.get_json(silent=True) or {}).get("parcela") or "202605"
    resultado = emitir_e_salvar_das_relp_sn_ap_facilities(str(parcela))
    status = 200 if resultado["categoria"] == "success" else 400
    resposta = {
        "mensagem": resultado["mensagem"],
        "categoria": resultado["categoria"],
    }
    if resultado.get("emissao") is not None:
        resposta["emissao"] = dict(resultado["emissao"])
    return jsonify(resposta), status


@relp_sn_bp.route("/a-p-facilities/emitir-das", methods=["POST"])
def emitir_das_ap_facilities():
    parcela = request.form.get("parcela") or "202605"
    resultado = emitir_e_salvar_das_relp_sn_ap_facilities(str(parcela))
    flash(resultado["mensagem"], resultado["categoria"])
    return redirect(url_for("historico.mensal"))
