import type { NewsArticle, ReportListItem, SentimentReport, WeeklyReport } from "./types";

// 항상 현재 origin 기준 상대경로. nginx(frontend 컨테이너)가 /api/*를
// fastapi-server:8000으로 프록시해준다 (nginx.conf 참고) - 실제 사용자 브라우저든
// PDF 캡처용 헤드리스 브라우저든 항상 같은 방식으로 동작한다.
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${path} -> ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchLatestReport(): Promise<WeeklyReport> {
  return request<WeeklyReport>("/reports/latest");
}

export function fetchReport(id: string): Promise<WeeklyReport> {
  return request<WeeklyReport>(`/reports/${id}`);
}

export function fetchReportList(): Promise<ReportListItem[]> {
  return request<ReportListItem[]>("/reports");
}

export function reportDownloadUrl(pdfUrl: string): string {
  return `${API_BASE}${pdfUrl}`;
}

export function fetchNews(limit = 20, offset = 0): Promise<NewsArticle[]> {
  return request<NewsArticle[]>(`/news?limit=${limit}&offset=${offset}`);
}

export function fetchNewsItem(id: number): Promise<NewsArticle> {
  return request<NewsArticle>(`/news/${id}`);
}

export function fetchSentimentList(): Promise<SentimentReport[]> {
  return request<SentimentReport[]>("/sentiment");
}

export function fetchSentimentItem(appid: number): Promise<SentimentReport> {
  return request<SentimentReport>(`/sentiment/${appid}`);
}
