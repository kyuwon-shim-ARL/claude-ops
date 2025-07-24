process GENOME_ANNOTATION {
    label 'process_medium'
    
    publishDir "${params.outdir}/annotation", mode: 'copy'

    input:
    path reference_genome

    output:
    path "annotation.gff", emit: annotation
    path "annotation/*", emit: all_files
    path "versions.yml", emit: versions

    script:
    def prefix = reference_genome.baseName
    """
    # Run Prokka annotation
    prokka \\
        --outdir annotation \\
        --prefix ${prefix} \\
        --kingdom Bacteria \\
        --cpus ${task.cpus} \\
        --force \\
        ${reference_genome}

    # Copy main annotation file
    cp annotation/${prefix}.gff annotation.gff

    # Version information
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        prokka: \$(prokka --version 2>&1 | head -1 | sed 's/prokka //')
    END_VERSIONS
    """

    stub:
    """
    mkdir -p annotation
    touch annotation.gff
    touch annotation/prokka.gff
    touch annotation/prokka.gbk
    touch annotation/prokka.faa
    touch versions.yml
    """
}