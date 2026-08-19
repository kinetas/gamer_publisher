import type { SentimentReport } from "../types";

interface SentimentCardProps {
  report: SentimentReport;
}

function formatGeneratedAt(generatedAt: string): string {
  const parsed = new Date(generatedAt);
  if (Number.isNaN(parsed.getTime())) return generatedAt;
  return parsed.toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SentimentCard({ report }: SentimentCardProps) {
  const total = report.positiveCount + report.negativeCount + report.neutralCount;
  const positivePct = total > 0 ? (report.positiveCount / total) * 100 : 0;
  const negativePct = total > 0 ? (report.negativeCount / total) * 100 : 0;
  const neutralPct = total > 0 ? (report.neutralCount / total) * 100 : 0;

  return (
    <div
      style={{
        padding: 16,
        border: "1px solid var(--color-border)",
        background: "var(--color-surface)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: 12,
          marginBottom: 12,
        }}
      >
        <h4 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>{report.name}</h4>
        <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
          리뷰 {report.reviewCount.toLocaleString("ko-KR")}건
        </span>
      </div>

      <div
        style={{
          display: "flex",
          height: 8,
          width: "100%",
          overflow: "hidden",
          background: "var(--color-surface-raised)",
          marginBottom: 8,
        }}
      >
        {total > 0 ? (
          <>
            <div style={{ width: `${positivePct}%`, background: "var(--color-positive)" }} />
            <div style={{ width: `${neutralPct}%`, background: "var(--color-text-muted)" }} />
            <div style={{ width: `${negativePct}%`, background: "var(--color-negative)" }} />
          </>
        ) : null}
      </div>

      <div
        style={{
          display: "flex",
          gap: 16,
          fontSize: 12,
          color: "var(--color-text-muted)",
          marginBottom: 12,
        }}
      >
        <span style={{ color: "var(--color-positive)" }}>긍정 {report.positiveCount.toLocaleString("ko-KR")}</span>
        <span>중립 {report.neutralCount.toLocaleString("ko-KR")}</span>
        <span style={{ color: "var(--color-negative)" }}>부정 {report.negativeCount.toLocaleString("ko-KR")}</span>
      </div>

      <p
        style={{
          margin: "0 0 8px",
          fontSize: 13,
          lineHeight: 1.6,
          color: "var(--color-text)",
        }}
      >
        {report.summary ?? "아직 요약이 생성되지 않았습니다."}
      </p>

      <p style={{ margin: 0, fontSize: 11, color: "var(--color-text-muted)" }}>
        분석 생성 시각: {formatGeneratedAt(report.generatedAt)}
      </p>
    </div>
  );
}
