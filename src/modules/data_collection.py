"""
Data Collection Module
======================

This module handles data collection from various sources for the research pipeline.
Supports CSV, TSV, and metadata file formats with validation.

Author: Claude Code Automation System
Task: TID-23a5d36f - Task 1.1: 데이터 수집 모듈 구현
"""

import pandas as pd
import os
from pathlib import Path
from typing import Dict, List, Optional, Union
import logging

logger = logging.getLogger(__name__)

class DataCollector:
    """
    Data collection class that handles multiple data sources and formats.
    """
    
    def __init__(self, base_path: Union[str, Path] = "data/"):
        """
        Initialize the data collector.
        
        Args:
            base_path: Base directory for data files
        """
        self.base_path = Path(base_path)
        self.collected_data = {}
        self.metadata = {}
        
    def collect_csv_data(self, file_path: str, data_type: str = "default") -> pd.DataFrame:
        """
        Collect data from CSV files.
        
        Args:
            file_path: Path to the CSV file
            data_type: Type identifier for the data
            
        Returns:
            Loaded DataFrame
        """
        full_path = self.base_path / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"Data file not found: {full_path}")
            
        logger.info(f"Collecting CSV data from {full_path}")
        
        # Load CSV with appropriate settings
        df = pd.read_csv(full_path)
        
        # Store in collected data
        self.collected_data[data_type] = df
        
        # Log collection statistics
        logger.info(f"Collected {len(df)} rows, {len(df.columns)} columns for {data_type}")
        
        return df
    
    def collect_tsv_data(self, file_path: str, data_type: str = "tsv_data") -> pd.DataFrame:
        """
        Collect data from TSV files.
        
        Args:
            file_path: Path to the TSV file
            data_type: Type identifier for the data
            
        Returns:
            Loaded DataFrame
        """
        full_path = self.base_path / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"Data file not found: {full_path}")
            
        logger.info(f"Collecting TSV data from {full_path}")
        
        # Load TSV with tab separator
        df = pd.read_csv(full_path, sep='\t')
        
        # Store in collected data
        self.collected_data[data_type] = df
        
        logger.info(f"Collected {len(df)} rows, {len(df.columns)} columns for {data_type}")
        
        return df
    
    def collect_metadata(self, metadata_path: str) -> Dict:
        """
        Collect metadata information.
        
        Args:
            metadata_path: Path to metadata file
            
        Returns:
            Metadata dictionary
        """
        full_path = self.base_path / metadata_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {full_path}")
            
        logger.info(f"Collecting metadata from {full_path}")
        
        # Load metadata based on file extension
        if full_path.suffix.lower() in ['.csv', '.tsv']:
            sep = '\t' if full_path.suffix.lower() == '.tsv' else ','
            metadata_df = pd.read_csv(full_path, sep=sep)
            self.metadata = metadata_df.to_dict('records')
        else:
            raise ValueError(f"Unsupported metadata format: {full_path.suffix}")
        
        logger.info(f"Collected metadata for {len(self.metadata)} entries")
        
        return self.metadata
    
    def validate_data(self, data_type: str) -> Dict[str, Union[bool, str, int]]:
        """
        Validate collected data.
        
        Args:
            data_type: Type of data to validate
            
        Returns:
            Validation results dictionary
        """
        if data_type not in self.collected_data:
            return {"valid": False, "error": f"Data type {data_type} not found"}
        
        df = self.collected_data[data_type]
        
        validation_results = {
            "valid": True,
            "rows": len(df),
            "columns": len(df.columns),
            "missing_values": df.isnull().sum().sum(),
            "duplicate_rows": df.duplicated().sum(),
            "data_types": df.dtypes.to_dict()
        }
        
        # Check for critical issues
        if validation_results["missing_values"] > len(df) * 0.5:  # More than 50% missing
            validation_results["valid"] = False
            validation_results["error"] = "Too many missing values"
        
        logger.info(f"Validation results for {data_type}: {validation_results}")
        
        return validation_results
    
    def get_collection_summary(self) -> Dict:
        """
        Get summary of all collected data.
        
        Returns:
            Summary dictionary
        """
        summary = {
            "total_datasets": len(self.collected_data),
            "datasets": {},
            "metadata_entries": len(self.metadata) if self.metadata else 0
        }
        
        for data_type, df in self.collected_data.items():
            summary["datasets"][data_type] = {
                "rows": len(df),
                "columns": len(df.columns),
                "size_mb": df.memory_usage(deep=True).sum() / 1024 / 1024
            }
        
        return summary
    
    def export_collection_report(self, output_path: str = "data_collection_report.txt") -> str:
        """
        Export a detailed collection report.
        
        Args:
            output_path: Path for the report file
            
        Returns:
            Path to the generated report
        """
        summary = self.get_collection_summary()
        
        report_content = f"""
Data Collection Report
======================
Generated by: Data Collection Module (TID-23a5d36f)
Total Datasets: {summary['total_datasets']}
Metadata Entries: {summary['metadata_entries']}

Dataset Details:
"""
        
        for data_type, info in summary["datasets"].items():
            report_content += f"""
- {data_type}:
  Rows: {info['rows']}
  Columns: {info['columns']}
  Size: {info['size_mb']:.2f} MB
"""
        
        # Write report to file
        report_path = Path(output_path)
        with open(report_path, 'w') as f:
            f.write(report_content)
        
        logger.info(f"Collection report exported to {report_path}")
        
        return str(report_path)


def main():
    """
    Example usage of the DataCollector.
    """
    collector = DataCollector()
    
    try:
        # Collect sample data
        if Path("data/sample_data.csv").exists():
            collector.collect_csv_data("sample_data.csv", "sample")
            validation = collector.validate_data("sample")
            print(f"Sample data validation: {validation}")
        
        # Collect metadata
        if Path("data/metadata.csv").exists():
            collector.collect_metadata("metadata.csv")
        
        # Generate summary
        summary = collector.get_collection_summary()
        print(f"Collection summary: {summary}")
        
        # Export report
        report_path = collector.export_collection_report()
        print(f"Report generated: {report_path}")
        
    except Exception as e:
        logger.error(f"Data collection failed: {e}")
        print(f"Error: {e}")


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    main()