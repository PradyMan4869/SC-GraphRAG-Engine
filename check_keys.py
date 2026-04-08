import asyncio
from src.rag.indexer import get_rag
from lightrag import QueryParam

async def check():
    rag = await get_rag()
    res = await rag.aquery_llm("What is Section 29A?", param=QueryParam(mode="hybrid"))
    print("KEYS:", res.keys())
    # Often keys are 'entities', 'relationships', 'chunks', 'llm_response'
    if 'entities' in res:
        print(f"ENTITIES COUNT: {len(res['entities'])}")
        print(f"SAMPLE ENTITIES: {[e.get('entity_name') or e.get('id') for e in res['entities'][:10]]}")
    if 'chunks' in res:
        print(f"CHUNKS COUNT: {len(res['chunks'])}")
        print(f"SAMPLE CHUNK CONTENT (first 100 char): {str(res['chunks'][0])[:100] if res['chunks'] else 'NONE'}")

if __name__ == "__main__":
    asyncio.run(check())
