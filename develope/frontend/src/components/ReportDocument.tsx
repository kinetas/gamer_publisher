import type { WeeklyReport } from "../types";
import { PageSheet } from "./PageSheet";
import { GameGrid } from "./GameGrid";
import { GameDetailRow } from "./GameDetailRow";

interface ReportDocumentProps {
  report: WeeklyReport;
}

export function ReportDocument({ report }: ReportDocumentProps) {
  return (
    <div>
      <PageSheet>
        <div style={{ marginBottom: 40 }}>
          <div style={{ fontSize: 28, fontWeight: 700, fontFamily: "var(--font-mono)" }}>
            {report.date}
          </div>
          <div
            style={{
              fontSize: 44,
              fontWeight: 800,
              letterSpacing: "0.04em",
              color: "var(--color-accent)",
            }}
          >
            REPORT
          </div>
        </div>

        <GameGrid title="명작 아카이브" games={report.oldIntroductions} />
      </PageSheet>

      <PageSheet breakBefore>
        <h2
          style={{
            fontSize: 20,
            fontWeight: 700,
            margin: "0 0 24px",
            paddingBottom: 12,
            borderBottom: "2px solid var(--color-accent)",
          }}
        >
          명작 아카이브
        </h2>
        {report.oldIntroductions.map((game) => (
          <div key={game.appid} className="print-row">
            <GameDetailRow game={game} />
          </div>
        ))}
      </PageSheet>
    </div>
  );
}
