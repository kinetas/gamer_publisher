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
  /** Steam header_image URL. 취재 실패 등으로 없으면 빈 문자열. */
  image: string;
}

export interface WeeklyReport {
  /** YYYY-MM-DD */
  date: string;
  oldIntroductions: GameEntry[];
}

export interface ReportListItem {
  id: string;
  /** YYYY-MM-DD */
  date: string;
  title: string;
  /** 아직 PDF로 archive 안 됐으면(가장 최근 리포트는 보통 그렇다) null */
  pdfUrl: string | null;
}

export interface NewsArticle {
  id: number;
  source: string;
  title: string;
  excerpt: string | null;
  link: string | null;
  imageUrl: string | null;
  pubDate: string | null;
  appid: number | null;
}

export interface SentimentReport {
  appid: number;
  name: string;
  positiveCount: number;
  negativeCount: number;
  neutralCount: number;
  reviewCount: number;
  summary: string | null;
  generatedAt: string;
}
