import logging
import os

import boto3
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

app = FastAPI(title="gamer_publisher API")

# A4 물리 페이지 여백. 프론트 쪽 .page-sheet는 인쇄 시 padding 0/width 100%로
# 재정의되므로(global.css) 종이 여백은 전부 여기서만 담당한다 - 한 곳만 바꾸면
# 모든 섹션/페이지에 동일하게 적용된다.
PDF_PAGE_MARGIN = {"top": "20mm", "bottom": "20mm", "left": "15mm", "right": "15mm"}
PDF_FOOTER_TEMPLATE = """
<div style="width:100%; font-size:10px; font-family:monospace; text-align:right; padding:0 15mm; color:#888;">
  PAGE <span class="pageNumber"></span> / <span class="totalPages"></span>
</div>
"""

DATABASE_URL = os.environ.get("DATABASE_URL")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://frontend")
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY")
MINIO_REPORTS_BUCKET = os.environ.get("MINIO_REPORTS_BUCKET", "reports")


def _db_conn():
    return psycopg2.connect(DATABASE_URL)


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
    )


def _row_to_report(row: dict) -> dict:
    content = row["content"]
    return {
        "date": row["report_date"].isoformat(),
        "oldIntroductions": content.get("old_introductions", []),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _row_to_news(row: dict) -> dict:
    return {
        "id": row["id"],
        "source": row["source"],
        "title": row["title"],
        "excerpt": row["excerpt"],
        "link": row["link"],
        "imageUrl": row["image_url"],
        "pubDate": row["pub_date"].isoformat() if row["pub_date"] else None,
        "appid": row["appid"],
    }


def _row_to_sentiment(row: dict) -> dict:
    return {
        "appid": row["appid"],
        "name": row["name"],
        "positiveCount": row["positive_count"],
        "negativeCount": row["negative_count"],
        "neutralCount": row["neutral_count"],
        "reviewCount": row["review_count"],
        "summary": row["summary"],
        "generatedAt": row["generated_at"].isoformat(),
    }


@app.get("/news")
def list_news(limit: int = 20, offset: int = 0) -> list[dict]:
    conn = _db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM game_news ORDER BY pub_date DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [_row_to_news(row) for row in rows]


@app.get("/news/{news_id}")
def get_news(news_id: int) -> dict:
    conn = _db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM game_news WHERE id = %s", (news_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="news not found")
    return _row_to_news(row)


@app.get("/sentiment")
def list_sentiment() -> list[dict]:
    conn = _db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM sentiment_reports ORDER BY generated_at DESC")
            rows = cur.fetchall()
    finally:
        conn.close()
    return [_row_to_sentiment(row) for row in rows]


@app.get("/sentiment/{appid}")
def get_sentiment(appid: int) -> dict:
    conn = _db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM sentiment_reports WHERE appid = %s", (appid,))
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="sentiment report not found")
    return _row_to_sentiment(row)


@app.get("/reports/latest")
def latest_report() -> dict:
    conn = _db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM weekly_reports ORDER BY report_date DESC LIMIT 1")
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="no reports yet")
    return _row_to_report(row)


@app.get("/reports")
def list_reports() -> list[dict]:
    conn = _db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, report_date, pdf_path FROM weekly_reports ORDER BY report_date DESC")
            rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {
            "id": str(row["id"]),
            "date": row["report_date"].isoformat(),
            "title": f"{row['report_date'].isoformat()} Report",
            "pdfUrl": f"/reports/{row['id']}/download" if row["pdf_path"] else None,
        }
        for row in rows
    ]


@app.get("/reports/{report_id}")
def get_report(report_id: int) -> dict:
    conn = _db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM weekly_reports WHERE id = %s", (report_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")
    return _row_to_report(row)


@app.get("/reports/{report_id}/download")
def download_report(report_id: int) -> StreamingResponse:
    conn = _db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT pdf_path FROM weekly_reports WHERE id = %s", (report_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None or not row["pdf_path"]:
        raise HTTPException(status_code=404, detail="pdf not archived yet")

    obj = _s3_client().get_object(Bucket=MINIO_REPORTS_BUCKET, Key=row["pdf_path"])
    return StreamingResponse(obj["Body"], media_type="application/pdf")


async def _render_report_pdf(report_id: str) -> bytes:
    """헤드리스 Chromium으로 프론트 /print/:id 페이지를 PDF로 캡처한다.

    브라우저 launch 이후 어느 단계에서 실패하든(페이지 로드 실패, 프론트 쪽
    데이터 fetch 에러, 타임아웃 등) finally에서 반드시 browser.close()가
    돌아가도록 해서, 한 번 실패했다고 Chromium 프로세스가 좀비로 남아
    다음 호출들까지 연쇄로 실패시키는 일이 없게 한다.
    """
    async with async_playwright() as playwright:
        # --no-sandbox: 이 컨테이너는 root로 돌고 전용 seccomp/유저 네임스페이스
        #   격리가 없어 Chromium 자체 샌드박스가 기동 단계에서 거부당해 죽는 경우가
        #   있다 (headless 서버에서 흔한 증상). --disable-dev-shm-usage: 도커 기본
        #   /dev/shm(64MB)이 작아 탭이 크래시하는 걸 방지 - 둘 다 Playwright/Puppeteer가
        #   도커 환경에 공식적으로 권장하는 플래그.
        browser = await playwright.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        try:
            page = await browser.new_page()
            page.set_default_timeout(30_000)
            await page.goto(f"{FRONTEND_BASE_URL}/print/{report_id}", wait_until="domcontentloaded")
            # PrintReport.tsx가 로딩/성공/실패를 data-print-status 속성 하나로
            # 알려준다 - networkidle처럼 "네트워크가 조용해졌을 것"이라는 간접
            # 신호에 기대지 않고, 실제로 렌더링할 데이터가 다 갖춰졌는지를 직접 확인한다.
            await page.wait_for_selector('[data-print-status="ready"], [data-print-status="error"]')
            status = await page.get_attribute("[data-print-status]", "data-print-status")
            if status != "ready":
                raise RuntimeError(f"frontend reported data-print-status={status!r}")

            # page.pdf()는 기본적으로 print 미디어를 자동 적용하지 않는다(screen 그대로
            # 렌더링) — 이걸 안 하면 global.css의 @media print 블록이 통째로 무시돼서,
            # 사용자가 직접 브라우저로 인쇄(window.print() — 항상 print 미디어 적용됨)한
            # 결과와 페이지 구성이 달라진다.
            await page.emulate_media(media="print")
            return await page.pdf(
                format="A4",
                print_background=True,
                margin=PDF_PAGE_MARGIN,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=PDF_FOOTER_TEMPLATE,
            )
        finally:
            await browser.close()


@app.post("/reports/archive-current")
async def archive_current_report() -> dict:
    """다음 주 파이프라인이 새 리포트를 만들기 직전에 호출된다. 그때까지 '최신'이던
    리포트(pdf_path가 아직 없는 것)를 헤드리스 브라우저로 프론트 /print/:id 페이지를
    캡처해 PDF로 떠서 MinIO에 저장하고 pdf_path를 채운다.
    """
    conn = _db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, report_date FROM weekly_reports WHERE pdf_path IS NULL "
                "ORDER BY report_date DESC LIMIT 1"
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        return {"status": "skipped", "reason": "no un-archived report"}

    report_id = row["id"]
    report_date = row["report_date"].isoformat()

    try:
        pdf_bytes = await _render_report_pdf(report_id)
    except (PlaywrightTimeoutError, PlaywrightError, RuntimeError) as exc:
        logger.exception("PDF 캡처 실패 (report_id=%s)", report_id)
        raise HTTPException(status_code=502, detail=f"PDF 생성 실패: {exc}") from exc

    pdf_path = f"{report_date}.pdf"
    _s3_client().put_object(
        Bucket=MINIO_REPORTS_BUCKET, Key=pdf_path, Body=pdf_bytes, ContentType="application/pdf"
    )

    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE weekly_reports SET pdf_path = %s WHERE id = %s", (pdf_path, report_id))
        conn.commit()
    finally:
        conn.close()

    return {"status": "archived", "report_id": report_id, "pdf_path": pdf_path}

    return {"status": "archived", "report_id": report_id, "pdf_path": pdf_path}
