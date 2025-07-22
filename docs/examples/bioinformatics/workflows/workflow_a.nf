#!/usr/bin/env nextflow

/*
 * Workflow A: FASTQ-based bacterial transcriptome analysis pipeline
 * BA-TR-PIPE-001 - Version 2.0
 */

nextflow.enable.dsl = 2

include { QC_AND_QUANTIFY } from '../modules/qc/qc_quantify.nf'
include { DIFFERENTIAL_EXPRESSION } from '../modules/dge/deseq2.nf'
include { GENOME_ANNOTATION } from '../modules/annotation/prokka.nf'
include { FUNCTIONAL_ENRICHMENT } from '../modules/enrichment/clusterprofiler.nf'

workflow WORKFLOW_A {
    take:
    fastq_files      // channel: [ meta, [fastq_files] ]
    reference_genome // path: reference.fasta
    metadata        // path: metadata.tsv
    contrast        // val: "condition,Treated,Control"

    main:
    // A-1: QC and Quantification
    QC_AND_QUANTIFY(fastq_files, reference_genome)
    
    // A-2: Differential Expression Analysis
    DIFFERENTIAL_EXPRESSION(
        QC_AND_QUANTIFY.out.counts,
        metadata,
        contrast
    )
    
    // A-3: Genome Annotation
    GENOME_ANNOTATION(reference_genome)
    
    // A-4: Functional Enrichment Analysis
    FUNCTIONAL_ENRICHMENT(
        DIFFERENTIAL_EXPRESSION.out.deg_results,
        GENOME_ANNOTATION.out.annotation
    )

    emit:
    counts = QC_AND_QUANTIFY.out.counts
    deg_results = DIFFERENTIAL_EXPRESSION.out.deg_results
    deg_plots = DIFFERENTIAL_EXPRESSION.out.plots
    annotation = GENOME_ANNOTATION.out.annotation
    enrichment_results = FUNCTIONAL_ENRICHMENT.out.results
    enrichment_plots = FUNCTIONAL_ENRICHMENT.out.plots
    reports = QC_AND_QUANTIFY.out.multiqc_report
}

workflow {
    // Default parameter validation
    if (!params.fastq_dir) {
        error "Please specify --fastq_dir parameter"
    }
    if (!params.reference_genome) {
        error "Please specify --reference_genome parameter"
    }
    if (!params.metadata) {
        error "Please specify --metadata parameter"
    }

    // Create input channels
    fastq_ch = Channel
        .fromFilePairs("${params.fastq_dir}/*_{R1,R2}.fastq.gz", size: 2)
        .map { name, reads -> [['sample': name], reads] }

    // Run workflow
    WORKFLOW_A(
        fastq_ch,
        file(params.reference_genome),
        file(params.metadata),
        params.contrast ?: "condition,Treated,Control"
    )

    // Publish results
    WORKFLOW_A.out.deg_results.view { "DEG analysis completed: $it" }
    WORKFLOW_A.out.enrichment_results.view { "Functional enrichment completed: $it" }
}