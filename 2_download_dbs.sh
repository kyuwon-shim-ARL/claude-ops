#!/bin/bash
# Script 2: For downloading databases in parallel
set -e

PROJECT_DIR=~/nf-core-mag-project
CONFIG_FILE=${PROJECT_DIR}/nextflow.config
DUMMY_SAMPLESHEET=${PROJECT_DIR}/dummy_samplesheet.csv

echo "========= [DB] Starting database download process... ========="
echo "This run uses a dummy samplesheet to trigger downloads specified in nextflow.config."

# nextflow.config 에 명시된 DB 경로들이 비어있으므로,
# 이 명령은 실제 DB들을 다운로드하기 시작할 것입니다.
# 가짜 데이터에 대한 분석은 매우 빠르게 끝나거나 사소한 에러로 중단될 수 있지만,
# 그 전에 DB 다운로드라는 주된 목적은 달성됩니다.
nextflow run nf-core/mag -r 3.1.0 \
    -c ${CONFIG_FILE} \
    -profile singularity \
    --input ${DUMMY_SAMPLESHEET} \
    --outdir ${PROJECT_DIR}/dummy_results
    -resume \
    -with-report \
    -with-timeline \
    -with-trace    

echo "========= [DB] Database download process initiated. Check logs for progress. ========="