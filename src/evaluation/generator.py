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
GEN_MODEL = os.getenv("LM_STUDIO_MODEL", "default")
SEED = int(os.getenv("EVAL_SEED", "1234"))  # reproducible question set
N_QUESTIONS = int(os.getenv("EVAL_N_QUESTIONS", "300"))
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "storage"))

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
            model=GEN_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=500,
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

MAX_PER_DOC = int(os.getenv("EVAL_MAX_PER_DOC", "3"))  # stop long judgments dominating
CONCURRENCY = int(os.getenv("EVAL_CONCURRENCY", "4"))


async def main():
    mapping_path = STORAGE_DIR / "kv_store_entity_chunks.json"
    chunks_path = STORAGE_DIR / "kv_store_text_chunks.json"
    if not mapping_path.exists() or not chunks_path.exists():
        print("Required storage files not found.")
        return

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    all_chunks = json.loads(chunks_path.read_text(encoding="utf-8"))

    # Entities mentioned in >=3 chunks (skips one-off mentions); sorted then
    # shuffled with a fixed seed so the question set is reproducible.
    candidates = sorted(k for k, v in mapping.items() if len(v.get("chunk_ids", [])) >= 3)
    rng = random.Random(SEED)
    rng.shuffle(candidates)
    print(f"{len(candidates)} candidate entities; target {N_QUESTIONS} questions "
          f"(<= {MAX_PER_DOC} per document, generator model: {GEN_MODEL})")

    # Pick (entity, chunk) jobs up front, enforcing the per-document cap.
    per_doc: dict[str, int] = {}
    jobs = []
    for entity in candidates:
        if len(jobs) >= N_QUESTIONS * 2:  # headroom for generation failures
            break
        chunk_id = rng.choice(mapping[entity]["chunk_ids"])
        chunk = all_chunks.get(chunk_id)
        if not chunk or len(chunk.get("content", "")) < 200:
            continue
        doc = chunk.get("full_doc_id", chunk_id)
        if per_doc.get(doc, 0) >= MAX_PER_DOC:
            continue
        per_doc[doc] = per_doc.get(doc, 0) + 1
        jobs.append((entity, chunk_id, doc, chunk["content"]))

    sem = asyncio.Semaphore(CONCURRENCY)

    async def work(job):
        entity, chunk_id, doc, text = job
        async with sem:
            pair = await generate_qa_pair(text, entity)
        if pair:
            pair["reference_chunk_id"] = chunk_id
            pair["doc_id"] = doc
        return pair

    results = await asyncio.gather(*(work(j) for j in jobs))
    ground_truth = [r for r in results if r][:N_QUESTIONS]

    output_path = STORAGE_DIR / "ground_truth.json"
    output_path.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")
    print(f"\nDone! Saved {len(ground_truth)} pairs from {len({g['doc_id'] for g in ground_truth})} documents to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
