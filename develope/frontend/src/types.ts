export interface GameEntry {
  appid: number;
  name: string;
  developer: string;
  publisher: string;
  positive: number;
  negative: number;
  ccu: number;
  /** langgraph-server가 생성할 추천 사유/설명 문구. 지금은 mock 텍스트. */
  description: string;
}

export interface WeeklyReport {
  /** YYYY-MM-DD */
  date: string;
  oldIntroductions: GameEntry[];
  recentReplays: GameEntry[];
  recentNew: GameEntry[];
}

export interface ReportListItem {
  id: string;
  /** YYYY-MM-DD */
  date: string;
  title: string;
  /** MinIO에 저장된 PDF 경로 (reports 버킷) */
  pdfUrl: string;
}
