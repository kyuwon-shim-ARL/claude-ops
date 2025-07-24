"""
Data Preprocessing Module
=========================

This module handles data preprocessing operations for the research pipeline.
Builds on the data collection module to clean, transform, and prepare data for analysis.

Author: Claude Code Automation System
Task: TID-23a5d36f - Task 1.2: 데이터 전처리 모듈 구현
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
import logging
try:
    from .data_collection import DataCollector
except ImportError:
    from data_collection import DataCollector

logger = logging.getLogger(__name__)

class DataPreprocessor:
    """
    Data preprocessing class that handles cleaning, transformation, and preparation.
    """
    
    def __init__(self, base_path: Union[str, Path] = "data/"):
        """
        Initialize the data preprocessor.
        
        Args:
            base_path: Base directory for data files
        """
        self.base_path = Path(base_path)
        self.processed_data = {}
        self.preprocessing_log = []
        
        # Initialize data collector for input data
        self.collector = DataCollector(base_path)
        
    def load_raw_data(self, data_type: str, file_path: str, format_type: str = "csv") -> pd.DataFrame:
        """
        Load raw data using the data collector.
        
        Args:
            data_type: Type identifier for the data
            file_path: Path to the data file
            format_type: File format (csv, tsv)
            
        Returns:
            Loaded raw DataFrame
        """
        logger.info(f"Loading raw data: {data_type} from {file_path}")
        
        if format_type.lower() == "csv":
            df = self.collector.collect_csv_data(file_path, data_type)
        elif format_type.lower() == "tsv":
            df = self.collector.collect_tsv_data(file_path, data_type)
        else:
            raise ValueError(f"Unsupported format: {format_type}")
        
        self._log_operation(f"Loaded {data_type}", f"{len(df)} rows, {len(df.columns)} columns")
        return df
    
    def clean_missing_values(self, df: pd.DataFrame, strategy: str = "drop", 
                           threshold: float = 0.5) -> pd.DataFrame:
        """
        Handle missing values in the dataset.
        
        Args:
            df: Input DataFrame
            strategy: Cleaning strategy ('drop', 'fill_mean', 'fill_median', 'fill_zero')
            threshold: Threshold for dropping columns (fraction of missing values)
            
        Returns:
            Cleaned DataFrame
        """
        logger.info(f"Cleaning missing values using strategy: {strategy}")
        
        initial_shape = df.shape
        
        # Drop columns with too many missing values
        missing_fraction = df.isnull().sum() / len(df)
        cols_to_drop = missing_fraction[missing_fraction > threshold].index
        if len(cols_to_drop) > 0:
            df = df.drop(columns=cols_to_drop)
            logger.info(f"Dropped {len(cols_to_drop)} columns with >{threshold*100}% missing values")
        
        # Handle remaining missing values
        if strategy == "drop":
            df = df.dropna()
        elif strategy == "fill_mean":
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].mean())
        elif strategy == "fill_median":
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].median())
        elif strategy == "fill_zero":
            df = df.fillna(0)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
        
        final_shape = df.shape
        self._log_operation(
            "Missing value cleaning", 
            f"{initial_shape} → {final_shape}, strategy: {strategy}"
        )
        
        return df
    
    def remove_duplicates(self, df: pd.DataFrame, subset: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Remove duplicate rows from the dataset.
        
        Args:
            df: Input DataFrame
            subset: List of columns to consider for duplicates
            
        Returns:
            DataFrame with duplicates removed
        """
        logger.info("Removing duplicate rows")
        
        initial_count = len(df)
        df = df.drop_duplicates(subset=subset)
        final_count = len(df)
        
        removed = initial_count - final_count
        self._log_operation(
            "Duplicate removal", 
            f"Removed {removed} duplicates ({initial_count} → {final_count})"
        )
        
        return df
    
    def normalize_data(self, df: pd.DataFrame, method: str = "minmax", 
                      columns: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Normalize numerical data.
        
        Args:
            df: Input DataFrame
            method: Normalization method ('minmax', 'zscore', 'robust')
            columns: Specific columns to normalize (default: all numeric)
            
        Returns:
            DataFrame with normalized data
        """
        logger.info(f"Normalizing data using method: {method}")
        
        df_normalized = df.copy()
        
        if columns is None:
            columns = df.select_dtypes(include=[np.number]).columns
        
        if method == "minmax":
            df_normalized[columns] = (df[columns] - df[columns].min()) / (df[columns].max() - df[columns].min())
        elif method == "zscore":
            df_normalized[columns] = (df[columns] - df[columns].mean()) / df[columns].std()
        elif method == "robust":
            df_normalized[columns] = (df[columns] - df[columns].median()) / (df[columns].quantile(0.75) - df[columns].quantile(0.25))
        else:
            raise ValueError(f"Unknown normalization method: {method}")
        
        self._log_operation(
            "Data normalization", 
            f"Applied {method} normalization to {len(columns)} columns"
        )
        
        return df_normalized
    
    def encode_categorical(self, df: pd.DataFrame, method: str = "onehot", 
                          columns: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Encode categorical variables.
        
        Args:
            df: Input DataFrame
            method: Encoding method ('onehot', 'label')
            columns: Specific columns to encode (default: all object/categorical)
            
        Returns:
            DataFrame with encoded categorical variables
        """
        logger.info(f"Encoding categorical variables using method: {method}")
        
        df_encoded = df.copy()
        
        if columns is None:
            columns = df.select_dtypes(include=['object', 'category']).columns
        
        if method == "onehot":
            df_encoded = pd.get_dummies(df_encoded, columns=columns, prefix=columns)
        elif method == "label":
            from sklearn.preprocessing import LabelEncoder
            le = LabelEncoder()
            for col in columns:
                df_encoded[col] = le.fit_transform(df_encoded[col].astype(str))
        else:
            raise ValueError(f"Unknown encoding method: {method}")
        
        self._log_operation(
            "Categorical encoding", 
            f"Applied {method} encoding to {len(columns)} columns"
        )
        
        return df_encoded
    
    def detect_outliers(self, df: pd.DataFrame, method: str = "iqr", 
                       columns: Optional[List[str]] = None) -> Dict[str, List[int]]:
        """
        Detect outliers in the dataset.
        
        Args:
            df: Input DataFrame
            method: Outlier detection method ('iqr', 'zscore')
            columns: Specific columns to check (default: all numeric)
            
        Returns:
            Dictionary with column names and outlier indices
        """
        logger.info(f"Detecting outliers using method: {method}")
        
        if columns is None:
            columns = df.select_dtypes(include=[np.number]).columns
        
        outliers = {}
        
        for col in columns:
            if method == "iqr":
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                outlier_mask = (df[col] < lower_bound) | (df[col] > upper_bound)
            elif method == "zscore":
                z_scores = np.abs((df[col] - df[col].mean()) / df[col].std())
                outlier_mask = z_scores > 3
            else:
                raise ValueError(f"Unknown outlier detection method: {method}")
            
            outliers[col] = df[outlier_mask].index.tolist()
        
        total_outliers = sum(len(indices) for indices in outliers.values())
        self._log_operation(
            "Outlier detection", 
            f"Found {total_outliers} outliers across {len(columns)} columns using {method}"
        )
        
        return outliers
    
    def preprocess_pipeline(self, data_type: str, file_path: str, 
                           format_type: str = "csv",
                           pipeline_config: Optional[Dict] = None) -> pd.DataFrame:
        """
        Execute a complete preprocessing pipeline.
        
        Args:
            data_type: Type identifier for the data
            file_path: Path to the data file
            format_type: File format
            pipeline_config: Configuration for preprocessing steps
            
        Returns:
            Fully preprocessed DataFrame
        """
        logger.info(f"Starting preprocessing pipeline for {data_type}")
        
        # Default pipeline configuration
        if pipeline_config is None:
            pipeline_config = {
                "clean_missing": {"strategy": "fill_mean", "threshold": 0.5},
                "remove_duplicates": True,
                "normalize": {"method": "minmax"},
                "encode_categorical": {"method": "onehot"},
                "detect_outliers": {"method": "iqr"}
            }
        
        # Load raw data
        df = self.load_raw_data(data_type, file_path, format_type)
        
        # Apply preprocessing steps
        if "clean_missing" in pipeline_config:
            df = self.clean_missing_values(df, **pipeline_config["clean_missing"])
        
        if pipeline_config.get("remove_duplicates", False):
            df = self.remove_duplicates(df)
        
        if "encode_categorical" in pipeline_config:
            df = self.encode_categorical(df, **pipeline_config["encode_categorical"])
        
        if "normalize" in pipeline_config:
            df = self.normalize_data(df, **pipeline_config["normalize"])
        
        if "detect_outliers" in pipeline_config:
            outliers = self.detect_outliers(df, **pipeline_config["detect_outliers"])
            logger.info(f"Outlier summary: {sum(len(v) for v in outliers.values())} total outliers detected")
        
        # Store processed data
        self.processed_data[data_type] = df
        
        logger.info(f"Preprocessing pipeline completed for {data_type}")
        return df
    
    def export_preprocessed_data(self, data_type: str, output_path: str) -> str:
        """
        Export preprocessed data to file.
        
        Args:
            data_type: Type of data to export
            output_path: Output file path
            
        Returns:
            Path to exported file
        """
        if data_type not in self.processed_data:
            raise ValueError(f"No preprocessed data found for {data_type}")
        
        df = self.processed_data[data_type]
        df.to_csv(output_path, index=False)
        
        logger.info(f"Exported preprocessed data to {output_path}")
        self._log_operation("Data export", f"Exported {data_type} to {output_path}")
        
        return output_path
    
    def generate_preprocessing_report(self, output_path: str = "preprocessing_report.txt") -> str:
        """
        Generate a detailed preprocessing report.
        
        Args:
            output_path: Path for the report file
            
        Returns:
            Path to the generated report
        """
        report_content = f"""
Data Preprocessing Report
=========================
Generated by: Data Preprocessing Module (TID-23a5d36f)
Total Processed Datasets: {len(self.processed_data)}

Preprocessing Operations:
"""
        
        for operation in self.preprocessing_log:
            report_content += f"- {operation}\n"
        
        report_content += f"""

Processed Dataset Summary:
"""
        
        for data_type, df in self.processed_data.items():
            report_content += f"""
{data_type}:
  Rows: {len(df)}
  Columns: {len(df.columns)}
  Memory Usage: {df.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB
  Data Types: {dict(df.dtypes.value_counts())}
"""
        
        # Write report to file
        report_path = Path(output_path)
        with open(report_path, 'w') as f:
            f.write(report_content)
        
        logger.info(f"Preprocessing report exported to {report_path}")
        
        return str(report_path)
    
    def _log_operation(self, operation: str, details: str):
        """Log preprocessing operations for reporting."""
        log_entry = f"{operation}: {details}"
        self.preprocessing_log.append(log_entry)
        logger.info(log_entry)


def main():
    """
    Example usage of the DataPreprocessor.
    """
    preprocessor = DataPreprocessor()
    
    try:
        # Run preprocessing pipeline on sample data
        if Path("data/sample_data.csv").exists():
            processed_df = preprocessor.preprocess_pipeline(
                data_type="sample",
                file_path="sample_data.csv",
                format_type="csv"
            )
            
            print(f"Preprocessing completed!")
            print(f"Original shape: {preprocessor.collector.collected_data['sample'].shape}")
            print(f"Processed shape: {processed_df.shape}")
            
            # Export processed data
            preprocessor.export_preprocessed_data("sample", "processed_sample_data.csv")
            
            # Generate report
            report_path = preprocessor.generate_preprocessing_report()
            print(f"Report generated: {report_path}")
        
    except Exception as e:
        logger.error(f"Preprocessing failed: {e}")
        print(f"Error: {e}")


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    main()