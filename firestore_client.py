import json

from google.cloud import firestore, secretmanager
from google.oauth2 import service_account
from datetime import datetime, timezone


_db = None


def _get_db() -> firestore.Client:
    sm = secretmanager.SecretManagerServiceClient()
    name = "projects/fiscalia-mvp/secrets/FIREBASE_SA_KEY/versions/latest"
    payload = sm.access_secret_version(request={"name": name}).payload.data.decode("utf-8")
    sa_info = json.loads(payload)
    creds = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return firestore.Client(project="fiscalia-mvp-bf46c", credentials=creds)


def get_db() -> firestore.Client:
    global _db
    if _db is None:
        _db = _get_db()
    return _db


def guardar_factura(datos: dict) -> str:
    db = get_db()
    doc_ref = db.collection("facturas").document()
    doc_ref.set(
        {
            **datos,
            "timestamp": datetime.now(timezone.utc),
            "estado": "procesada",
        }
    )
    return doc_ref.id
