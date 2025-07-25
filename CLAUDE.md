# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an nf-core/mag (metagenomics assembly and genome binning) pipeline project for analyzing metagenomic data from TARA ocean samples. The project uses Nextflow with Singularity/Apptainer containers and focuses on genome assembly, binning, and taxonomic classification.

## Key Commands

### Running the Pipeline

**Main pipeline execution:**
```bash
./run_nf_mag_public.sh
```

**Full command structure:**
```bash
nextflow run nf-core/mag -r 3.1.0 \
    -c nextflow.config \
    -profile singularity \
    --input sample_sheet_public.csv \
    --outdir results_public \
    --busco_auto_lineage_prok \
    -resume \
    -with-report \
    -with-timeline \
    -with-trace
```

**Database download (run first for new setup):**
```bash
./2_download_dbs.sh
```

### Important Parameters

- **Input format**: CSV samplesheet with columns: `sample,short_reads_1,short_reads_2`
- **Main config**: `nextflow.config` (contains database paths, resource allocation)
- **Profile**: Always use `-profile singularity` for containerized execution
- **Resume capability**: Always include `-resume` to restart from checkpoints
- **Reporting**: Include `-with-report`, `-with-timeline`, `-with-trace` for execution monitoring

### Resource Configuration

The `nextflow.config` file contains critical resource settings:
- SPAdes processes: 150GB memory, 16 CPUs
- Singularity cache: `/home/kyuwon/.singularity/cache`
- BUSCO staging mode: `copy` (required for this setup)

## Architecture and Workflow

### Pipeline Structure

The nf-core/mag pipeline performs these main steps:
1. **QC_shortreads**: Quality control with FastQC, fastp, PhiX removal
2. **Assembly**: MEGAHIT and SPAdes assembly 
3. **GenomeBinning**: CONCOCT, MaxBin2, MetaBAT2 binning
4. **QC**: BUSCO and QUAST quality assessment
5. **Taxonomy**: GTDB-Tk taxonomic classification
6. **Annotation**: Prodigal gene calling, Prokka annotation
7. **MultiQC**: Consolidated quality reports

### Directory Structure

```
├── data/                    # Input FASTQ files
├── results_public/          # Main pipeline outputs
├── work/                    # Nextflow working directory (cacheable)
├── nextflow.config          # Pipeline configuration
├── sample_sheet_public.csv  # Input sample metadata
├── run_nf_mag_public.sh     # Main execution script
└── 2_download_dbs.sh        # Database download script
```

### Key Output Directories

- `results_public/QC_shortreads/`: Read quality control results
- `results_public/Assembly/`: Assembled contigs (MEGAHIT, SPAdes)
- `results_public/GenomeBinning/`: Genome bins and quality metrics
- `results_public/Taxonomy/`: GTDB-Tk taxonomic classifications
- `results_public/multiqc/`: Comprehensive quality report
- `results_public/pipeline_info/`: Execution reports and parameters

### Database Requirements

Key databases (auto-downloaded if paths not specified):
- **BUSCO**: `/db/tool_specific_db/busco/v5` (configured)
- **GTDB-Tk**: Auto-download (commented paths available)
- **CheckM**: Auto-download (commented paths available)
- **Kraken2**: Auto-download (commented paths available)

## Sample Data

The project uses TARA ocean metagenomic samples:
- `TARA_ERR599039`: Paired-end reads in `data/ERR599039_*.fastq.gz`
- `TARA_ERR599042`: Paired-end reads in `data/ERR599042_*.fastq.gz`

## Important Notes

### Resource Management
- SPAdes assembly requires high memory (150GB configured)
- Use `-resume` to restart from failed steps without recomputation
- Singularity containers cached in `/home/kyuwon/.singularity/cache`

### Database Management
- Run `2_download_dbs.sh` before first execution to populate databases
- Database paths in `nextflow.config` can be uncommented once downloaded
- BUSCO database path is pre-configured to avoid repeated downloads

### Execution Monitoring
- HTML reports generated in `results_public/pipeline_info/`
- MultiQC report provides comprehensive quality overview
- Use `-with-trace` for detailed process monitoring

### Common Issues
- SPAdes may fail with insufficient memory - adjust in `nextflow.config`
- Database downloads can be large - ensure adequate storage
- Always use `singularity` profile for reproducible containerized execution