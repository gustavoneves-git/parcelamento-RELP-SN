from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.services.empresa_service import (
    atualizar_empresa,
    buscar_empresa,
    criar_empresa,
    listar_empresas_com_parcela_atual,
)
from app.services.relp_sn import (
    consultar_e_salvar_relp_sn_serpro_ap_facilities,
    emitir_e_salvar_das_relp_sn_ap_facilities,
    enviar_emissao_onvio,
)


empresas_bp = Blueprint("empresas", __name__, url_prefix="/empresas")


@empresas_bp.route("/")
def index():
    filtro_status = request.args.get("status", "ATIVA").upper()
    if filtro_status not in ("ATIVA", "INATIVA", "TODAS"):
        filtro_status = "ATIVA"
    status_consulta = None if filtro_status == "TODAS" else filtro_status

    return render_template(
        "empresas.html",
        empresas=listar_empresas_com_parcela_atual(status_consulta),
        filtro_status=filtro_status,
    )


@empresas_bp.route("/nova", methods=["GET", "POST"])
def nova():
    if request.method == "POST":
        empresa_id, erros = criar_empresa(request.form)
        if not erros:
            flash("Empresa cadastrada com sucesso.", "success")
            return redirect(url_for("empresas.editar", empresa_id=empresa_id))
        for erro in erros:
            flash(erro, "error")

    return render_template("empresa_form.html", empresa=request.form, titulo="Nova empresa")


@empresas_bp.route("/<int:empresa_id>/editar", methods=["GET", "POST"])
def editar(empresa_id):
    empresa = buscar_empresa(empresa_id)
    if empresa is None:
        flash("Empresa nao encontrada.", "error")
        return redirect(url_for("empresas.index"))

    if request.method == "POST":
        erros = atualizar_empresa(empresa_id, request.form)
        if not erros:
            flash("Empresa atualizada com sucesso.", "success")
            return redirect(url_for("empresas.index"))
        for erro in erros:
            flash(erro, "error")
        empresa = request.form

    return render_template("empresa_form.html", empresa=empresa, titulo="Editar empresa")


@empresas_bp.route("/<int:empresa_id>/emitir", methods=["POST"])
def emitir(empresa_id):
    parcela = request.form.get("parcela") or ""
    resultado = emitir_e_salvar_das_relp_sn_ap_facilities(parcela)
    flash(resultado["mensagem"], resultado["categoria"])
    return redirect(url_for("empresas.index"))


@empresas_bp.route("/<int:empresa_id>/consultar-serpro", methods=["POST"])
def consultar_serpro(empresa_id):
    resultado = consultar_e_salvar_relp_sn_serpro_ap_facilities()
    flash(resultado["mensagem"], resultado["categoria"])
    return redirect(url_for("empresas.index"))


@empresas_bp.route("/<int:empresa_id>/subir-onvio", methods=["POST"])
def subir_onvio(empresa_id):
    emissao_id = request.form.get("emissao_id")
    if not emissao_id:
        flash("Emissao RELP-SN nao encontrada para envio.", "error")
        return redirect(url_for("empresas.index"))
    resultado = enviar_emissao_onvio(int(emissao_id))
    flash(resultado["mensagem"], resultado["categoria"])
    return redirect(url_for("empresas.index"))
