"""Investigation report generation (PDF via ReportLab)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Investigation
from . import audit_service


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "—"


def generate_pdf(db: Session, investigation_id: int) -> dict:
    inv = db.get(Investigation, investigation_id)
    if not inv:
        raise ValueError("Investigation not found")

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable)

    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"report_{inv.screening_id}.pdf"
    out_path = settings.reports_dir / filename

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("H", parent=styles["Heading2"], textColor=colors.HexColor("#1e3a8a")))
    styles.add(ParagraphStyle("Small", parent=styles["Normal"], fontSize=8,
                              textColor=colors.HexColor("#64748b")))
    body = styles["Normal"]

    doc = SimpleDocTemplate(str(out_path), pagesize=A4, title=f"Screening Report {inv.screening_id}",
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    story = []

    story.append(Paragraph("SENTINEL — Document Screening Report", styles["Title"]))
    if settings.demo_mode:
        story.append(Paragraph(
            "<b>SYNTHETIC DEMONSTRATION DATA — NOT A REAL GOVERNMENT DOCUMENT</b>",
            ParagraphStyle("banner", parent=body, textColor=colors.white,
                           backColor=colors.HexColor("#b45309"), alignment=1, spaceBefore=4,
                           spaceAfter=8, borderPadding=4)))
    story.append(Paragraph(f"Screening ID: <b>{inv.screening_id}</b> &nbsp;&nbsp; "
                           f"Generated: {_fmt(datetime.utcnow())}", styles["Small"]))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#cbd5e1")))
    story.append(Spacer(1, 6))

    # --- Summary ---
    story.append(Paragraph("Risk Assessment", styles["H"]))
    risk = inv.risk_assessments[-1] if inv.risk_assessments else None
    summary_rows = [
        ["Risk Score", f"{inv.risk_score or 0:.0f} / 100"],
        ["Risk Level", inv.risk_level or "—"],
        ["Recommended Action", (inv.recommended_action or "—").replace("_", " ")],
        ["Watchlist Match", "YES" if inv.watchlist_hit else "No"],
        ["Screening Time", f"{(inv.screening_time_ms or 0)/1000:.1f} s"],
        ["Status", inv.screening_status or "—"],
    ]
    t = Table(summary_rows, colWidths=[55 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(t)
    story.append(Paragraph(risk.disclaimer if risk else
                           "Risk assessment is an analytical aid and does not constitute a final "
                           "determination.", styles["Small"]))
    story.append(Spacer(1, 8))

    # --- Documents & extracted fields ---
    for d in inv.documents:
        story.append(Paragraph(f"Document: {d.original_filename} ({d.document_type})", styles["H"]))
        ocr = d.ocr_result
        mrz = d.mrz_result
        fields = (mrz.fields if mrz and mrz.fields else {}) or (ocr.fields if ocr else {})
        info_rows = [["Field", "Value"]]
        for k in ("full_name", "surname", "given_names", "document_number", "nationality",
                  "dob", "sex", "expiry_date"):
            if fields.get(k):
                info_rows.append([k.replace("_", " ").title(), str(fields[k])])
        if len(info_rows) > 1:
            it = Table(info_rows, colWidths=[55 * mm, 110 * mm])
            it.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("FONTSIZE", (0, 0), (-1, -1), 8)]))
            story.append(it)
        if mrz:
            checks = ", ".join(f"{k}={v}" for k, v in (mrz.checks or {}).items()) or "n/a"
            story.append(Paragraph(f"MRZ ({mrz.mrz_type or 'n/a'}): {checks}", styles["Small"]))
        if d.forensic_result:
            story.append(Paragraph(
                f"Forensic anomaly score: {d.forensic_result.overall_score or 0:.2f} "
                f"({'suspicious' if d.forensic_result.suspicious else 'clean'})", styles["Small"]))
        if d.face_result:
            story.append(Paragraph(f"Face: {d.face_result.status} "
                                   f"(similarity {d.face_result.similarity or '—'})", styles["Small"]))
        story.append(Spacer(1, 6))

    # --- Evidence ---
    story.append(Paragraph("Evidence", styles["H"]))
    ev_rows = [["Type", "Severity", "Pts", "Description"]]
    for e in inv.evidence:
        ev_rows.append([e.type.replace("_", " "), e.severity, str(e.risk_contribution),
                        Paragraph(e.description, styles["Small"])])
    if len(ev_rows) > 1:
        et = Table(ev_rows, colWidths=[38 * mm, 20 * mm, 12 * mm, 95 * mm])
        et.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(et)
    else:
        story.append(Paragraph("No evidence items generated.", body))
    story.append(Spacer(1, 8))

    # --- Human review ---
    story.append(Paragraph("Human Officer Review", styles["H"]))
    if inv.reviews:
        for r in inv.reviews:
            story.append(Paragraph(
                f"<b>{r.decision.replace('_',' ')}</b> by {r.reviewer} — "
                f"AI recommended {r.ai_recommendation or '—'} ({r.ai_risk_level or '—'}); "
                f"override: {'YES' if r.overridden else 'no'}.", body))
            if r.notes:
                story.append(Paragraph(f"Notes: {r.notes}", styles["Small"]))
    else:
        story.append(Paragraph("No officer review recorded yet.", body))
    story.append(Spacer(1, 8))

    # --- Audit trail ---
    story.append(Paragraph("Audit Trail", styles["H"]))
    for a in audit_service.timeline(db, inv.id):
        story.append(Paragraph(f"{_fmt(a.ts)} — {a.event} ({a.actor})", styles["Small"]))

    doc.build(story)
    audit_service.log(db, "REPORT_GENERATED", investigation_id=inv.id,
                      details={"filename": filename})
    return {"filename": filename, "path": str(out_path),
            "relative": f"reports/{filename}"}
