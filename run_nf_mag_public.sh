#!/bin/bash
set -e

# 프로젝트 및 설정 파일 경로
PROJECT_DIR=~/nf-core-mag-project
CONFIG_FILE=${PROJECT_DIR}/nextflow.config

# 데이터베이스 경로 변수 설정
BUSCO_DB_PATH="/db/tool_specific_db/busco/v5"

# Nextflow 실행
nextflow run nf-core/mag -r 3.1.0 \
    -c ${CONFIG_FILE} \
    -profile singularity \
    --input ${PROJECT_DIR}/sample_sheet_public_small.csv \
    --outdir ${PROJECT_DIR}/results_public_busco_full_db_hard_copy \
    --busco_auto_lineage_prok \
    -name small_sample_test_BUSCO_full_db_hard_copy_3 \
    -resume \
    -with-report \
    -with-timeline \
    --skip_spadeshybrid \
    --skip_spades \
    -with-trace