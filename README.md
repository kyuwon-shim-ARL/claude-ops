# TARA Ocean Metagenomic Analysis with nf-core/mag

This project analyzes TARA ocean metagenomic samples using the nf-core/mag pipeline for genome assembly, binning, and taxonomic classification.

## Overview

- **Pipeline**: nf-core/mag v3.1.0
- **Container System**: Singularity/Apptainer
- **Samples**: TARA ocean metagenomic data (ERR599039, ERR599042)
- **Analysis Focus**: Metagenome assembly, genome binning, taxonomic classification

## Key Files

- `nextflow.config` - Pipeline configuration with resource settings
- `run_nf_mag_public.sh` - Main execution script
- `2_download_dbs.sh` - Database download automation
- `sample_sheet_public.csv` - Sample metadata for pipeline input
- `CLAUDE.md` - Detailed project documentation and instructions

## Quick Start

1. **Setup databases** (first time only):
   ```bash
   ./2_download_dbs.sh
   ```

2. **Run the pipeline**:
   ```bash
   ./run_nf_mag_public.sh
   ```

## Data

- **Input**: Paired-end FASTQ files from TARA ocean samples
- **Output**: Assembly contigs, genome bins, taxonomic classifications, quality reports

## Pipeline Workflow

1. **QC**: FastQC, fastp, PhiX removal
2. **Assembly**: MEGAHIT and SPAdes
3. **Binning**: CONCOCT, MaxBin2, MetaBAT2
4. **Quality Assessment**: BUSCO, QUAST
5. **Taxonomy**: GTDB-Tk classification
6. **Annotation**: Prodigal, Prokka
7. **Reporting**: MultiQC integration

## Resource Requirements

- **Memory**: 150GB for SPAdes assembly
- **Storage**: >100GB for databases and results
- **Compute**: Multi-core recommended (16+ CPUs)

## Results

Results are generated in `results_public/` with comprehensive quality reports available in `results_public/multiqc/multiqc_report.html`.

## Configuration

The pipeline is configured for:
- High-memory SPAdes assembly
- BUSCO prokaryotic lineage auto-detection
- Singularity container execution
- Resume capability for interrupted runs

For detailed configuration options, see `nextflow.config` and `CLAUDE.md`.