#!/usr/bin/env nextflow

/*
 * Generic Data Analysis Pipeline Template
 * Adaptable for various research domains
 */

nextflow.enable.dsl = 2

include { DATA_PREPROCESSING } from '../modules/preprocessing/clean_data.nf'
include { STATISTICAL_ANALYSIS } from '../modules/analysis/statistics.nf'
include { VISUALIZATION } from '../modules/visualization/plots.nf'
include { GENERATE_REPORT } from '../modules/reporting/report.nf'

workflow DATA_ANALYSIS {
    take:
    input_data      // channel: [ meta, data_files ]
    metadata       // path: metadata file
    analysis_params // val: analysis parameters

    main:
    // Step 1: Data Preprocessing
    DATA_PREPROCESSING(input_data, metadata)
    
    // Step 2: Statistical Analysis
    STATISTICAL_ANALYSIS(
        DATA_PREPROCESSING.out.clean_data,
        analysis_params
    )
    
    // Step 3: Visualization
    VISUALIZATION(
        STATISTICAL_ANALYSIS.out.results,
        metadata
    )
    
    // Step 4: Generate Report
    GENERATE_REPORT(
        STATISTICAL_ANALYSIS.out.results,
        VISUALIZATION.out.plots
    )

    emit:
    results = STATISTICAL_ANALYSIS.out.results
    plots = VISUALIZATION.out.plots
    report = GENERATE_REPORT.out.report
}

workflow {
    // Default parameter validation
    if (!params.input_data) {
        error "Please specify --input_data parameter"
    }
    if (!params.metadata) {
        error "Please specify --metadata parameter"  
    }

    // Create input channels
    data_ch = Channel
        .fromPath(params.input_data)
        .map { file -> [['sample': file.baseName], file] }

    // Run workflow
    DATA_ANALYSIS(
        data_ch,
        file(params.metadata),
        params.analysis_type ?: "standard"
    )

    // Publish results
    DATA_ANALYSIS.out.results.view { "Analysis completed: $it" }
    DATA_ANALYSIS.out.report.view { "Report generated: $it" }
}