# Workflow B 데이터 교체 가이드

이 디렉토리의 템플릿 파일들을 실제 데이터로 교체하여 Workflow B를 실행하세요.

## 교체해야 할 파일들

### 1. `counts.tsv` (필수)
- **형식**: TSV (탭으로 구분)
- **첫 번째 컬럼**: `gene_id` - 유전자 식별자
- **나머지 컬럼**: 각 샘플의 gene count 값
- **예시**:
```
gene_id	sample_A	sample_B	sample_C	sample_D
GENE_001	100	150	120	180
```

### 2. `metadata.tsv` (필수)  
- **형식**: TSV (탭으로 구분)
- **필수 컬럼**:
  - `sample`: 샘플 ID (counts.tsv의 컬럼명과 일치해야 함)
  - `condition`: 실험 조건 (예: Treated, Control)
  - `batch`: 배치 정보 (선택사항, 없으면 제거 가능)
- **예시**:
```
sample	condition	batch
sample_A	Treated	batch_1
sample_B	Control	batch_1
```

### 3. `annotation/annotation.gff` (권장)
- **형식**: GFF3 형식
- **내용**: 유전체 주석 정보 (유전자 위치, 기능 등)
- **만약 없다면**: `annotation/genome.fasta` 파일을 제공하면 자동으로 생성

### 4. `annotation/genome.fasta` (annotation.gff가 없을 때 필수)
- **형식**: FASTA 형식
- **내용**: 참조 유전체 서열

## 실행 방법

데이터 교체 후 다음 명령어로 실행:

```bash
# annotation.gff 파일이 있는 경우
python main.py workflow-b --count-table data/workflow_b/counts.tsv --metadata data/workflow_b/metadata.tsv --annotation data/workflow_b/annotation/annotation.gff

# annotation.gff가 없고 genome.fasta만 있는 경우
python main.py workflow-b --count-table data/workflow_b/counts.tsv --metadata data/workflow_b/metadata.tsv --reference-genome data/workflow_b/annotation/genome.fasta
```

## 주의사항
- `counts.tsv`의 샘플명과 `metadata.tsv`의 샘플명이 정확히 일치해야 합니다
- 컬럼 구분자는 반드시 탭(tab)을 사용하세요
- 파일 인코딩은 UTF-8을 권장합니다