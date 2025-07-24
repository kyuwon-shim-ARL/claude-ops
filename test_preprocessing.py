#!/usr/bin/env python3
"""
Test Data Preprocessing Module
==============================
"""

import sys
import os
sys.path.append('/home/kyuwon/MC_test_ops/src/modules')

from data_preprocessing import DataPreprocessor
import pandas as pd

def create_test_data():
    """Create test data for preprocessing"""
    test_data = {
        'id': range(1, 21),
        'value_a': [1.2, 2.5, None, 4.1, 5.3, 6.7, 7.8, 8.9, 9.1, 10.2,
                   11.5, 12.3, 13.7, 14.2, 15.8, 16.4, 17.9, 18.1, 19.6, 20.3],
        'value_b': [10, 15, 20, 25, 30, 35, 40, 45, 50, 55,
                   60, 65, 70, 75, 80, 85, 90, 95, 100, 999],  # 999 is outlier
        'category': ['A', 'B', 'A', 'C', 'B', 'A', 'C', 'A', 'B', 'C',
                    'A', 'B', 'C', 'A', 'B', 'C', 'A', 'B', 'C', 'A'],
        'group': ['X', 'Y', 'X', 'Y', 'X', 'Y', 'X', 'Y', 'X', 'Y',
                 'X', 'Y', 'X', 'Y', 'X', 'Y', 'X', 'Y', 'X', 'Y']
    }
    
    df = pd.DataFrame(test_data)
    df.to_csv('data/test_sample.csv', index=False)
    print("✅ Created test data: data/test_sample.csv")
    return df

def main():
    # Create test data
    os.makedirs('data', exist_ok=True)
    original_df = create_test_data()
    
    # Initialize preprocessor
    preprocessor = DataPreprocessor()
    
    try:
        print("\n🔄 Starting preprocessing pipeline...")
        
        # Run preprocessing pipeline
        processed_df = preprocessor.preprocess_pipeline(
            data_type="test_sample",
            file_path="test_sample.csv",
            format_type="csv",
            pipeline_config={
                "clean_missing": {"strategy": "fill_mean", "threshold": 0.5},
                "remove_duplicates": True,
                "encode_categorical": {"method": "onehot"},
                "normalize": {"method": "minmax"},
                "detect_outliers": {"method": "iqr"}
            }
        )
        
        print(f"\n✅ Preprocessing completed!")
        print(f"📊 Original shape: {original_df.shape}")
        print(f"📊 Processed shape: {processed_df.shape}")
        print(f"📊 Original columns: {list(original_df.columns)}")
        print(f"📊 Processed columns: {list(processed_df.columns)}")
        
        # Export processed data
        output_file = preprocessor.export_preprocessed_data("test_sample", "processed_test_data.csv")
        print(f"💾 Exported to: {output_file}")
        
        # Generate report
        report_path = preprocessor.generate_preprocessing_report("test_preprocessing_report.txt")
        print(f"📋 Report generated: {report_path}")
        
        # Show sample of processed data
        print(f"\n📋 Sample of processed data:")
        print(processed_df.head())
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()