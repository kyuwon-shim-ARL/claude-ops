process QC_AND_QUANTIFY {
    tag "$meta.sample"
    label 'process_high'
    
    publishDir "${params.outdir}/qc", mode: 'copy', pattern: "*{fastqc,multiqc}*"
    publishDir "${params.outdir}/counts", mode: 'copy', pattern: "counts.tsv"

    input:
    tuple val(meta), path(reads)
    path reference_genome

    output:
    path "counts.tsv", emit: counts
    path "*fastqc*", emit: fastqc
    path "multiqc_report.html", emit: multiqc_report
    path "versions.yml", emit: versions

    script:
    def prefix = meta.sample
    """
    # QC with FastQC
    fastqc -t ${task.cpus} ${reads[0]} ${reads[1]}

    # Trim with Trimmomatic
    trimmomatic PE -threads ${task.cpus} \\
        ${reads[0]} ${reads[1]} \\
        ${prefix}_R1_trimmed.fastq.gz ${prefix}_R1_unpaired.fastq.gz \\
        ${prefix}_R2_trimmed.fastq.gz ${prefix}_R2_unpaired.fastq.gz \\
        ILLUMINACLIP:TruSeq3-PE.fa:2:30:10 LEADING:3 TRAILING:3 SLIDINGWINDOW:4:15 MINLEN:36

    # Build STAR index if not exists
    if [ ! -d "star_index" ]; then
        mkdir star_index
        STAR --runMode genomeGenerate \\
            --genomeDir star_index \\
            --genomeFastaFiles ${reference_genome} \\
            --runThreadN ${task.cpus} \\
            --genomeSAindexNbases 10
    fi

    # Align with STAR
    STAR --runMode alignReads \\
        --genomeDir star_index \\
        --readFilesIn ${prefix}_R1_trimmed.fastq.gz ${prefix}_R2_trimmed.fastq.gz \\
        --readFilesCommand zcat \\
        --runThreadN ${task.cpus} \\
        --outSAMtype BAM SortedByCoordinate \\
        --outFileNamePrefix ${prefix}_

    # Count features
    featureCounts -T ${task.cpus} -p -a ${reference_genome}.gff -o ${prefix}_counts.txt ${prefix}_Aligned.sortedByCoord.out.bam

    # Combine counts from all samples (simplified for single sample)
    tail -n +3 ${prefix}_counts.txt | cut -f1,7- > counts.tsv

    # Generate MultiQC report
    multiqc .

    # Version information
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        fastqc: \$(fastqc --version | sed 's/FastQC v//')
        trimmomatic: \$(trimmomatic -version 2>&1 | head -1 | cut -d' ' -f2)
        star: \$(STAR --version | head -1)
        featurecounts: \$(featureCounts -v 2>&1 | head -1 | cut -d' ' -f2)
        multiqc: \$(multiqc --version | sed 's/multiqc, version //')
    END_VERSIONS
    """

    stub:
    """
    touch counts.tsv
    touch multiqc_report.html
    touch versions.yml
    """
}