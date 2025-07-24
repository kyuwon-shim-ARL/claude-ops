process STATISTICAL_ANALYSIS {
    label 'process_medium'
    
    publishDir "${params.outdir}/analysis", mode: 'copy'

    input:
    tuple val(meta), path(clean_data)
    val analysis_params

    output:
    path "statistical_results.csv", emit: results
    path "*.{png,pdf}", emit: plots
    path "analysis_report.html", emit: report
    path "versions.yml", emit: versions

    script:
    """
    #!/usr/bin/env python3
    
    import pandas as pd
    import numpy as np
    import matplotlib.pyplot as plt
    import seaborn as sns
    from scipy import stats
    
    # Read cleaned data
    data = pd.read_csv("${clean_data}")
    
    # Perform basic statistical analysis
    results = {}
    
    # Descriptive statistics
    desc_stats = data.describe()
    results['descriptive_stats'] = desc_stats.to_dict()
    
    # Correlation analysis (if multiple numeric columns)
    numeric_cols = data.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) > 1:
        correlation = data[numeric_cols].corr()
        
        # Create correlation heatmap
        plt.figure(figsize=(10, 8))
        sns.heatmap(correlation, annot=True, cmap='coolwarm', center=0)
        plt.title('Correlation Matrix')
        plt.tight_layout()
        plt.savefig('correlation_heatmap.png', dpi=300)
        plt.savefig('correlation_heatmap.pdf')
        plt.close()
    
    # Basic distribution plots
    for col in numeric_cols[:5]:  # Limit to first 5 numeric columns
        plt.figure(figsize=(8, 6))
        sns.histplot(data[col], kde=True)
        plt.title(f'Distribution of {col}')
        plt.tight_layout()
        plt.savefig(f'distribution_{col}.png', dpi=300)
        plt.close()
    
    # Save statistical results
    results_df = pd.DataFrame([
        {'metric': 'total_samples', 'value': len(data)},
        {'metric': 'numeric_features', 'value': len(numeric_cols)},
        {'metric': 'categorical_features', 'value': len(data.columns) - len(numeric_cols)}
    ])
    
    results_df.to_csv('statistical_results.csv', index=False)
    
    # Generate analysis report
    report_html = f'''
    <!DOCTYPE html>
    <html><head><title>Statistical Analysis Report</title></head>
    <body>
    <h1>Statistical Analysis Report</h1>
    <h2>Dataset Overview</h2>
    <p>Total samples: {len(data)}</p>
    <p>Numeric features: {len(numeric_cols)}</p>
    <p>Categorical features: {len(data.columns) - len(numeric_cols)}</p>
    
    <h2>Descriptive Statistics</h2>
    {desc_stats.to_html()}
    </body></html>
    '''
    
    with open("analysis_report.html", "w") as f:
        f.write(report_html)
    
    # Version information
    with open("versions.yml", "w") as f:
        f.write('"${task.process}":\\n')
        f.write('    pandas: "2.0.0"\\n')
        f.write('    numpy: "1.24.0"\\n')
        f.write('    matplotlib: "3.7.0"\\n')
        f.write('    seaborn: "0.12.0"\\n')
        f.write('    scipy: "1.10.0"\\n')
    """

    stub:
    """
    touch statistical_results.csv
    touch correlation_heatmap.png
    touch analysis_report.html
    touch versions.yml
    """
}