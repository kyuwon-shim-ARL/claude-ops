#!/usr/bin/env python3

import argparse
import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional

# Import workflow manager
try:
    import sys
    sys.path.append('.')
    from src.workflow_manager import WorkflowManager
except ImportError as e:
    print(f"⚠️  Workflow manager not available: {e}")
    WorkflowManager = None

def validate_workflow_a_inputs(args):
    """Validate inputs for Workflow A (FASTQ-based)"""
    errors = []
    
    if not os.path.exists(args.fastq_dir):
        errors.append(f"FASTQ directory not found: {args.fastq_dir}")
    
    if not os.path.exists(args.reference_genome):
        errors.append(f"Reference genome not found: {args.reference_genome}")
    
    if not os.path.exists(args.metadata):
        errors.append(f"Metadata file not found: {args.metadata}")
    
    return errors

def validate_workflow_b_inputs(args):
    """Validate inputs for Workflow B (Count table-based)"""
    errors = []
    
    if not os.path.exists(args.count_table):
        errors.append(f"Count table not found: {args.count_table}")
    
    if not os.path.exists(args.metadata):
        errors.append(f"Metadata file not found: {args.metadata}")
    
    if not args.annotation and not args.reference_genome:
        errors.append("Either --annotation or --reference_genome must be provided")
    
    if args.annotation and not os.path.exists(args.annotation):
        errors.append(f"Annotation file not found: {args.annotation}")
    
    if args.reference_genome and not os.path.exists(args.reference_genome):
        errors.append(f"Reference genome not found: {args.reference_genome}")
    
    return errors

def run_nextflow_workflow(workflow_script: str, params: Dict[str, str], profile: str = "local"):
    """Execute Nextflow workflow with given parameters"""
    cmd = ["nextflow", "run", workflow_script, "-profile", profile]
    
    # Add parameters
    for key, value in params.items():
        if value is not None:
            cmd.extend([f"--{key}", str(value)])
    
    print(f"Executing: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Pipeline completed successfully!")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Pipeline failed with exit code {e.returncode}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False

def workflow_a(args):
    """Execute Workflow A: FASTQ-based pipeline"""
    print("=== Bacterial Transcriptome Analysis Pipeline - Workflow A (FASTQ-based) ===")
    
    # Validate inputs
    errors = validate_workflow_a_inputs(args)
    if errors:
        print("Input validation errors:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    # Prepare parameters
    params = {
        "fastq_dir": args.fastq_dir,
        "reference_genome": args.reference_genome,
        "metadata": args.metadata,
        "contrast": args.contrast,
        "outdir": args.outdir or "./results_workflow_a"
    }
    
    # Run pipeline
    workflow_script = "src/workflows/workflow_a.nf"
    return run_nextflow_workflow(workflow_script, params, args.profile)

def workflow_b(args):
    """Execute Workflow B: Count table-based pipeline"""
    print("=== Bacterial Transcriptome Analysis Pipeline - Workflow B (Count table-based) ===")
    
    # Validate inputs
    errors = validate_workflow_b_inputs(args)
    if errors:
        print("Input validation errors:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    # Prepare parameters
    params = {
        "count_table": args.count_table,
        "metadata": args.metadata,
        "contrast": args.contrast,
        "annotation": args.annotation,
        "reference_genome": args.reference_genome,
        "outdir": args.outdir or "./results_workflow_b"
    }
    
    # Run pipeline
    workflow_script = "src/workflows/workflow_b.nf"
    return run_nextflow_workflow(workflow_script, params, args.profile)

def list_results(output_dir: str):
    """List and summarize pipeline results"""
    if not os.path.exists(output_dir):
        print(f"Results directory not found: {output_dir}")
        return
    
    print(f"\n=== Results Summary - {output_dir} ===")
    
    # Key result files to check
    key_files = [
        ("counts.tsv", "Gene expression count matrix"),
        ("deg_results.tsv", "Differential expression results"),
        ("enrichment_results.tsv", "Functional enrichment results"),
        ("pca_plot.png", "PCA plot"),
        ("volcano_plot.png", "Volcano plot"),
        ("heatmap.png", "Expression heatmap"),
        ("dotplot.png", "Enrichment dot plot")
    ]
    
    for filename, description in key_files:
        filepath = Path(output_dir) / filename
        if filepath.exists():
            print(f"✓ {description}: {filepath}")
        else:
            # Check in subdirectories
            found = False
            for subdir in ["counts", "dge", "enrichment", "qc"]:
                subpath = Path(output_dir) / subdir / filename
                if subpath.exists():
                    print(f"✓ {description}: {subpath}")
                    found = True
                    break
            if not found:
                print(f"✗ {description}: Not found")

def main():
    parser = argparse.ArgumentParser(
        description="Claude-Ops: AI-Augmented Research Workflow System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pipeline Commands:
  Workflow A (FASTQ-based):
    python main.py workflow-a --fastq-dir ./data/fastq --reference-genome ./ref/genome.fasta --metadata ./data/metadata.tsv
  
  Workflow B (Count table-based):
    python main.py workflow-b --count-table ./data/counts.tsv --metadata ./data/metadata.tsv --annotation ./ref/annotation.gff

Workflow Management Commands:
  Create project plan:
    python main.py project-plan --source docs/proposals/my-proposal.md
  
  Start task:
    python main.py task-start T-001
  
  Archive conversation:
    python main.py task-archive T-001
  
  Finish task with PR:
    python main.py task-finish T-001 --pr
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Workflow Management Commands
    if WorkflowManager:
        # Project plan command
        plan_parser = subparsers.add_parser("project-plan", help="Create Epic/Task tickets from proposal")
        plan_parser.add_argument("--source", required=True, help="Source proposal file")
        plan_parser.add_argument("--project", help="Project ID")
        
        # Task commands
        start_parser = subparsers.add_parser("task-start", help="Start a task")
        start_parser.add_argument("task_id", help="Task ID")
        
        archive_parser = subparsers.add_parser("task-archive", help="Archive task conversation")
        archive_parser.add_argument("task_id", help="Task ID")
        archive_parser.add_argument("--file", help="Conversation file path")
        
        finish_parser = subparsers.add_parser("task-finish", help="Finish a task")
        finish_parser.add_argument("task_id", help="Task ID")
        finish_parser.add_argument("--pr", action="store_true", help="Create pull request")
        
        publish_parser = subparsers.add_parser("task-publish", help="Publish task knowledge")
        publish_parser.add_argument("task_id", help="Task ID")
    
    # Workflow A parser
    parser_a = subparsers.add_parser("workflow-a", help="Run Workflow A (FASTQ-based)")
    parser_a.add_argument("--fastq-dir", required=True, help="Directory containing FASTQ files")
    parser_a.add_argument("--reference-genome", required=True, help="Reference genome FASTA file")
    parser_a.add_argument("--metadata", required=True, help="Sample metadata TSV file")
    parser_a.add_argument("--contrast", default="condition,Treated,Control", help="Contrast for DEG analysis")
    parser_a.add_argument("--outdir", help="Output directory (default: ./results_workflow_a)")
    parser_a.add_argument("--profile", default="local", choices=["local", "cluster"], help="Execution profile")
    
    # Workflow B parser
    parser_b = subparsers.add_parser("workflow-b", help="Run Workflow B (Count table-based)")
    parser_b.add_argument("--count-table", required=True, help="Gene expression count matrix TSV file")
    parser_b.add_argument("--metadata", required=True, help="Sample metadata TSV file")
    parser_b.add_argument("--contrast", default="condition,Treated,Control", help="Contrast for DEG analysis")
    parser_b.add_argument("--annotation", help="Genome annotation GFF file")
    parser_b.add_argument("--reference-genome", help="Reference genome FASTA file")
    parser_b.add_argument("--outdir", help="Output directory (default: ./results_workflow_b)")
    parser_b.add_argument("--profile", default="local", choices=["local", "cluster"], help="Execution profile")
    
    # Results parser
    parser_results = subparsers.add_parser("results", help="List and summarize pipeline results")
    parser_results.add_argument("--outdir", required=True, help="Results directory to summarize")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Handle workflow management commands
    if WorkflowManager and args.command in ["project-plan", "task-start", "task-archive", "task-finish", "task-publish"]:
        manager = WorkflowManager()
        
        if args.command == "project-plan":
            success = manager.create_project_plan(args.source, args.project)
        elif args.command == "task-start":
            success = manager.start_task(args.task_id)
        elif args.command == "task-archive":
            success = manager.archive_task(args.task_id, getattr(args, 'file', None))
        elif args.command == "task-finish":
            success = manager.finish_task(args.task_id, args.pr)
        elif args.command == "task-publish":
            success = manager.publish_task(args.task_id)
        
        return 0 if success else 1
    
    # Handle pipeline commands
    if args.command == "workflow-a":
        success = workflow_a(args)
    elif args.command == "workflow-b":
        success = workflow_b(args)
    elif args.command == "results":
        list_results(args.outdir)
        return 0
    else:
        parser.print_help()
        return 1
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
