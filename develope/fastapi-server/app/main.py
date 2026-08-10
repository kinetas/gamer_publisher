import os

import boto3
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from playwright.async_api import async_playwright

app = FastAPI(title="gamer_publisher API")

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
        "recentReplays": content.get("recent_replays", []),
        "recentNew": content.get("recent_new", []),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


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

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.goto(f"{FRONTEND_BASE_URL}/print/{report_id}", wait_until="networkidle")
        pdf_bytes = await page.pdf(format="A4", print_background=True)
        await browser.close()

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
