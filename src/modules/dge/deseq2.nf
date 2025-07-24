process DIFFERENTIAL_EXPRESSION {
    label 'process_medium'
    
    publishDir "${params.outdir}/dge", mode: 'copy'

    input:
    path count_table
    path metadata
    val contrast

    output:
    path "deg_results.tsv", emit: deg_results
    path "*.{png,pdf}", emit: plots
    path "dge_report.html", emit: report
    path "versions.yml", emit: versions

    script:
    """
    #!/usr/bin/env Rscript
    
    # Load required libraries
    library(DESeq2)
    library(ggplot2)
    library(pheatmap)
    library(RColorBrewer)
    library(plotly)
    
    # Read input data
    counts <- read.table("${count_table}", header=TRUE, row.names=1, sep="\\t")
    metadata <- read.table("${metadata}", header=TRUE, row.names=1, sep="\\t")
    
    # Parse contrast
    contrast_parts <- strsplit("${contrast}", ",")[[1]]
    contrast_col <- contrast_parts[1]
    treatment <- contrast_parts[2]
    control <- contrast_parts[3]
    
    # Ensure sample order matches
    metadata <- metadata[colnames(counts), , drop=FALSE]
    
    # Create DESeq2 object
    dds <- DESeqDataSetFromMatrix(
        countData = counts,
        colData = metadata,
        design = as.formula(paste("~", contrast_col))
    )
    
    # Filter low counts
    dds <- dds[rowSums(counts(dds)) >= 10, ]
    
    # Run DESeq2 analysis
    dds <- DESeq(dds)
    
    # Get results
    res <- results(dds, contrast = c(contrast_col, treatment, control))
    res_df <- as.data.frame(res)
    res_df <- res_df[order(res_df\$padj), ]
    
    # Write results
    write.table(res_df, "deg_results.tsv", sep="\\t", quote=FALSE, row.names=TRUE)
    
    # Generate plots
    
    # 1. PCA plot
    rld <- rlog(dds, blind=FALSE)
    pca_data <- plotPCA(rld, intgroup=contrast_col, returnData=TRUE)
    percentVar <- round(100 * attr(pca_data, "percentVar"))
    
    p1 <- ggplot(pca_data, aes(PC1, PC2, color=group)) +
        geom_point(size=3) +
        xlab(paste0("PC1: ", percentVar[1], "% variance")) +
        ylab(paste0("PC2: ", percentVar[2], "% variance")) +
        ggtitle("PCA Plot") +
        theme_minimal()
    ggsave("pca_plot.png", p1, width=8, height=6)
    ggsave("pca_plot.pdf", p1, width=8, height=6)
    
    # 2. Volcano plot
    res_df\$significance <- "NS"
    res_df\$significance[res_df\$padj < 0.05 & res_df\$log2FoldChange > 1] <- "Up"
    res_df\$significance[res_df\$padj < 0.05 & res_df\$log2FoldChange < -1] <- "Down"
    
    p2 <- ggplot(res_df, aes(x=log2FoldChange, y=-log10(padj), color=significance)) +
        geom_point(alpha=0.7) +
        scale_color_manual(values=c("Up"="red", "Down"="blue", "NS"="grey")) +
        geom_vline(xintercept=c(-1, 1), linetype="dashed") +
        geom_hline(yintercept=-log10(0.05), linetype="dashed") +
        ggtitle("Volcano Plot") +
        theme_minimal()
    ggsave("volcano_plot.png", p2, width=8, height=6)
    ggsave("volcano_plot.pdf", p2, width=8, height=6)
    
    # 3. MA plot
    p3 <- ggplot(res_df, aes(x=baseMean, y=log2FoldChange, color=significance)) +
        geom_point(alpha=0.7) +
        scale_x_log10() +
        scale_color_manual(values=c("Up"="red", "Down"="blue", "NS"="grey")) +
        geom_hline(yintercept=0, linetype="dashed") +
        ggtitle("MA Plot") +
        theme_minimal()
    ggsave("ma_plot.png", p3, width=8, height=6)
    ggsave("ma_plot.pdf", p3, width=8, height=6)
    
    # 4. Heatmap of top 50 DEGs
    top_genes <- head(rownames(res_df)[!is.na(res_df\$padj) & res_df\$padj < 0.05], 50)
    if(length(top_genes) > 0) {
        heatmap_data <- assay(rld)[top_genes, ]
        png("heatmap.png", width=800, height=1000)
        pheatmap(heatmap_data, 
                scale="row",
                clustering_distance_rows="correlation",
                clustering_distance_cols="correlation",
                color=colorRampPalette(c("blue", "white", "red"))(50))
        dev.off()
        
        pdf("heatmap.pdf", width=8, height=10)
        pheatmap(heatmap_data, 
                scale="row",
                clustering_distance_rows="correlation",
                clustering_distance_cols="correlation",
                color=colorRampPalette(c("blue", "white", "red"))(50))
        dev.off()
    }
    
    # Generate HTML report
    cat("<!DOCTYPE html>
    <html><head><title>DGE Analysis Report</title></head>
    <body>
    <h1>Differential Gene Expression Analysis Report</h1>
    <h2>Summary</h2>
    <p>Total genes tested:", nrow(res_df), "</p>
    <p>Significant genes (p.adj < 0.05):", sum(res_df\$padj < 0.05, na.rm=TRUE), "</p>
    <p>Upregulated genes:", sum(res_df\$significance == 'Up', na.rm=TRUE), "</p>
    <p>Downregulated genes:", sum(res_df\$significance == 'Down', na.rm=TRUE), "</p>
    </body></html>", file="dge_report.html")
    
    # Version information
    writeLines(c(
        paste0('"', "${task.process}", '":'),
        paste0('    DESeq2: ', packageVersion("DESeq2")),
        paste0('    ggplot2: ', packageVersion("ggplot2")),
        paste0('    pheatmap: ', packageVersion("pheatmap"))
    ), "versions.yml")
    """

    stub:
    """
    touch deg_results.tsv
    touch pca_plot.png
    touch volcano_plot.png
    touch ma_plot.png
    touch heatmap.png
    touch dge_report.html
    touch versions.yml
    """
}