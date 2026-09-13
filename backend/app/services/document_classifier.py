"""Hybrid document classifier.

Combines MRZ evidence, OCR keyword patterns and structural cues into a document
type + confidence + human-readable evidence list. Designed so a trained model
(``DocumentClassifier.classify(image)``) can later replace the heuristics behind
the same interface.
"""
from __future__ import annotations

import re

from ..core.constants import DocumentType


class DocumentClassifier:
    """Rule/OCR hybrid classifier (swappable for a trained model later)."""

    def classify(self, ocr_text: str, mrz: dict) -> dict:
        text = (ocr_text or "").upper()
        evidence: list[str] = []
        scores = {
            DocumentType.PASSPORT: 0.0,
            DocumentType.VISA: 0.0,
            DocumentType.NATIONAL_ID: 0.0,
        }

        # --- MRZ signal (strong) ---
        if mrz and mrz.get("detected"):
            mtype = mrz.get("mrz_type")
            dtype = (mrz.get("fields", {}) or {}).get("document_type", "").upper()
            if mtype == "TD3":
                scores[DocumentType.PASSPORT] += 0.55
                evidence.append("TD3 MRZ (passport format) detected")
            elif mtype == "TD1":
                scores[DocumentType.NATIONAL_ID] += 0.5
                evidence.append("TD1 MRZ (ID-1 card format) detected")
            elif mtype == "TD2":
                scores[DocumentType.NATIONAL_ID] += 0.3
                evidence.append("TD2 MRZ detected")
            if dtype.startswith("P"):
                scores[DocumentType.PASSPORT] += 0.15
                evidence.append("MRZ document type code 'P' (passport)")
            elif dtype.startswith("V"):
                scores[DocumentType.VISA] += 0.35
                evidence.append("MRZ document type code 'V' (visa)")
            elif dtype.startswith("I") or dtype.startswith("A") or dtype.startswith("C"):
                scores[DocumentType.NATIONAL_ID] += 0.2
                evidence.append("MRZ document type code 'I/A/C' (ID card)")

        # --- Keyword signal ---
        keyword_map = [
            (DocumentType.PASSPORT, r"\bPASSPORT\b", 0.4, "Keyword 'PASSPORT' found"),
            (DocumentType.VISA, r"\bVISA\b", 0.5, "Keyword 'VISA' found"),
            (DocumentType.NATIONAL_ID, r"NATIONAL\s+ID|IDENTITY\s+CARD|ID\s+CARD",
             0.45, "Keyword 'IDENTITY/ID CARD' found"),
        ]
        for dtype, pattern, weight, note in keyword_map:
            if re.search(pattern, text):
                scores[dtype] += weight
                evidence.append(note)

        # --- Field-pattern signal ---
        if re.search(r"PASSPORT\s*N[O0]", text) or re.search(r"\bTYPE\b.*\bP\b", text):
            scores[DocumentType.PASSPORT] += 0.1
            evidence.append("Passport field pattern detected")
        if re.search(r"DATE\s+OF\s+EXPIRY|DATE\s+OF\s+BIRTH", text):
            for k in scores:
                scores[k] += 0.03

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        if best_score < 0.25:
            return {
                "document_type": DocumentType.UNKNOWN,
                "confidence": round(min(0.4, best_score + 0.1), 3),
                "evidence": evidence or ["No decisive passport/visa/ID indicators found"],
            }

        confidence = round(min(0.99, best_score), 3)
        return {
            "document_type": best_type,
            "confidence": confidence,
            "evidence": evidence,
        }


document_classifier = DocumentClassifier()
