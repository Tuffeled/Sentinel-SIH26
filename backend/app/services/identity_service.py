"""Cross-document identity consistency + a lightweight identity graph.

When an investigation holds more than one document we compare identity attributes
(name, DOB, nationality, sex, face) across them and build a consistency matrix.
Meaningful conflicts become CROSS_DOCUMENT_CONFLICT evidence.

The identity graph is a plain Python/SQLite structure (Person → Document →
Face/Identifier), designed so a graph DB (e.g. Neo4j) could be introduced later.
"""
from __future__ import annotations

import numpy as np

from ..config import settings
from ..core.constants import Severity
from ..utils.text import normalize_date, normalize_name, similarity

_CROSS_FACE_THRESHOLD = 0.62  # looser than single-doc verification


def _canonical(doc: dict) -> dict:
    mrz = doc.get("mrz_fields") or {}
    ocr = doc.get("ocr_fields") or {}

    def pick(key):
        return mrz.get(key) or ocr.get(key) or ""

    return {
        "document_id": doc.get("id"),
        "document_type": doc.get("document_type"),
        "label": doc.get("label") or doc.get("document_type"),
        "full_name": pick("full_name") or f"{ocr.get('given_names','')} {ocr.get('surname','')}".strip(),
        "surname": pick("surname"),
        "dob": normalize_date(pick("dob")),
        "nationality": pick("nationality"),
        "sex": pick("sex"),
        "document_number": doc.get("document_number") or pick("document_number"),
        "encoding": doc.get("face_encoding"),
    }


def _compare_text_attr(docs, key, *, name_like=False):
    values = [(d["document_id"], (d.get(key) or "").strip()) for d in docs]
    present = [(i, v) for i, v in values if v]
    if len(present) < 2:
        return "N/A", values
    if name_like:
        base = present[0][1]
        conflict = any(similarity(base, v) < 0.8 for _, v in present[1:])
    else:
        norm = {normalize_name(v) if name_like else v.upper() for _, v in present}
        conflict = len(norm) > 1
    return ("CONFLICT" if conflict else "MATCH"), values


def _compare_faces(docs):
    enc = [(d["document_id"], np.array(d["encoding"]))
           for d in docs if d.get("encoding") is not None]
    if len(enc) < 2:
        return "N/A", [], None
    max_dist = 0.0
    for i in range(len(enc)):
        for j in range(i + 1, len(enc)):
            dist = float(np.linalg.norm(enc[i][1] - enc[j][1]))
            max_dist = max(max_dist, dist)
    values = [{"document_id": did, "value": "face present"} for did, _ in enc]
    if max_dist > _CROSS_FACE_THRESHOLD:
        return "WARNING", values, round(max_dist, 3)
    return "MATCH", values, round(max_dist, 3)


def analyze(documents: list[dict]) -> dict:
    """documents: list of {id, document_type, label, ocr_fields, mrz_fields,
    face_encoding, document_number}. Returns matrix + conflicts + graph."""
    if len(documents) < 2:
        return {"applicable": False, "matrix": [], "conflicts": [],
                "graph": _graph([_canonical(d) for d in documents]),
                "message": "Cross-document consistency requires at least two documents."}

    docs = [_canonical(d) for d in documents]
    matrix, conflicts = [], []

    attr_specs = [
        ("full_name", "Name", True, Severity.HIGH),
        ("dob", "Date of birth", False, Severity.HIGH),
        ("nationality", "Nationality", False, Severity.MEDIUM),
        ("sex", "Sex", False, Severity.LOW),
    ]
    for key, label, name_like, severity in attr_specs:
        result, values = _compare_text_attr(docs, key, name_like=name_like)
        row = {"attribute": key, "label": label, "result": result,
               "values": [{"document_id": i, "value": v} for i, v in values]}
        matrix.append(row)
        if result == "CONFLICT":
            conflicts.append({
                "attribute": key, "label": label, "severity": severity,
                "description": f"{label} is inconsistent across the linked documents.",
                "values": row["values"],
            })

    face_result, face_values, max_dist = _compare_faces(docs)
    matrix.append({"attribute": "face", "label": "Face", "result": face_result,
                   "values": face_values, "detail": {"max_distance": max_dist}})
    if face_result == "WARNING":
        conflicts.append({
            "attribute": "face", "label": "Face", "severity": Severity.MEDIUM,
            "description": ("Faces across the linked documents differ more than expected "
                            f"(max distance {max_dist})."),
            "values": face_values,
        })

    return {
        "applicable": True,
        "matrix": matrix,
        "conflicts": conflicts,
        "graph": _graph(docs),
        "message": f"Compared {len(docs)} documents.",
    }


def _graph(docs: list[dict]) -> dict:
    """Build a small identity graph structure for visualisation."""
    nodes = [{"id": "person", "type": "Person", "label": "Subject Identity"}]
    edges = []
    for d in docs:
        did = d.get("document_id")
        dnode = f"doc{did}"
        nodes.append({"id": dnode, "type": "Document",
                      "label": f"{d.get('label') or d.get('document_type')}"})
        edges.append({"source": "person", "target": dnode, "relation": "owns"})
        if d.get("document_number"):
            idnode = f"id{did}"
            nodes.append({"id": idnode, "type": "Identifier", "label": d["document_number"]})
            edges.append({"source": dnode, "target": idnode, "relation": "has_identifier"})
        if d.get("encoding") is not None:
            fnode = f"face{did}"
            nodes.append({"id": fnode, "type": "Face", "label": "Face"})
            edges.append({"source": dnode, "target": fnode, "relation": "has_face"})
    return {"nodes": nodes, "edges": edges}
