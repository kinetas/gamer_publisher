import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { fetchReport } from "../api";
import { ReportDocument } from "../components/ReportDocument";
import type { WeeklyReport } from "../types";

/** 헤더/사이드바/푸터 없는 순수 리포트 페이지. fastapi-server의 /reports/archive-current가
 * 헤드리스 브라우저로 이 페이지를 열어 PDF로 캡처한다. */
export default function PrintReport() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchReport(id)
      .then(setReport)
      .catch(() => setError("리포트를 불러오지 못했습니다."));
  }, [id]);

  if (error) return <p style={{ padding: 40 }}>{error}</p>;
  if (!report) return <p style={{ padding: 40 }}>불러오는 중...</p>;

  return (
    <div style={{ padding: "40px 0" }}>
      <ReportDocument report={report} />
    </div>
  );
}
