import asyncio
import logging
from app.database import get_recent_calls, get_call_detail, init_db, close_db
from app.services.crm import process_call_to_crm
from app.models.schemas import TranscriptEntry

logging.basicConfig(level=logging.INFO)

async def run_sync():
    await init_db()
    
    calls = await get_recent_calls(limit=1000)
    for call in reversed(calls): # sync oldest first
        if not call.get("frappe_synced"):
            print(f"Syncing call {call['id']} to Frappe CRM...")
            db_call_id = call["id"]
            
            detail = await get_call_detail(db_call_id)
            if not detail:
                continue
            
            transcript_raw = detail.get("transcript", [])
            transcript_entries = [TranscriptEntry(**t) for t in transcript_raw]
            
            caller_phone = call.get("caller_number", "unknown")
            if not caller_phone or caller_phone == "unknown":
                # Just give it a fake phone
                caller_phone = "9999999999"
                
            await process_call_to_crm(
                transcript=transcript_entries,
                caller_phone=caller_phone,
                db_call_id=db_call_id,
                sync_to_frappe=True,
                is_dummy=True
            )
            
    await close_db()
    print("Done syncing old leads!")

if __name__ == '__main__':
    asyncio.run(run_sync())
