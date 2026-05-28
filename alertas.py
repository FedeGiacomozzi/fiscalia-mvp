import os

import resend
from google.cloud import secretmanager

TOPE_ANUAL = 50_000_000
TOPE_MENSUAL = TOPE_ANUAL / 12        # ~$4_166_667
TOPE_FACTURAS = 50
UMBRAL = 0.80
DESTINATARIO = "Fede.Giacomozzi@gmail.com"

_resend_api_key: str | None = None


def _get_resend_api_key() -> str:
    global _resend_api_key
    if _resend_api_key is not None:
        return _resend_api_key
    key = os.environ.get("RESEND_API_KEY")
    if key:
        _resend_api_key = key
        return _resend_api_key
    client = secretmanager.SecretManagerServiceClient()
    name = "projects/fiscalia-mvp/secrets/RESEND_API_KEY/versions/latest"
    response = client.access_secret_version(request={"name": name})
    _resend_api_key = response.payload.data.decode("utf-8")
    return _resend_api_key


def send_test_mail() -> None:
    resend.api_key = _get_resend_api_key()
    resend.Emails.send({
        "from": "FiscalIA <onboarding@resend.dev>",
        "to": [DESTINATARIO],
        "subject": "FiscalIA — test de notificación funcionando",
        "html": """
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;">
          <h2 style="color:#7C3AED;">✅ FiscalIA</h2>
          <p>El sistema de notificaciones por mail está funcionando correctamente.</p>
          <p style="color:#aaa;font-size:11px;">FiscalIA MVP · mensaje de prueba</p>
        </div>
        """,
    })


def evaluar_y_enviar_alertas(facturas: list[dict]) -> list[dict]:
    """
    Recibe facturas del mes actual, evalúa dos umbrales al 80%:
      - monto acumulado vs tope mensual de monotributo ($50M/12)
      - cantidad de facturas vs 50
    Si alguno supera el umbral, envía mail a DESTINATARIO vía Resend.
    Devuelve la lista de alertas disparadas (puede estar vacía).
    """
    monto_acumulado = sum(f.get("monto_total") or 0 for f in facturas)
    cantidad = len(facturas)

    pct_monto = monto_acumulado / TOPE_MENSUAL
    pct_cant = cantidad / TOPE_FACTURAS

    alertas: list[dict] = []

    if pct_monto >= UMBRAL:
        alertas.append({
            "tipo": "monto_mensual",
            "descripcion": (
                f"Monto acumulado ${monto_acumulado:,.0f} representa el "
                f"{pct_monto * 100:.1f}% del tope mensual de monotributo "
                f"(${TOPE_MENSUAL:,.0f})"
            ),
            "porcentaje": round(pct_monto * 100, 1),
            "valor_actual": monto_acumulado,
            "tope": TOPE_MENSUAL,
        })

    if pct_cant >= UMBRAL:
        alertas.append({
            "tipo": "cantidad_facturas",
            "descripcion": (
                f"{cantidad} facturas procesadas representan el "
                f"{pct_cant * 100:.1f}% del límite de {TOPE_FACTURAS}"
            ),
            "porcentaje": round(pct_cant * 100, 1),
            "valor_actual": cantidad,
            "tope": TOPE_FACTURAS,
        })

    if alertas:
        _enviar_mail(alertas, monto_acumulado, cantidad)

    return alertas


def _enviar_mail(alertas: list[dict], monto: float, cantidad: int) -> None:
    resend.api_key = _get_resend_api_key()

    items_html = "".join(
        f"<li><b>{a['tipo'].replace('_', ' ').title()}</b> — {a['descripcion']}</li>"
        for a in alertas
    )

    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;">
      <h2 style="color:#7C3AED;">⚠️ FiscalIA — Alertas fiscales del mes</h2>
      <p>Se superaron los siguientes umbrales del <b>80%</b>:</p>
      <ul style="line-height:1.7;">{items_html}</ul>
      <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
      <p style="color:#888;font-size:13px;">
        Monto acumulado del mes: <b>${monto:,.0f}</b> &nbsp;|&nbsp;
        Facturas procesadas: <b>{cantidad}</b>
      </p>
      <p style="color:#aaa;font-size:11px;">FiscalIA MVP · alerta automática</p>
    </div>
    """

    # El remitente onboarding@resend.dev funciona sin verificar dominio propio.
    # En producción reemplazarlo por un dominio verificado en Resend.
    resend.Emails.send({
        "from": "FiscalIA <onboarding@resend.dev>",
        "to": [DESTINATARIO],
        "subject": "⚠️ FiscalIA — Alerta fiscal activa",
        "html": html,
    })
