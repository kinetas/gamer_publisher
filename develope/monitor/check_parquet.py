"""datalake의 parquet 결과를 눈으로 확인하기 위한 스크립트.

호스트(Windows)에서 바로 실행한다 (docker-compose.yml에 minio가 9000 포트로
호스트에 노출돼 있어서 localhost:9000으로 접근 가능). 자격증명은 develope/.env에서 읽는다.

사용법:
    pip install -r requirements.txt
    python check_parquet.py                              # 기본값: silver/steamspy_all
    python check_parquet.py --path bronze/steamspy_all
"""
import argparse
from pathlib import Path

import pandas as pd

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="silver/steamspy_all", help="datalake 버킷 내부 경로")
    parser.add_argument("--rows", type=int, default=20, help="출력할 샘플 행 수")
    args = parser.parse_args()

    env = load_env(ENV_PATH)
    storage_options = {
        "key": env["MINIO_ROOT_USER"],
        "secret": env["MINIO_ROOT_PASSWORD"],
        "client_kwargs": {"endpoint_url": "http://localhost:9000"},
    }

    df = pd.read_parquet(f"s3://datalake/{args.path}/", storage_options=storage_options)

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)

    print(f"path   : datalake/{args.path}/")
    print(f"rows   : {len(df)}")
    print(f"columns: {list(df.columns)}")
    print()
    print(df.head(args.rows).to_string())

    if "ccu" in df.columns:
        print()
        print(f"ccu min/mean/max: {df['ccu'].min()} / {df['ccu'].mean():.1f} / {df['ccu'].max()}")

    if {"positive", "negative"} <= set(df.columns):
        violations = df[df["positive"] < df["negative"]]
        print(f"positive < negative 위반 row 수: {len(violations)} (0이어야 정상)")


if __name__ == "__main__":
    main()
