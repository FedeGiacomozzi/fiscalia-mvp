import base64
import json
import os
import re
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import secretmanager
from openai import OpenAI

from alertas import evaluar_y_enviar_alertas, send_test_mail
from firestore_client import get_db, guardar_factura

app = FastAPI(title="FiscalIA API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_openai_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        return api_key

    client = secretmanager.SecretManagerServiceClient()
    name = "projects/fiscalia-mvp/secrets/OPENAI_API_KEY/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


_openai_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=_get_openai_api_key(), http_client=httpx.Client())
    return _openai_client


EXTRACTION_PROMPT = (
    "Sos un asistente que extrae datos de facturas argentinas. "
    "Devolvé SOLO un JSON con estos campos: "
    "proveedor (string), monto_total (number), fecha (string DD/MM/YYYY), "
    "numero_factura (string), tipo (string: A/B/C), iva_monto (number), "
    "categoria (string: elegí la más apropiada entre: servicios, insumos, "
    "alquiler, logistica, otros)"
)


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


@app.post("/procesar-factura")
async def procesar_factura(imagen: UploadFile = File(...)):
    contents = await imagen.read()
    b64 = base64.b64encode(contents).decode("utf-8")

    content_type = imagen.content_type or "image/jpeg"

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": EXTRACTION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{content_type};base64,{b64}"
                            },
                        },
                    ],
                }
            ],
            max_tokens=512,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al llamar a OpenAI: {exc}")

    raw = response.choices[0].message.content or ""

    try:
        datos = _extract_json(raw)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail=(
                "OpenAI no pudo extraer los datos de la imagen. "
                "Asegurate de subir una foto clara de la factura."
            ),
        )

    try:
        doc_id = guardar_factura(datos)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al guardar en Firestore: {exc}")

    return {"id": doc_id, **datos}


@app.get("/verificar-alertas")
async def verificar_alertas():
    now = datetime.now(timezone.utc)
    inicio_mes = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if now.month == 12:
        inicio_prox = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        inicio_prox = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

    try:
        docs = (
            get_db()
            .collection("facturas")
            .where("timestamp", ">=", inicio_mes)
            .where("timestamp", "<", inicio_prox)
            .get()
        )
        facturas = [doc.to_dict() for doc in docs]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al leer Firestore: {exc}")

    try:
        alertas = evaluar_y_enviar_alertas(facturas)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al procesar alertas: {exc}")

    return {
        "mes": now.strftime("%Y-%m"),
        "facturas_del_mes": len(facturas),
        "alertas_disparadas": len(alertas),
        "mail_enviado": len(alertas) > 0,
        "alertas": alertas,
    }


@app.get("/test-mail")
async def test_mail():
    try:
        send_test_mail()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al enviar mail: {exc}")
    return {"ok": True, "mensaje": "Mail de prueba enviado a Fede.Giacomozzi@gmail.com"}
