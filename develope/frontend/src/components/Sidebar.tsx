import { useState } from "react";
import type { ReportListItem } from "../types";

interface SidebarProps {
  reports: ReportListItem[];
}

function downloadReport(report: ReportListItem | undefined) {
  if (!report) return;
  // TODO: pdfUrl이 실제 MinIO(reports 버킷) 경로로 채워지면 그대로 다운로드된다.
  window.open(report.pdfUrl, "_blank");
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
              aria-label={`${report.title} 다운로드`}
              style={{
                border: "1px solid var(--color-border)",
                background: "transparent",
                color: "var(--color-text)",
                padding: "4px 8px",
                fontSize: 12,
                cursor: "pointer",
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
          style={{
            width: "100%",
            padding: "8px",
            background: "var(--color-accent)",
            border: "none",
            color: "#12151a",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          다운로드
        </button>
      </div>
    </aside>
  );
}
