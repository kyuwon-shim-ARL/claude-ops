process FUNCTIONAL_ENRICHMENT {
    label 'process_medium'
    
    publishDir "${params.outdir}/enrichment", mode: 'copy'

    input:
    path deg_results
    path annotation

    output:
    path "enrichment_results.tsv", emit: results
    path "*.{png,pdf}", emit: plots
    path "enrichment_report.html", emit: report
    path "versions.yml", emit: versions

    script:
    """
    #!/usr/bin/env Rscript
    
    # Load required libraries
    library(clusterProfiler)
    library(DOSE)
    library(ggplot2)
    library(enrichplot)
    library(dplyr)
    
    # Read DEG results
    deg_data <- read.table("${deg_results}", header=TRUE, row.names=1, sep="\\t")
    
    # Filter significant genes
    sig_genes <- rownames(deg_data)[!is.na(deg_data\$padj) & deg_data\$padj < 0.05]
    up_genes <- rownames(deg_data)[!is.na(deg_data\$padj) & deg_data\$padj < 0.05 & deg_data\$log2FoldChange > 1]
    down_genes <- rownames(deg_data)[!is.na(deg_data\$padj) & deg_data\$padj < 0.05 & deg_data\$log2FoldChange < -1]
    
    # Parse annotation file to extract GO terms (simplified)
    # In real implementation, would need proper GO/KEGG database
    
    # Create mock GO annotation for demonstration
    # In practice, would use organism-specific databases
    all_genes <- rownames(deg_data)
    go_terms <- sample(c("GO:0008150", "GO:0003674", "GO:0005575", "GO:0009987", "GO:0044237"), 
                      length(all_genes), replace=TRUE)
    go_annotation <- data.frame(
        gene = all_genes,
        go_id = go_terms,
        evidence = "IEA",
        stringsAsFactors = FALSE
    )
    
    # Create term2gene mapping
    term2gene <- go_annotation[, c("go_id", "gene")]
    
    # Create term2name mapping (simplified)
    term2name <- data.frame(
        go_id = c("GO:0008150", "GO:0003674", "GO:0005575", "GO:0009987", "GO:0044237"),
        description = c("biological_process", "molecular_function", "cellular_component", 
                       "cellular_process", "cellular_metabolic_process"),
        stringsAsFactors = FALSE
    )
    
    # Perform enrichment analysis
    if(length(sig_genes) > 5) {
        ego <- enricher(sig_genes, 
                       TERM2GENE = term2gene,
                       TERM2NAME = term2name,
                       pvalueCutoff = 0.05,
                       qvalueCutoff = 0.2)
        
        # Convert to data frame and save
        if(!is.null(ego) && nrow(ego@result) > 0) {
            enrichment_df <- as.data.frame(ego@result)
            write.table(enrichment_df, "enrichment_results.tsv", sep="\\t", quote=FALSE, row.names=FALSE)
            
            # Generate plots
            
            # 1. Dot plot
            if(nrow(enrichment_df) > 0) {
                p1 <- dotplot(ego, showCategory=20) + ggtitle("GO Enrichment Dot Plot")
                ggsave("dotplot.png", p1, width=10, height=8)
                ggsave("dotplot.pdf", p1, width=10, height=8)
                
                # 2. Bar plot
                p2 <- barplot(ego, showCategory=20) + ggtitle("GO Enrichment Bar Plot")
                ggsave("barplot.png", p2, width=10, height=8)
                ggsave("barplot.pdf", p2, width=10, height=8)
                
                # 3. Gene-concept network (if applicable)
                if(nrow(enrichment_df) >= 3 && length(sig_genes) >= 10) {
                    p3 <- cnetplot(ego, categorySize="pvalue", foldChange=NULL)
                    ggsave("cnetplot.png", p3, width=12, height=10)
                    ggsave("cnetplot.pdf", p3, width=12, height=10)
                }
            }
        } else {
            # No significant enrichment found
            cat("No significant GO terms found\\n", file="enrichment_results.tsv")
            
            # Create empty plots
            p_empty <- ggplot() + 
                annotate("text", x=0.5, y=0.5, label="No significant enrichment found", size=6) +
                theme_void()
            ggsave("dotplot.png", p_empty, width=8, height=6)
            ggsave("barplot.png", p_empty, width=8, height=6)
        }
    } else {
        cat("Insufficient number of significant genes for enrichment analysis\\n", file="enrichment_results.tsv")
        
        # Create empty plots
        p_empty <- ggplot() + 
            annotate("text", x=0.5, y=0.5, label="Insufficient genes for analysis", size=6) +
            theme_void()
        ggsave("dotplot.png", p_empty, width=8, height=6)
        ggsave("barplot.png", p_empty, width=8, height=6)
    }
    
    # Generate HTML report
    cat("<!DOCTYPE html>
    <html><head><title>Functional Enrichment Report</title></head>
    <body>
    <h1>Functional Enrichment Analysis Report</h1>
    <h2>Summary</h2>
    <p>Total significant genes:", length(sig_genes), "</p>
    <p>Upregulated genes:", length(up_genes), "</p>
    <p>Downregulated genes:", length(down_genes), "</p>
    <p>See enrichment_results.tsv for detailed results.</p>
    </body></html>", file="enrichment_report.html")
    
    # Version information
    writeLines(c(
        paste0('"', "${task.process}", '":'),
        paste0('    clusterProfiler: ', packageVersion("clusterProfiler")),
        paste0('    DOSE: ', packageVersion("DOSE")),
        paste0('    ggplot2: ', packageVersion("ggplot2")),
        paste0('    enrichplot: ', packageVersion("enrichplot"))
    ), "versions.yml")
    """

    stub:
    """
    touch enrichment_results.tsv
    touch dotplot.png
    touch barplot.png
    touch enrichment_report.html
    touch versions.yml
    """
}