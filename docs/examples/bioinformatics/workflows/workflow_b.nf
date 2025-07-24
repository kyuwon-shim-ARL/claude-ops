#!/usr/bin/env nextflow

/*
 * Workflow B: Count table-based bacterial transcriptome analysis pipeline
 * BA-TR-PIPE-001 - Version 2.0
 */

nextflow.enable.dsl = 2

include { DIFFERENTIAL_EXPRESSION } from '../modules/dge/deseq2.nf'
include { GENOME_ANNOTATION } from '../modules/annotation/prokka.nf'
include { FUNCTIONAL_ENRICHMENT } from '../modules/enrichment/clusterprofiler.nf'

workflow WORKFLOW_B {
    take:
    count_table     // path: counts.tsv
    metadata       // path: metadata.tsv
    contrast       // val: "condition,Treated,Control"
    annotation     // path: annotation.gff (optional)
    reference_genome // path: reference.fasta (optional, used if no annotation)

    main:
    // B-1: Differential Expression Analysis
    DIFFERENTIAL_EXPRESSION(
        count_table,
        metadata,
        contrast
    )
    
    // B-2: Annotation Acquisition
    if (annotation) {
        // Use provided annotation
        final_annotation = annotation
    } else if (reference_genome) {
        // Generate annotation from reference genome
        GENOME_ANNOTATION(reference_genome)
        final_annotation = GENOME_ANNOTATION.out.annotation
    } else {
        error "Either --annotation or --reference_genome must be provided"
    }
    
    // B-3: Functional Enrichment Analysis
    FUNCTIONAL_ENRICHMENT(
        DIFFERENTIAL_EXPRESSION.out.deg_results,
        final_annotation
    )

    emit:
    deg_results = DIFFERENTIAL_EXPRESSION.out.deg_results
    deg_plots = DIFFERENTIAL_EXPRESSION.out.plots
    annotation = final_annotation
    enrichment_results = FUNCTIONAL_ENRICHMENT.out.results
    enrichment_plots = FUNCTIONAL_ENRICHMENT.out.plots
}

workflow {
    // Parameter validation
    if (!params.count_table) {
        error "Please specify --count_table parameter"
    }
    if (!params.metadata) {
        error "Please specify --metadata parameter"
    }
    if (!params.annotation && !params.reference_genome) {
        error "Either --annotation or --reference_genome must be provided"
    }

    // Prepare inputs
    annotation_file = params.annotation ? file(params.annotation) : null
    reference_file = params.reference_genome ? file(params.reference_genome) : null

    // Run workflow
    WORKFLOW_B(
        file(params.count_table),
        file(params.metadata),
        params.contrast ?: "condition,Treated,Control",
        annotation_file,
        reference_file
    )

    // Publish results
    WORKFLOW_B.out.deg_results.view { "DEG analysis completed: $it" }
    WORKFLOW_B.out.enrichment_results.view { "Functional enrichment completed: $it" }
}