"""감성분석 파이프라인 2단계: 로컬 경량 다국어 모델로 1차 분류 + 집계(classify).

TASK-006, doc/CHANGE_REQUEST.md 항목 3. spark-submit이 아니라 plain python으로
실행된다(common/spark_stage.py의 make_python_stage_task, sentiment_pipeline.py
참고) - HuggingFace transformers 로컬 추론은 분산처리가 필요 없는 단일 프로세스
작업이고, Spark UDF로 감싸면 executor마다 모델을 중복 로드하는 오버헤드만 커진다는
매니저 지시("Spark UDF로 넣지 말고 별도 PythonOperator 또는 KubernetesPodOperator
단계로 분리")를 그대로 따랐다.

사용 모델: cardiffnlp/twitter-xlm-roberta-base-sentiment (다국어 지원 경량
사전학습 모델, 긍정/중립/부정 3-way 분류). transformers/torch(CPU 전용
wheel)/sentencepiece/boto3는 develope/spark-jobs/requirements.txt +
Dockerfile에서 이 이미지에 설치해 둔다.

sentiment_ingest.py가 write_raw_json(append)으로 계속 쌓아 온
s3a://datalake/raw/steam/reviews/ 전체를 boto3로 직접 읽는다(SparkSession을 새로
띄우지 않고 plain python에서 MinIO(S3 호환)를 바로 읽기 위함). old_games_pipeline의
bronze/silver가 raw를 append로 누적하고 매 실행마다 전체를 다시 정제하는 것과 동일한
이 프로젝트의 기존 컨벤션이다. 같은 리뷰가 여러 주에 걸쳐 반복 수집될 수 있어
recommendationid 기준으로 dedup한다 - silver.py가 appid 기준 dropDuplicates로 bronze
중복을 없애는 것과 동일한 원칙을 여기서는(별도 bronze/silver 단계 없이) classify
단계 안에서 처리한다.

집계 결과(appid별 positive/negative/neutral/review_count + 대표 샘플 최대 15개)는
고정 MinIO 키(s3a://datalake/interim/sentiment/results.json)에 쓴다. 다음 단계
(Airflow common/sentiment_load.py의 summarize_and_save)가 이 키를 읽어
langgraph-server를 호출하고 postgres에 저장한다.
"""
import json
import os

import boto3

_BUCKET = "datalake"
_RAW_PREFIX = "raw/steam/reviews/"
_RESULTS_KEY = "interim/sentiment/results.json"

MODEL_NAME = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
_MAX_SAMPLES_PER_APPID = 15
# 리뷰가 지나치게 길면(에세이급 장문 리뷰) 토크나이저가 잘라내는데, 분류 전에
# 미리 앞부분만 남겨서 불필요한 토크나이즈 비용/경고를 줄인다. 감성 판단에는
# 보통 앞부분만으로도 충분하다는 경험적 판단.
_MAX_TEXT_LEN = 2000

# cardiffnlp/twitter-xlm-roberta-base-sentiment는 라벨을 "positive"/"neutral"/
# "negative" 문자열로 내놓지만(모델 config의 id2label), transformers/모델 버전에
# 따라 "LABEL_0"/"LABEL_1"/"LABEL_2" 형태로 나올 가능성에도 방어적으로 대응한다
# (카드에 명시된 매핑: 0=negative, 1=neutral, 2=positive).
_LABEL_MAP = {
    "positive": "positive",
    "negative": "negative",
    "neutral": "neutral",
    "label_2": "positive",
    "label_1": "neutral",
    "label_0": "negative",
    "pos": "positive",
    "neg": "negative",
}


def _normalize_label(label: str) -> str:
    return _LABEL_MAP.get((label or "").strip().lower(), "neutral")


def _minio_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )


def _list_raw_review_records(client) -> list[dict]:
    """s3a://datalake/raw/steam/reviews/ 아래 모든 JSON(라인 단위) 파일을 읽어
    레코드 리스트로 합친다. write_raw_json이 spark의 df.write.json으로 쓰기 때문에
    part 파일마다 한 줄에 레코드 하나씩(JSON Lines)이다.
    """
    records: list[dict] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_BUCKET, Prefix=_RAW_PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            body = client.get_object(Bucket=_BUCKET, Key=key)["Body"].read()
            for line in body.decode("utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def _dedup_by_recommendationid(records: list[dict]) -> list[dict]:
    """recommendationid(리뷰 고유 id) 기준으로 중복을 제거한다. id가 없는 레코드는
    (appid, review_text) 조합으로 대신 판별한다(방어적 fallback).
    """
    deduped: dict = {}
    for r in records:
        rid = r.get("recommendationid")
        key = rid if rid else (r.get("appid"), r.get("review_text"))
        deduped[key] = r
    return list(deduped.values())


def _load_classifier():
    from transformers import pipeline

    return pipeline(
        "sentiment-analysis", model=MODEL_NAME, tokenizer=MODEL_NAME, truncation=True
    )


def _pick_samples(samples: list[dict]) -> list[dict]:
    """긍정/부정을 우선 섞고, 자리가 남으면 나머지(긍정/부정 잔여 + 중립)로 채운다
    (매니저 지시: "대표 샘플(긍정/부정 섞어서 최대 15개 정도)").
    """
    positives = [s for s in samples if s["sentiment"] == "positive"]
    negatives = [s for s in samples if s["sentiment"] == "negative"]
    neutrals = [s for s in samples if s["sentiment"] == "neutral"]

    half = _MAX_SAMPLES_PER_APPID // 2
    mixed = positives[:half] + negatives[:half]
    remaining = _MAX_SAMPLES_PER_APPID - len(mixed)
    if remaining > 0:
        leftovers = positives[half:] + negatives[half:] + neutrals
        mixed += leftovers[:remaining]
    return mixed[:_MAX_SAMPLES_PER_APPID]


def main() -> None:
    client = _minio_client()
    records = _dedup_by_recommendationid(_list_raw_review_records(client))

    if not records:
        client.put_object(Bucket=_BUCKET, Key=_RESULTS_KEY, Body=b"[]")
        print("[sentiment_classify] raw 리뷰 레코드 0건, 빈 결과 저장")
        return

    classifier = _load_classifier()

    by_appid: dict[int, dict] = {}
    for r in records:
        appid = r.get("appid")
        if appid is None:
            continue
        text = (r.get("review_text") or "")[:_MAX_TEXT_LEN]
        if not text.strip():
            continue

        result = classifier(text)[0]
        sentiment = _normalize_label(result.get("label"))

        entry = by_appid.setdefault(
            appid,
            {
                "appid": appid,
                "name": r.get("name") or "",
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "review_count": 0,
                "_samples": [],
            },
        )
        entry["review_count"] += 1
        entry[f"{sentiment}_count"] += 1
        entry["_samples"].append({"text": text, "sentiment": sentiment})

    results = []
    for entry in by_appid.values():
        samples = entry.pop("_samples")
        entry["sample_reviews"] = _pick_samples(samples)
        results.append(entry)

    client.put_object(
        Bucket=_BUCKET,
        Key=_RESULTS_KEY,
        Body=json.dumps(results, ensure_ascii=False).encode("utf-8"),
    )
    print(
        f"[sentiment_classify] raw 리뷰 {len(records)}건(dedup 후) -> "
        f"{len(results)}개 appid 집계 완료: {_RESULTS_KEY}"
    )


if __name__ == "__main__":
    main()
