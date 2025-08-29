🧹 **Repository Comprehensive Cleanup v1.0**

**🎯 Purpose**: Comprehensively clean up your project repository aligned with roadmap - structure/code/docs/dependencies

**📚 Auto Context Loading:**
- project_rules.md check (reflects project philosophy)
- docs/specs/PRD-v*.md check (roadmap alignment)
- docs/CURRENT/status.md check (current state)

**⚡ 3-Stage Cleanup Process:**

## **1. 📊 Repository Analysis (Streamlined Planning)**

**Current State Diagnosis:**
- Full repository structure scan
- Identify issues: duplicate/temp files, structural confusion, doc mismatches
- Design target structure based on roadmap

**Cleanup Plan Establishment:**
- MECE-based cleanup task breakdown
- Priority matrix: Structure → Code → Docs → Dependencies order
- Generate concrete action plan with TodoWrite

**📊 Cleanup Scope Confirmation:**
- ✅ **Structure**: Directory reorganization + file classification + naming standardization
- ✅ **Code**: DRY principle + import optimization + dead code removal
- ✅ **Documentation**: README/CLAUDE.md sync + API docs + .gitignore cleanup
- ✅ **Dependencies**: Package cleanup + environment sync + test environment verification

## **2. 🔧 Comprehensive Cleanup (Focused Execution)**

**Repository Structure Optimization:**
- Full file analysis: directory structure, file purposes review
- Identify and clean duplicate/temp files
- Directory organization: logical grouping, hierarchy optimization
- File classification: systematic sorting by purpose and function
- Naming standardization: apply consistent naming conventions

**Code Quality Enhancement:**
- Apply DRY principle: find and consolidate duplicate code
- Import modifications: resolve circular references, optimize dependencies
- Fix reference errors: broken links, incorrect paths
- Remove unused code: clean up dead code

**Documentation Synchronization:**
- CLAUDE.md update: document structural changes
- README update: usage, installation instructions
- API documentation cleanup: ensure code-doc consistency
- .gitignore cleanup: update exclusion rules

**Dependency Resolution:**
- Environment sync: ensure requirements, configs, package.json consistency
- Package cleanup: remove unused dependencies
- Test environment verification: dev/test/prod environment sync

## **3. 🚀 Cleanup Verification (Cleanup-specific Validation)**

**📊 Automatic Completion Checklist (20 items)**

**Structure Cleanup Verification (5 items):**
- ✅ Root directory files < 15
- ✅ Directory structure logic (purpose-based classification)
- ✅ File naming consistency (kebab-case, camelCase, etc.)
- ✅ Duplicate files removed
- ✅ Temp files cleaned (*.tmp, *.bak, *~)

**Code Cleanup Verification (5 items):**
- ✅ DRY principle compliance (code duplication < 5%)
- ✅ Import errors resolved (0 circular references)
- ✅ Unused code removed
- ✅ Coding convention consistency
- ✅ Lint errors resolved (0 errors, 0 warnings)

**Documentation Cleanup Verification (5 items):**
- ✅ README.md up-to-date (within 24 hours)
- ✅ CLAUDE.md reflects structural changes
- ✅ API docs code consistency (100%)
- ✅ .gitignore optimized
- ✅ Document internal link validity (0 broken links)

**Dependency Cleanup Verification (5 items):**
- ✅ requirements/package.json updated
- ✅ Unused dependencies removed
- ✅ Environment config synced (dev/test/prod)
- ✅ Security vulnerabilities resolved
- ✅ Test environment operational

**Completion Report Example:**
```
📊 Repository Cleanup Completion: 92%

✅ Completed (18/20):
  Structure: 5/5 (100%) - Perfect
  Code: 4/5 (80%) - 1 lint warning
  Documentation: 5/5 (100%) - Perfect
  Dependencies: 4/5 (80%) - 1 security patch needed

⚠️ Incomplete (2 items):
  1. Lint warning 1 (Recommended)
  2. Security patch (Critical)

Select:
[1] Complete all items (Recommended)
[2] Complete critical items only
[3] Deploy as is
```

**Deployment and Verification:**
- Git commit: "refactor: comprehensive repository cleanup v1.0"
- Git push: reflect to remote repository
- Version tagging: cleanup version management
- Generate cleanup completion report: docs/CURRENT/cleanup-report.md

**🎯 Success Criteria:**
- **Structure cleanup rate**: 90%+ (directory logic, file classification)
- **Code cleanup rate**: 85%+ (duplication removal, import optimization)
- **Documentation cleanup rate**: 95%+ (README/CLAUDE.md sync)
- **Dependency cleanup rate**: 90%+ (package cleanup, environment sync)

**💡 Usage Scenarios:**
```bash
# Simple repo cleanup
/repoclean

# Focus on specific areas (optional)
/repoclean "focus on structure and code only"
/repoclean "documentation sync priority"
```

**⚠️ Out of Scope:**
- ❌ New feature development
- ❌ Major architecture changes
- ❌ Business logic refactoring
- ❌ Performance optimization (unrelated to cleanup)

ARGUMENTS: "${args}"