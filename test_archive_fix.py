#!/usr/bin/env python3
"""
Test Archive Fix
================

This script tests the archive function with proper TID resolution.
"""

import os
import subprocess
from notion_client import Client
from dotenv import load_dotenv
from pathlib import Path

def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize Notion client
    notion_token = os.getenv("NOTION_API_KEY")
    tasks_db_id = os.getenv("NOTION_TASKS_DB_ID")
    
    if not notion_token:
        print("❌ Missing Notion API credentials in .env file")
        return
    
    notion = Client(auth=notion_token)
    
    try:
        # Get current Git branch
        current_branch = subprocess.run(
            ['git', 'branch', '--show-current'], 
            capture_output=True, text=True, check=True
        ).stdout.strip()
        
        print(f"🔍 Current Git branch: {current_branch}")
        
        if not current_branch.startswith('feature/TID-'):
            print("❌ Not on a task branch")
            return
        
        # Extract short TID from branch name
        tid_short = current_branch.split('TID-')[1].split('-')[0]
        print(f"📋 Extracted short TID: {tid_short}")
        
        # Query Notion database to find the matching task
        response = notion.databases.query(database_id=tasks_db_id)
        
        matching_task = None
        for task in response['results']:
            if tid_short in task['id']:
                # Get task title
                title_prop = task['properties'].get('Task name', {})
                if title_prop.get('title'):
                    title = title_prop['title'][0]['text']['content']
                    if "데이터 수집 모듈" in title:  # Task 1.1 확인
                        matching_task = task
                        break
        
        if not matching_task:
            print(f"❌ Could not find matching task for TID: {tid_short}")
            return
        
        notion_tid = matching_task['id']
        task_title = matching_task['properties']['Task name']['title'][0]['text']['content']
        
        print(f"✅ Found matching task:")
        print(f"   Full TID: {notion_tid}")
        print(f"   Title: {task_title}")
        
        # Find conversation file
        export_files = list(Path('.').glob('*-command-message*.txt'))
        if not export_files:
            print("❌ No conversation file found")
            return
        
        conversation_file = str(max(export_files, key=os.path.getctime))
        print(f"📄 Found conversation file: {conversation_file}")
        
        # Read conversation content
        with open(conversation_file, 'r', encoding='utf-8') as f:
            conversation_content = f.read()
        
        print(f"📖 Read {len(conversation_content)} characters")
        
        # Find toggle block for AI conversation
        page_blocks = notion.blocks.children.list(block_id=notion_tid)
        toggle_block_id = None
        
        print(f"🔍 Searching for toggle block in {len(page_blocks['results'])} blocks...")
        
        for i, block in enumerate(page_blocks['results']):
            print(f"   Block {i}: {block.get('type')} - {block.get('id')}")
            if block.get('type') == 'toggle':
                toggle_text = block.get('toggle', {}).get('rich_text', [])
                if toggle_text:
                    text_content = toggle_text[0].get('text', {}).get('content', '')
                    print(f"     Toggle text: {text_content}")
                    if '💬 AI 대화 기록' in text_content or 'AI' in text_content:
                        toggle_block_id = block['id']
                        print(f"✅ Found AI conversation toggle block: {toggle_block_id}")
                        break
        
        if not toggle_block_id:
            print("❌ Could not find AI conversation toggle block")
            print("🔧 Available blocks:")
            for block in page_blocks['results']:
                if block.get('type') == 'toggle':
                    toggle_text = block.get('toggle', {}).get('rich_text', [])
                    if toggle_text:
                        text_content = toggle_text[0].get('text', {}).get('content', '')
                        print(f"   - {text_content}")
            return
        
        # Split conversation into chunks (Notion has 2000 character limit)
        chunks = [conversation_content[i:i+1800] for i in range(0, len(conversation_content), 1800)]
        
        print(f"📦 Splitting conversation into {len(chunks)} chunks")
        
        # Add chunks to toggle block
        for i, chunk in enumerate(chunks):
            chunk_block = {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"📝 Chunk {i+1}/{len(chunks)}\n"}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": chunk}}
                    ]
                }
            }
            
            notion.blocks.children.append(
                block_id=toggle_block_id, 
                children=[chunk_block]
            )
            print(f"✅ Added chunk {i+1}/{len(chunks)} to Notion")
        
        print(f"🎉 Successfully archived conversation to Task 1.1!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()