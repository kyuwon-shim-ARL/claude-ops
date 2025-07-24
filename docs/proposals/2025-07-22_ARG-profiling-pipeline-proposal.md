### **[Tech Spec] 박테리아 전사체 분석 파이프라인 명세서**

- **Ticket ID:** BA-TR-PIPE-001
    
- **Version:** 2.0
    
- **Date:** 2025-07-22
    
- **목표:** 원본 데이터(.fastq) 또는 유전자 발현량 데이터(Count Table)를 입력받아, 차등 발현 유전자(DEG) 분석 및 기능 농축 분석을 수행하는 표준화된 워크플로우 실행
    

---

### **## 워크플로우 A: 원본 데이터(.fastq) 기반 파이프라인**

#### **INPUTS**

1. **Raw Reads:** 샘플 별 `.fastq.gz` 파일
    
2. **Reference Genome:** 분석 대상 박테리아의 유전체 서열 (`.fasta`)
    
3. **Metadata:** 샘플 정보 및 실험 디자인을 포함하는 메타데이터 파일 (`.tsv`)
    

|Column|Description|Example|
|---|---|---|
|`sample`|샘플 ID|`sample_A`|
|`condition`|비교할 실험 조건 (처리군, 대조군 등)|`Treated`|
|`batch`|배치 효과가 있다면 명시 (선택 사항)|`batch_1`|

Export to Sheets

---

#### **PROCESS & TOOLCHAIN**

1. **[A-1] QC 및 정량화 (Quantification)**
    
    - **Tool:** 사내 Nextflow 스크립트 (wrapper for `FastQC`, `Trimmomatic`, `STAR`, `featureCounts`)
        
    - **Process:** Raw read QC → Trimming → Alignment → Gene count 정량화
        
    - **Output:** 유전자 발현량 매트릭스 (**`counts.tsv`**)
        
2. **[A-2] 차등 발현 유전자 분석 (DGE)**
    
    - **Tool:** `nf-core/differentialabundance`
        
    - **Process:** `DESeq2` 또는 `edgeR`을 이용한 통계 분석
        
    - **Inputs:**
        
        - `--input`: `A-1`에서 생성된 `counts.tsv`
            
        - `--phenotype`: 프로젝트 메타데이터 `.tsv`
            
        - `--contrast`: `condition,Treated,Control` (예시)
            
    - **Output:** **DEG 목록 테이블** 및 분석 리포트
        
3. **[A-3] 유전체 기능 주석 (Annotation)**
    
    - **Tool:** `Prokka` 또는 `Bakta`
        
    - **Process:** 참조 유전체 서열에 기능 정보(GO, KEGG 등) 주석 추가
        
    - **Input:** 프로젝트 참조 유전체 `.fasta`
        
    - **Output:** **주석 파일 (`.gff`)**
        
4. **[A-4] 기능 농축 분석 (Functional Enrichment)**
    
    - **Tool:** 사내 `R` 스크립트 (`clusterProfiler` 기반)
        
    - **Process:** Fisher's Exact Test 등을 이용한 통계적 농축 분석
        
    - **Inputs:**
        
        - DEG 목록 (from `A-2`)
            
        - 주석 파일 (from `A-3`)
            
    - **Output:** **기능 농축 분석 결과 테이블** 및 시각화 자료
        

---

#### **FINAL OUTPUTS (산출물)**

- DGE 분석 결과 테이블 (`.tsv`)
    
- 시각화 자료: Volcano plot, MA plot, PCA plot, Heatmap (`.png`, `.pdf`)
    
- 기능 농축 분석(GO/KEGG) 결과 테이블 (`.tsv`)
    
- 기능 농축 분석 시각화 자료: Dot plot, Bar plot, Enrichment map (`.png`, `.pdf`)
    
- 종합 분석 리포트 (`MultiQC`, `nf-core` 리포트)
    

---

---

### **## 워크플로우 B: Count Table 기반 파이프라인**

#### **INPUTS**

1. **Count Table:** 유전자 발현량 매트릭스 (`.tsv`)
    
2. **Metadata:** 샘플 정보 및 실험 디자인 파일 (`.tsv`)
    
3. **Annotation (아래 두 파일 중 최소 하나 필수):**
    
    - 유전체 주석 파일 (`.gff`) **(권장)**
        
    - 참조 유전체 서열 (`.fasta`)
        

---

#### **PROCESS & TOOLCHAIN**

1. **[B-1] 차등 발현 유전자 분석 (DGE)**
    
    - **Tool:** `nf-core/differentialabundance`
        
    - **Process:** `DESeq2` 또는 `edgeR`을 이용한 통계 분석
        
    - **Inputs:**
        
        - `--input`: 제공된 `counts.tsv`
            
        - `--phenotype`: 제공된 메타데이터 `.tsv`
            
        - `--contrast`: `condition,Treated,Control` (예시)
            
    - **Output:** **DEG 목록 테이블** 및 분석 리포트
        
2. **[B-2] 유전체 주석 정보 확보 (Annotation Acquisition)**
    
    - **Process:**
        
        - 제공된 `.gff` 파일이 있는지 확인하고 사용합니다.
            
        - 만약 `.gff` 파일이 없고 `.fasta` 파일만 있다면, **워크플로우 A의 `[A-3]` 프로세스를 실행하여 `.gff` 파일을 생성**합니다.
            
    - **Output:** 분석에 사용할 **주석 파일 (`.gff`)**
        
3. **[B-3] 기능 농축 분석 (Functional Enrichment)**
    
    - **Tool:** 사내 `R` 스크립트 (`clusterProfiler` 기반)
        
    - **Process:** Fisher's Exact Test 등을 이용한 통계적 농축 분석
        
    - **Inputs:**
        
        - DEG 목록 (from `B-1`)
            
        - 주석 파일 (from `B-2`)
            
    - **Output:** **기능 농축 분석 결과 테이블** 및 시각화 자료
        

---

#### **FINAL OUTPUTS (산출물)**

- 워크플로우 A와 동일한 형식의 산출물 일체