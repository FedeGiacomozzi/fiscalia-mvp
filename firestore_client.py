from google.cloud import firestore
from datetime import datetime, timezone


_db = None


def get_db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project="fiscalia-mvp-bf46c")
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
