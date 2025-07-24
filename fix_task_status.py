#!/usr/bin/env python3
"""
Fix Task Status in Notion
==========================

This script directly updates Task 1.1 status to "Done" in Notion.
"""

import os
from notion_client import Client
from dotenv import load_dotenv

def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize Notion client
    notion_token = os.getenv("NOTION_API_KEY")
    
    if not notion_token:
        print("❌ Missing Notion API credentials in .env file")
        return
    
    notion = Client(auth=notion_token)
    
    # Task 1.1 ID
    task_id = "23a5d36f-fc73-81c6-ad08-e7fcb660cca2"
    
    try:
        print(f"🔄 Updating Task 1.1 status to 'Done'...")
        print(f"📋 Task ID: {task_id}")
        
        # Update task status
        response = notion.pages.update(
            page_id=task_id,
            properties={
                "Status": {"status": {"name": "Done"}}
            }
        )
        
        print(f"✅ Successfully updated task status to 'Done'")
        
        # Verify the update
        updated_task = notion.pages.retrieve(page_id=task_id)
        current_status = updated_task['properties']['Status']['status']['name']
        print(f"🔍 Verified current status: {current_status}")
        
        if current_status.lower() == "done":
            print("🎉 Task 1.1 is now marked as DONE!")
        else:
            print(f"⚠️  Status update may have failed. Current status: {current_status}")
        
    except Exception as e:
        print(f"❌ Error updating task status: {e}")

if __name__ == "__main__":
    main()