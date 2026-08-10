import { useState } from "react";
import { reportDownloadUrl } from "../api";
import type { ReportListItem } from "../types";

interface SidebarProps {
  reports: ReportListItem[];
}

function downloadReport(report: ReportListItem | undefined) {
  if (!report?.pdfUrl) return;
  window.open(reportDownloadUrl(report.pdfUrl), "_blank");
}

export function Sidebar({ reports }: SidebarProps) {
  const [selectedId, setSelectedId] = useState(reports[0]?.id ?? "");

  return (
    <aside
      style={{
        width: 280,
        flexShrink: 0,
        borderLeft: "1px solid var(--color-border)",
        padding: 24,
      }}
    >
      <h2 style={{ fontSize: 14, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-text-muted)", margin: "0 0 16px" }}>
        보고서 목록
      </h2>

      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
        {reports.map((report) => (
          <li
            key={report.id}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 8,
              padding: "8px 10px",
              background: "var(--color-surface)",
              border: "1px solid var(--color-border)",
            }}
          >
            <span style={{ fontSize: 13 }}>{report.title}</span>
            <button
              onClick={() => downloadReport(report)}
              disabled={!report.pdfUrl}
              aria-label={`${report.title} 다운로드`}
              title={report.pdfUrl ? undefined : "아직 PDF로 보관되지 않았습니다"}
              style={{
                border: "1px solid var(--color-border)",
                background: "transparent",
                color: report.pdfUrl ? "var(--color-text)" : "var(--color-text-muted)",
                padding: "4px 8px",
                fontSize: 12,
                cursor: report.pdfUrl ? "pointer" : "not-allowed",
              }}
            >
              ↓
            </button>
          </li>
        ))}
      </ul>

      <div style={{ marginTop: 24, paddingTop: 20, borderTop: "1px solid var(--color-border)" }}>
        <h3 style={{ fontSize: 13, color: "var(--color-text-muted)", margin: "0 0 10px", fontWeight: 400 }}>
          이전 보고서 선택
        </h3>
        <select
          value={selectedId}
          onChange={(event) => setSelectedId(event.target.value)}
          style={{
            width: "100%",
            padding: "8px",
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            color: "var(--color-text)",
            marginBottom: 10,
          }}
        >
          {reports.map((report) => (
            <option key={report.id} value={report.id}>
              {report.title}
            </option>
          ))}
        </select>
        <button
          onClick={() => downloadReport(reports.find((r) => r.id === selectedId))}
          disabled={!reports.find((r) => r.id === selectedId)?.pdfUrl}
          style={{
            width: "100%",
            padding: "8px",
            background: reports.find((r) => r.id === selectedId)?.pdfUrl
              ? "var(--color-accent)"
              : "var(--color-placeholder)",
            border: "none",
            color: "#12151a",
            fontWeight: 600,
            cursor: reports.find((r) => r.id === selectedId)?.pdfUrl ? "pointer" : "not-allowed",
          }}
        >
          다운로드
        </button>
      </div>
    </aside>
  );
}
