📝 **Document Organization (Independent Documentation Management v3.0)**

**🎯 Core Role**: Systematic organization of **structure-independent** documents + project-specific archiving

**💡 Role Separation (v15.0)**:
- **`/stabilize`**: Structure-coupled docs (CLAUDE.md, README.md, API docs) auto-sync
- **`/docsorg`**: Structure-independent docs (tutorials, guides, meeting notes, specs) manual organization

## Usage
```
/docsorg [project-name]
/docsorg  # Auto-detect current project
```

## Claude Execution Process

### Step 1: Independent Document Identification & Collection

**🎯 Target Documents (Structure-Independent)**:
- Tutorials, user guides, how-to documents
- Meeting notes, planning documents, pure text files
- Research notes, idea sketches
- Blog posts, marketing materials
- User feedback, interview records

**⛔ Excluded (Structure-Coupled)**:
- CLAUDE.md, README.md → Handled automatically by `/stabilize`
- API docs, code documentation → Handled automatically by `/stabilize`
- requirements.txt, configs → Handled automatically by `/stabilize`

```python
def collect_independent_docs():
    # Selective collection of independent documents only
    targets = [
        "docs/guides/", "docs/tutorials/", "docs/meetings/",
        "*.md (non-technical docs)", "notes/", "planning/"
    ]
    # Skip structure-coupled documents
    exclude = ["CLAUDE.md", "README.md", "architecture.md"]
```

### Step 2: Content-Based Semantic Classification

**📚 Independent Document Classification System**:
```python
def classify_independent_docs():
    categories = {
        "tutorials": ["tutorial", "guide", "howto"],
        "planning": ["planning", "meeting", "idea", "brainstorm"],
        "research": ["research", "investigation", "analysis", "benchmark"],  
        "communication": ["presentation", "report", "feedback", "interview"],
        "knowledge": ["learning", "summary", "reference"],
        "archive": ["old-version", "deprecated", "legacy"]
    }
    # Classification based on content keywords + filename + creation date
    # Uses semantic classification, not roadmap-based
```

### Step 3: Independent Document Archive Structure

**📁 Semantic Archiving (Code-Agnostic)**:
```bash
docs/projects/{project-name}/
├── index.md            # Independent document list (auto-generated)
├── tutorials/          # Usage guides, tutorials
│   └── [moved tutorial documents]
├── planning/           # Planning docs, meeting notes, ideas
│   └── [moved planning documents] 
├── research/           # Investigation, research, benchmark materials
│   └── [moved research documents]
├── communication/      # Presentations, reports, feedback
│   └── [moved communication documents]
├── knowledge/          # Learning notes, reference materials
│   └── [moved knowledge documents]
└── archive/           # Old versions, deprecated
    └── [moved archive documents]

# Note: Structure-coupled documents are NOT included here
# CLAUDE.md, README.md etc. are handled automatically by /stabilize
```

### Step 4: Independent Document Statistics & Quality Analysis

```python
def analyze_document_quality():
    return {
        "document_count_by_type": {
            "tutorials": 5, "planning": 8, "research": 3
        },
        "outdated_documents": ["old-guide.md", "deprecated-api.md"],
        "missing_documentation": ["user-manual", "troubleshooting"],
        "consolidation_opportunities": ["merge 3 similar tutorials"],
        "knowledge_gaps": ["advanced topics", "edge cases"]
    }
```

### Step 5: Independent Document Index Generation

**📋 Semantic Indexing (Structure-Independent)**:
```markdown
# {Project Name} Independent Document Archive

## 📊 Document Status  
- Total documents: 24
- Last updated: 2024-08-27
- Quality status: Good (5 outdated)

## 📁 Documents by Category

### 📚 Tutorials (5 docs)
- [User Guide v2.1](tutorials/user-guide-v2.1.md) ⭐ Latest
- [Installation Tutorial](tutorials/installation.md)  
- [Advanced Features Guide](tutorials/advanced-features.md) ⚠️ Needs update

### 📋 Planning (8 docs)
- [2024 Q3 Plan](planning/2024-q3-plan.md)
- [UI Improvement Meeting](planning/ui-improvement-meeting.md)
- [User Feedback Summary](planning/user-feedback-summary.md)

### 🔍 Research (3 docs)
- [Competitor Analysis](research/competitor-analysis.md)
- [Tech Stack Comparison](research/tech-stack-comparison.md)

### 💬 Communication (4 docs) 
- [Monthly Report](communication/monthly-report.md)
- [Customer Interview Results](communication/customer-interviews.md)

### 🧠 Knowledge (3 docs)
- [Development Tips](knowledge/dev-tips.md)
- [Troubleshooting Guide](knowledge/troubleshooting.md)

### 📦 Archive (1 doc)
- [Old Version Documents](archive/) 

## 🔧 Document Quality Improvement Suggestions
- ⚠️ 5 documents need updates
- 💡 Recommend merging 3 duplicate tutorials
- 📝 Need to create new user manual

## 🔗 Related Resources
- Structure-coupled documents managed by `/stabilize` command
- Code documentation: CLAUDE.md, README.md (auto-sync)
- API documentation: /docs/api/ (code-linked)
```

## Actual Execution Example (Independent Documents Only)

### Input:
```
/docsorg "Claude-Dev-Kit"  
```

### Claude Execution:
1. **Selective search** for independent documents only (exclude structure-coupled docs)
2. Semantic classification of each document by content
3. Create docs/projects/Claude-Dev-Kit/ structure  
4. Organize documents by semantic categories
5. Quality analysis and improvement suggestions
6. Generate independent document index

### Output:
```
✅ Claude-Dev-Kit independent document organization complete

📊 Organization Results:
- 18 independent documents found (7 structure-coupled docs excluded)
- Classified into 6 semantic categories
- Document quality: Good (4 updates recommended)

📁 Created Structure:
docs/projects/Claude-Dev-Kit/
├── index.md (independent document list)
├── tutorials/ (3 documents)
├── planning/ (6 documents) 
├── research/ (2 documents)
├── communication/ (4 documents)
├── knowledge/ (2 documents)
└── archive/ (1 document)

⚠️ Structure-coupled documents managed separately:
- CLAUDE.md, README.md → Auto-sync via `/stabilize`
- API docs, config files → Handled by `/stabilize`

🔧 Document Quality Improvement Suggestions:
- 4 tutorials need updates
- Recommend merging 2 duplicate guides
- Need to create advanced usage documentation

📝 Detailed list: docs/projects/Claude-Dev-Kit/index.md
```

## Core Features (Independent Documents Only)

### 📋 Smart Document Identification  
- Auto-classify structure-coupled vs structure-independent
- Code change impact analysis for improved classification accuracy
- Automatically exclude CLAUDE.md, API docs, etc.

### 🏷️ Semantic Classification System
- Content-based classification, not roadmap-based
- Tutorials, planning, research, communication, knowledge, archive 
- Comprehensive analysis of keywords + context + creation date

### 🔍 Quality Management
- Duplicate document detection and merge suggestions
- Freshness check (outdated document identification)
- Documentation gap analysis (missing documentation)

## 🔗 Role Separation Workflow (v15.0)

### **Structure-Coupled Documents**: Auto-handled by `/stabilize`
```bash
# Auto-update linked docs when code changes
/stabilize
# → CLAUDE.md, README.md, API docs, requirements.txt etc.
# → Automatic sync of documents closely tied to code structure
```

### **Structure-Independent Documents**: Manual management via `/docsorg`  
```bash  
# 1. Organize independent documents (recommended monthly)
/docsorg "project-name"
# → Tutorials, guides, meeting notes, planning docs etc.
# → Content-based semantic archiving

# 2. Quality improvement
# → Update outdated documents
# → Consolidate duplicate documents
# → Identify missing documents
```

### **Integrated Flow**:
```bash
# Development → Stabilize(structure-coupled) → Docs-org(structure-independent) → Complete
/implement → /stabilize → /docsorg → /weekly
```

## ✨ Improvement Effects (v15.0)

### **🎯 Clear Role Separation**:
- **Structure-coupled**: Auto-sync on code changes (`/stabilize`)
- **Structure-independent**: Content-based manual archiving (`/docsorg`)

### **📊 Document Management Efficiency**:
- Remove unnecessary automation (forced roadmap classification of independent docs)
- Improved searchability through semantic classification
- Automated quality management (duplication, freshness, gaps)

### **🔄 Circular Optimization**:
- Mutual complementarity between stabilize ↔ docsorg
- Minimize impact of structural changes on independent documents
- Apply optimal management methods for each document type

### **🚀 User Experience**:
- Clear command system with defined roles
- Simultaneous achievement of structural stability and document quality
- Elimination of unnecessary redundant work

---
*Optimal separated management of structure-coupled and structure-independent documents ensures both system stability and efficiency.*