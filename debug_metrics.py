import asyncio
import json
from src.rag.query import query
from lightrag import QueryParam

async def debug_evaluation():
    test_queries = [
        {"q": "What is the purpose of Section 29A in the Arbitration and Conciliation Act, 1940?", "entity": "Section 29A"},
        {"q": "How does climate change impact Article 21?", "entity": "Article 21"}
    ]
    
    for item in test_queries:
        print(f"\n--- QUERY: {item['q']} ---")
        res = await query(item['q'], mode='hybrid')
        print(f"ENTITY TO FIND: {item['entity']}")
        print(f"CONTEXT COUNT: {len(res.get('context', []))}")
        
        for i, chunk in enumerate(res.get('context', [])[:3]):
            print(f"\nCHUNK {i+1} PREVIEW: {str(chunk)[:300]}...")
            found = item['entity'].lower() in str(chunk).lower()
            print(f"FOUND EXACT? {found}")

if __name__ == "__main__":
    asyncio.run(debug_evaluation())
