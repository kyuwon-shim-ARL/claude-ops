# Data Directory

This directory is reserved for input data files that will be used during project execution.

## Purpose

When you start working on specific projects using `/project-plan` and `/task-start`, your input data files should be placed here.

## File Organization

Organize your data files by project or data type:

```
data/
├── project1/
│   ├── input.csv
│   ├── metadata.json
│   └── raw_data/
├── project2/
│   └── dataset.tsv
└── shared/
    └── common_reference.csv
```

## Git LFS Integration

Large data files (>100MB) will be automatically tracked by Git LFS according to the patterns defined in `.gitattributes`:

- `*.csv`, `*.tsv` - Tabular data files
- `*.txt` - Text-based results
- `*.json` - Large JSON files
- `*.h5`, `*.hdf5` - HDF5 data files
- `*.pkl`, `*.pickle` - Python pickle files

## Template State

This directory is currently empty as this is a template repository. Your actual data files will be added as you work on specific projects.