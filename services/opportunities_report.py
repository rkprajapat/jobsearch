from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_PROJECT_DATA = Path(__file__).parent.parent / "project_data"
_DEFAULT_CLUSTERS_FILE = _PROJECT_DATA / "clusters.json"
_DEFAULT_REPORT_FILE = _PROJECT_DATA / "clusters_report.pdf"


class ClusterPDFReportService:
    def __init__(self, base_path: Path | None = None) -> None:
        self._base_path = base_path or _PROJECT_DATA
        self._styles = getSampleStyleSheet()
        self._title_style = ParagraphStyle(
            "ClusterReportTitle",
            parent=self._styles["Heading1"],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0f766e"),
            spaceAfter=6,
        )
        self._meta_style = ParagraphStyle(
            "ClusterReportMeta",
            parent=self._styles["BodyText"],
            fontSize=9,
            textColor=colors.HexColor("#4b5563"),
            spaceAfter=6,
        )
        self._card_heading_style = ParagraphStyle(
            "ClusterCardHeading",
            parent=self._styles["Heading3"],
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#111827"),
            spaceAfter=4,
        )
        self._body_style = ParagraphStyle(
            "ClusterBody",
            parent=self._styles["BodyText"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#111827"),
            spaceAfter=4,
        )

    def _read_clusters_payload(self, clusters_file: Path) -> dict:
        if not clusters_file.exists():
            raise FileNotFoundError(
                f"Cluster file not found at {clusters_file}. Run JD clustering first."
            )

        with open(clusters_file, "r", encoding="utf-8") as file:
            payload = json.load(file)

        if not isinstance(payload, dict) or "clusters" not in payload:
            raise ValueError(
                "Cluster file does not have the expected format. "
                "Expected top-level object with 'clusters'."
            )

        return payload

    def _format_generated_at(self, generated_at: str | None) -> str:
        if not generated_at:
            return "Unknown"

        try:
            parsed = datetime.fromisoformat(generated_at)
            return parsed.strftime("%Y-%m-%d %H:%M:%S %Z") or generated_at
        except ValueError:
            return generated_at

    def _build_overview_table(self, payload: dict) -> Table:
        clusters = payload.get("clusters", [])
        data = [
            ["Detected clusters", str(len(clusters))],
            ["Configured max k", str(payload.get("max_k", "n/a"))],
            ["Effective k", str(payload.get("effective_k", "n/a"))],
        ]
        table = Table(data, colWidths=[48 * mm, 120 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f9fafb")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ]
            )
        )
        return table

    def _build_opportunities_table(self, opportunities: list[dict], limit: int = 12) -> Table:
        rows: list[list[str]] = [["Designation", "Opportunity ID"]]
        if not opportunities:
            rows.append(["No opportunities attached.", "n/a"])
        else:
            for opportunity in opportunities[:limit]:
                designation = str(opportunity.get("designation", "Unknown role"))
                opportunity_id = str(opportunity.get("id", "n/a"))
                rows.append([designation, opportunity_id])

        table = Table(rows, colWidths=[132 * mm, 36 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#374151")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return table

    def _build_cluster_block(self, cluster: dict) -> KeepTogether:
        cluster_id = str(cluster.get("cluster_id", "n/a"))
        total = str(cluster.get("total_opportunities", 0))
        summary = str(cluster.get("summary_keywords", "No summary available."))
        keywords = cluster.get("keywords", [])
        opportunities = cluster.get("opportunities", [])

        keywords_line = ", ".join(str(keyword) for keyword in keywords[:24])
        if not keywords_line:
            keywords_line = "No keywords available."

        block = [
            Paragraph(f"Cluster {cluster_id} ({total} opportunities)", self._card_heading_style),
            Paragraph(f"<b>Summary:</b> {summary}", self._body_style),
            Paragraph(f"<b>Top Keywords:</b> {keywords_line}", self._body_style),
            Spacer(1, 2 * mm),
            self._build_opportunities_table(opportunities),
            Spacer(1, 6 * mm),
        ]
        return KeepTogether(block)

    def generate_pdf_report(
        self,
        clusters_file: Path | None = None,
        output_file: Path | None = None,
    ) -> Path:
        clusters_path = clusters_file or _DEFAULT_CLUSTERS_FILE
        report_path = output_file or _DEFAULT_REPORT_FILE

        payload = self._read_clusters_payload(clusters_path)
        generated_at = self._format_generated_at(payload.get("generated_at"))

        report_path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(report_path),
            pagesize=A4,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            title="Job Description Clusters Report",
            author="JobSearch",
        )

        elements = [
            Paragraph("Job Description Clusters Report", self._title_style),
            Paragraph(f"Generated at: {generated_at}", self._meta_style),
            Spacer(1, 2 * mm),
            self._build_overview_table(payload),
            Spacer(1, 6 * mm),
        ]

        for cluster in payload.get("clusters", []):
            elements.append(self._build_cluster_block(cluster))

        doc.build(elements)
        return report_path
