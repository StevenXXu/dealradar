"""Create the DealRadar Notion database with the required schema."""
import os
from notion_client import Client as NotionClientLib

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
if not NOTION_API_KEY:
    # Try loading from .env file directly
    from pathlib import Path
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("NOTION_API_KEY="):
                NOTION_API_KEY = line.split("=", 1)[1].strip()
                break

if not NOTION_API_KEY:
    raise ValueError("NOTION_API_KEY not set in .env")

client = NotionClientLib(auth=NOTION_API_KEY)

# Find the "INP Capital CRM" page to use as parent
print("Searching for 'INP Capital CRM' page...")
search = client.search(filter={"property": "object", "value": "page"}, page_size=10)
pages = search.get('results', [])

parent_page_id = None
for p in pages:
    props = p.get('properties', {})
    for k, v in props.items():
        if v.get('type') == 'title':
            t = v.get('title', [{}])
            if t:
                title = t[0].get('text', {}).get('content', '')
                if 'INP Capital' in title or 'CRM' in title:
                    parent_page_id = p['id']
                    print(f"Found parent page: [{p['id']}] {title}")
                    break
    if parent_page_id:
        break

if not parent_page_id:
    # Look for "CRM Page" or use first available
    for p in pages:
        props = p.get('properties', {})
        for k, v in props.items():
            if v.get('type') == 'title':
                t = v.get('title', [{}])
                if t:
                    title = t[0].get('text', {}).get('content', 'Untitled')
                    print(f"  [{p['id']}] {title}")
                break
    # Use CRM Page if found, else first page
    crm_page = next((p for p in pages if 'CRM Page' in str(p.get('properties', {})) or 'INP' in str(p.get('properties', {}))), pages[0] if pages else None)
    if crm_page:
        parent_page_id = crm_page['id']
        print(f"Using: [{parent_page_id}]")
    else:
        raise ValueError("No suitable parent page found.")

if not parent_page_id:
    raise ValueError("No pages found in Notion workspace. Please create a page first.")

# Create the database with the required schema
database_schema = {
    "Name": {"title": {}},
    "Domain": {"url": {}},
    "VC Source": {"rich_text": {}},
    "Sector": {"rich_text": {}},
    "One-liner": {"rich_text": {}},
    "Signal Score": {"number": {"format": "number"}},
    "Funding Clock": {"date": {}},
    "Tags": {"multi_select": {}},
    "Last Raise Amount": {"rich_text": {}},
    "Last Raise Date": {"date": {}},
    "Last Scraped": {"date": {}},
    "Source URL": {"url": {}},
    "Model Used": {"rich_text": {}},
}

print(f"\nCreating database 'DealRadar Companies' under parent page {parent_page_id}...")

# Use correct parent structure for notion_client
database = client.databases.create(
    parent={"type": "page_id", "page_id": parent_page_id},
    title=[{"text": {"content": "DealRadar Companies"}}],
    properties=database_schema
)

db_id = database["id"]
print(f"\n✅ Database created successfully!")
print(f"   Database ID: {db_id}")
print(f"\nAdd this to your .env file:")
print(f"   NOTION_DATABASE_ID={db_id}")
print(f"\nOr update config/vc_seeds.json with the parent page ID if needed.")
