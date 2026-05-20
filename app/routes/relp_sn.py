from flask import Blueprint, jsonify, request

from app.services.relp_sn import (
    RelpSnErroValidacao,
    gerar_relp_sn,
    gerar_relp_sn_ap_facilities,
)


relp_sn_bp = Blueprint("relp_sn", __name__, url_prefix="/relp-sn")


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
    exportacao = gerar_relp_sn_ap_facilities()
    return jsonify(
        {
            "mensagem": "RELP-SN da A & P Facilities gerado com sucesso.",
            "exportacao": exportacao.as_dict(),
        }
    )
