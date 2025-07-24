#!/usr/bin/env nextflow

/*
 * Sample Nextflow pipeline for bioinformatics research
 */

params.input_dir = "${baseDir}/data"
params.output_dir = "${baseDir}/results"

workflow {
    log.info """
    ========================================
    Bioinformatics Pipeline
    ========================================
    Input directory : ${params.input_dir}
    Output directory: ${params.output_dir}
    ========================================
    """
    
    // Add your pipeline processes here
}