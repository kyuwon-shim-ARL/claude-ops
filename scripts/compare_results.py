#!/usr/bin/env python3
"""
Compare hooks vs scraping notification results.
Usage: python compare_results.py [--hours N]
"""

import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
import argparse


def load_events(filepath: str) -> list:
    """Load events from JSONL file."""
    events = []
    if not os.path.exists(filepath):
        return events

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp."""
    # Handle different ISO formats
    ts = ts.replace('Z', '+00:00')
    if '+' in ts:
        ts = ts.split('+')[0]
    return datetime.fromisoformat(ts)


def filter_recent(events: list, hours: int) -> list:
    """Filter events from the last N hours."""
    cutoff = datetime.now() - timedelta(hours=hours)
    return [
        e for e in events
        if parse_timestamp(e['timestamp']) > cutoff
    ]


def match_events(hooks_events: list, scraping_events: list, window_seconds: int = 30) -> dict:
    """
    Match hooks and scraping events within a time window.
    Returns analysis results.
    """
    results = {
        'hooks_only': [],      # Hooks detected, scraping missed
        'scraping_only': [],   # Scraping detected, hooks missed
        'both': [],            # Both detected
        'latency_diffs': [],   # Time differences when both detected
    }

    # Group scraping events by session
    scraping_by_session = defaultdict(list)
    for e in scraping_events:
        session = e.get('session_name', '')
        scraping_by_session[session].append(e)

    # For each hooks event, find matching scraping event
    matched_scraping = set()

    for hooks_event in hooks_events:
        hooks_ts = parse_timestamp(hooks_event['timestamp'])
        project = hooks_event.get('project', '')

        # Try to find matching scraping event
        # Session name format: claude_<project>
        possible_sessions = [
            f"claude_{project}",
            f"claude-{project}",
            project
        ]

        found_match = False
        for session in possible_sessions:
            for i, scraping_event in enumerate(scraping_by_session.get(session, [])):
                scraping_ts = parse_timestamp(scraping_event['timestamp'])
                diff = abs((hooks_ts - scraping_ts).total_seconds())

                if diff <= window_seconds:
                    # Match found
                    results['both'].append({
                        'hooks': hooks_event,
                        'scraping': scraping_event,
                        'latency_diff_seconds': diff
                    })
                    results['latency_diffs'].append(diff)
                    matched_scraping.add((session, i))
                    found_match = True
                    break

            if found_match:
                break

        if not found_match:
            results['hooks_only'].append(hooks_event)

    # Find scraping events that weren't matched
    for session, events in scraping_by_session.items():
        for i, event in enumerate(events):
            if (session, i) not in matched_scraping:
                results['scraping_only'].append(event)

    return results


def generate_report(results: dict, hooks_count: int, scraping_count: int) -> str:
    """Generate comparison report."""
    lines = []
    lines.append("=" * 60)
    lines.append("HOOKS vs SCRAPING COMPARISON REPORT")
    lines.append("=" * 60)
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(f"- Total Hooks events:    {hooks_count}")
    lines.append(f"- Total Scraping events: {scraping_count}")
    lines.append(f"- Matched (both):        {len(results['both'])}")
    lines.append(f"- Hooks only:            {len(results['hooks_only'])}")
    lines.append(f"- Scraping only:         {len(results['scraping_only'])}")
    lines.append("")

    # Accuracy metrics
    total_events = len(results['both']) + len(results['hooks_only']) + len(results['scraping_only'])
    if total_events > 0:
        hooks_accuracy = (len(results['both']) + len(results['hooks_only'])) / total_events * 100
        scraping_accuracy = (len(results['both']) + len(results['scraping_only'])) / total_events * 100

        lines.append("## Accuracy")
        lines.append(f"- Hooks detection rate:    {hooks_accuracy:.1f}%")
        lines.append(f"- Scraping detection rate: {scraping_accuracy:.1f}%")
        lines.append("")

    # Latency
    if results['latency_diffs']:
        avg_diff = sum(results['latency_diffs']) / len(results['latency_diffs'])
        max_diff = max(results['latency_diffs'])
        min_diff = min(results['latency_diffs'])

        lines.append("## Latency Difference (when both detected)")
        lines.append(f"- Average: {avg_diff:.2f}s")
        lines.append(f"- Min:     {min_diff:.2f}s")
        lines.append(f"- Max:     {max_diff:.2f}s")
        lines.append("")

    # False positives/negatives analysis
    lines.append("## Analysis")

    if results['hooks_only']:
        lines.append("")
        lines.append("### Hooks Only (Scraping missed these):")
        for event in results['hooks_only'][:5]:
            lines.append(f"  - {event['timestamp']}: {event.get('project', 'unknown')} ({event.get('event_type', 'unknown')})")

    if results['scraping_only']:
        lines.append("")
        lines.append("### Scraping Only (Hooks missed these):")
        for event in results['scraping_only'][:5]:
            lines.append(f"  - {event['timestamp']}: {event.get('session_name', 'unknown')} ({event.get('event_type', 'unknown')})")

    # Recommendation
    lines.append("")
    lines.append("## Recommendation")

    if len(results['scraping_only']) > len(results['hooks_only']):
        lines.append("⚠️  Scraping detected more events than Hooks.")
        lines.append("    Consider investigating why Hooks missed some events.")
    elif len(results['hooks_only']) > len(results['scraping_only']):
        lines.append("✅ Hooks detected more events than Scraping.")
        lines.append("    Hooks appears to be more reliable.")
    else:
        lines.append("📊 Both methods detected similar events.")
        lines.append("    Hooks is recommended for its official support and simplicity.")

    lines.append("")
    lines.append("=" * 60)

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Compare hooks vs scraping results')
    parser.add_argument('--hours', type=int, default=24, help='Analyze last N hours (default: 24)')
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hooks_file = os.path.join(base_dir, 'logs', 'hooks_events.jsonl')
    scraping_file = os.path.join(base_dir, 'logs', 'scraping_events.jsonl')

    # Load events
    hooks_events = load_events(hooks_file)
    scraping_events = load_events(scraping_file)

    # Filter recent
    hooks_events = filter_recent(hooks_events, args.hours)
    scraping_events = filter_recent(scraping_events, args.hours)

    print(f"Analyzing last {args.hours} hours...")
    print(f"Hooks events:    {len(hooks_events)}")
    print(f"Scraping events: {len(scraping_events)}")
    print("")

    if not hooks_events and not scraping_events:
        print("No events found in the specified time range.")
        return

    # Match and analyze
    results = match_events(hooks_events, scraping_events)

    # Generate report
    report = generate_report(results, len(hooks_events), len(scraping_events))
    print(report)


if __name__ == '__main__':
    main()
