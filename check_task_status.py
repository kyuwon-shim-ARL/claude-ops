#!/usr/bin/env python3
"""
Notion Task Status Checker
==========================

This script queries the Notion API to check the current status of all tasks,
specifically focusing on verifying TID-23a5d36f (Task 1.1) status.
"""

import os
from notion_client import Client
from dotenv import load_dotenv
import json

def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize Notion client
    notion_token = os.getenv("NOTION_API_KEY")
    tasks_db_id = os.getenv("NOTION_TASKS_DB_ID")
    
    if not notion_token or not tasks_db_id:
        print("❌ Missing Notion API credentials in .env file")
        return
    
    notion = Client(auth=notion_token)
    
    try:
        print("🔍 Querying Notion Tasks Database...")
        print(f"📋 Database ID: {tasks_db_id}")
        print("-" * 60)
        
        # Query all tasks from the database
        response = notion.databases.query(database_id=tasks_db_id)
        
        print(f"📊 Found {len(response['results'])} total tasks")
        print("=" * 60)
        
        target_task_found = False
        target_tid = "23a5d36f"
        
        for i, task in enumerate(response['results'], 1):
            try:
                # Extract task properties
                task_id = task['id']
                
                # Get title
                title_prop = task['properties'].get('Task name', {})
                if title_prop.get('title'):
                    title = title_prop['title'][0]['text']['content']
                else:
                    title = "No title"
                
                # Get status
                status_prop = task['properties'].get('Status', {})
                if status_prop.get('status'):
                    status = status_prop['status']['name']
                else:
                    status = "No status"
                
                # Check if this is our target task
                is_target = target_tid in task_id
                
                if is_target:
                    target_task_found = True
                    print(f"🎯 TARGET TASK FOUND:")
                    print(f"   Task ID: {task_id}")
                    print(f"   Short TID: {target_tid}")
                    print(f"   Title: {title}")
                    print(f"   Status: {status}")
                    print(f"   ✅ Status Check: {'DONE' if status.lower() == 'done' else 'NOT DONE'}")
                    print("-" * 60)
                
                # Display all tasks
                status_emoji = "✅" if status.lower() == "done" else "🔄" if "progress" in status.lower() else "⏸️"
                target_indicator = "🎯 " if is_target else "   "
                
                print(f"{target_indicator}{i:2d}. {status_emoji} {title[:50]}")
                print(f"      ID: {task_id}")
                print(f"      Status: {status}")
                print()
                
            except Exception as e:
                print(f"❌ Error processing task {i}: {e}")
                continue
        
        print("=" * 60)
        
        if not target_task_found:
            print(f"❌ Target task with TID '{target_tid}' NOT FOUND")
            print("🔍 Available task IDs:")
            for task in response['results']:
                print(f"   - {task['id']}")
        else:
            print(f"✅ Target task analysis complete")
        
        # Summary
        done_count = sum(1 for task in response['results'] 
                        if task['properties'].get('Status', {}).get('status', {}).get('name', '').lower() == 'done')
        
        print(f"\n📈 Task Summary:")
        print(f"   Total Tasks: {len(response['results'])}")
        print(f"   Completed (Done): {done_count}")
        print(f"   Remaining: {len(response['results']) - done_count}")
        
    except Exception as e:
        print(f"❌ Error querying Notion: {e}")
        print(f"   Please check your API credentials and database ID")

if __name__ == "__main__":
    main()