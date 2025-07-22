process DATA_PREPROCESSING {
    tag "$meta.sample"
    label 'process_medium'
    
    publishDir "${params.outdir}/preprocessing", mode: 'copy'

    input:
    tuple val(meta), path(data_file)
    path metadata

    output:
    tuple val(meta), path("*_cleaned.csv"), emit: clean_data
    path "preprocessing_report.html", emit: report
    path "versions.yml", emit: versions

    script:
    def prefix = meta.sample
    """
    #!/usr/bin/env python3
    
    import pandas as pd
    import numpy as np
    
    # Read input data
    data = pd.read_csv("${data_file}")
    metadata_df = pd.read_csv("${metadata}")
    
    # Basic data cleaning
    # Remove missing values
    data_cleaned = data.dropna()
    
    # Remove duplicates
    data_cleaned = data_cleaned.drop_duplicates()
    
    # Save cleaned data
    data_cleaned.to_csv("${prefix}_cleaned.csv", index=False)
    
    # Generate preprocessing report
    report_html = f'''
    <!DOCTYPE html>
    <html><head><title>Data Preprocessing Report</title></head>
    <body>
    <h1>Data Preprocessing Report</h1>
    <h2>Summary</h2>
    <p>Original records: {len(data)}</p>
    <p>Cleaned records: {len(data_cleaned)}</p>
    <p>Removed records: {len(data) - len(data_cleaned)}</p>
    </body></html>
    '''
    
    with open("preprocessing_report.html", "w") as f:
        f.write(report_html)
    
    # Version information
    with open("versions.yml", "w") as f:
        f.write('"${task.process}":\\n')
        f.write('    pandas: "2.0.0"\\n')
        f.write('    numpy: "1.24.0"\\n')
    """

    stub:
    """
    touch ${prefix}_cleaned.csv
    touch preprocessing_report.html
    touch versions.yml
    """
}