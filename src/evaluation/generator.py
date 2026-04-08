"""
Synthetic Ground Truth Generator for Supreme Court GraphRAG.
Generates Q&A pairs from existing text chunks to serve as a 'Gold Standard' for evaluation.
"""
import json
import random
import asyncio
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os

# Load env for LM Studio URL
load_dotenv()
LM_STUDIO_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
STORAGE_DIR = Path("storage")

client = AsyncOpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")

async def generate_qa_pair(chunk_text: str, entity_name: str) -> dict | None:
    """Ask the LLM to generate a question and answer based on the provided text."""
    prompt = f"""
    You are a legal expert evaluating a GraphRAG system.
    Below is a snippet from a Supreme Court judgment related to '{entity_name}'.
    
    TEXT SNIPPET:
    {chunk_text}
    
    TASK:
    1. Generate a specialized legal question that can be answered using ONLY this text.
    2. Provide the correct 'Gold Standard' answer.
    
    RESPONSE FORMAT (JSON):
    {{
        "question": "...",
        "answer": "..."
    }}
    """
    
    try:
        response = await client.chat.completions.create(
            model="default", 
            messages=[{"role": "user", "content": prompt}]
        )
        # Attempt to find JSON in the content (some models wrap it in ```json)
        content = response.choices[0].message.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        data = json.loads(content)
        return {
            "entity": entity_name,
            "question": data["question"],
            "ground_truth": data["answer"]
        }
    except Exception as e:
        print(f"Error generating for {entity_name}: {e}")
        return None

async def main():
    # 1. Load entity-chunk mapping
    mapping_path = STORAGE_DIR / "kv_store_entity_chunks.json"
    chunks_path = STORAGE_DIR / "kv_store_text_chunks.json"
    
    if not mapping_path.exists() or not chunks_path.exists():
        print("Required storage files not found.")
        return

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    all_chunks = json.loads(chunks_path.read_text(encoding="utf-8"))

    # 2. Filter for significant entities (those with at least 5 chunks)
    candidates = [k for k, v in mapping.items() if len(v.get("chunk_ids", [])) >= 3]
    selected_entities = random.sample(candidates, min(len(candidates), 15))

    print(f"Generating ground truth for {len(selected_entities)} entities...")
    
    ground_truth = []
    for entity in selected_entities:
        chunk_id = random.choice(mapping[entity]["chunk_ids"])
        chunk_data = all_chunks.get(chunk_id)
        if not chunk_data:
            continue
            
        text = chunk_data.get("content", "")
        if len(text) < 200: continue # Skip very short chunks
        
        pair = await generate_qa_pair(text, entity)
        if pair:
            pair["reference_chunk_id"] = chunk_id
            ground_truth.append(pair)
            print(f"  + Generated for: {entity}")

    # 3. Save
    output_path = STORAGE_DIR / "ground_truth.json"
    output_path.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")
    print(f"\nDone! Saved {len(ground_truth)} pairs to {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
