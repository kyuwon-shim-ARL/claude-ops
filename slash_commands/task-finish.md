# /task-finish

Complete a Notion task, create PR, and optionally auto-merge with cleanup.

## Usage

```bash
/task-finish <TID> [--pr] [--auto-merge]
```

## Parameters

- `<TID>`: Notion Task ID (UUID format)
- `--pr`: Create a pull request for the changes
- `--auto-merge`: Automatically merge the PR and clean up branches

## Examples

### Basic completion (no PR)
```bash
/task-finish 23a5d36f-fc73-8114-9dff-dca65d81c102
```

### Create PR but manual merge
```bash
/task-finish 23a5d36f-fc73-8114-9dff-dca65d81c102 --pr
```

### Full automation (recommended for small changes)
```bash
/task-finish 23a5d36f-fc73-8114-9dff-dca65d81c102 --pr --auto-merge
```

## What it does

1. **Task Completion**:
   - Updates Notion task status to "Done"
   - Adds completion timestamp

2. **Pull Request Creation** (if `--pr`):
   - Creates PR with formatted title: `[TID-xxx] Task Name`
   - Includes summary and Claude Code attribution
   - Links to Notion task for context

3. **Auto-merge** (if `--auto-merge`):
   - Waits 2 seconds for PR to be ready
   - Merges using squash method
   - Deletes remote feature branch
   - Switches to main and pulls latest
   - Deletes local feature branch
   - Complete cleanup for streamlined workflow

## Benefits of Auto-merge

- **Faster workflow**: No manual PR review steps
- **Clean history**: Squash merge keeps main branch tidy  
- **Automatic cleanup**: Removes stale branches
- **Rollback friendly**: Git history allows easy reversion if needed

## Safety Notes

- Auto-merge uses squash method to maintain clean history
- Failed auto-merge falls back to manual PR
- All changes are tracked in Git for easy rollback
- Notion task status is updated regardless of PR status

## Implementation

The command executes via `/home/kyuwon/MC_test_ops/src/workflow_manager.py`:

```python
python src/workflow_manager.py task-finish <TID> --pr --auto-merge
```

This integrates with the Notion-Git dual-space system to maintain consistency between strategic planning (Notion) and development execution (Git).