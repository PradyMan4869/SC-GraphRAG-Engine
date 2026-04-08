@echo off
REM ============================================================
REM  Download, extract, and preprocess Indian Supreme Court
REM  Judgments from AWS S3.
REM  Bucket: s3://indian-supreme-court-judgments (ap-south-1)
REM  License: CC-BY-4.0  |  No AWS credentials required
REM ============================================================

cd /d "%~dp0.."
call venv\Scripts\activate

REM Download sample: 2023-2025 (for dev/testing)
python src/ingestion/download.py --years 2023 2024 2025

REM Extract and preprocess
python src/ingestion/extract.py --years 2023 2024 2025
python src/ingestion/preprocess.py --years 2023 2024 2025

echo Done.
