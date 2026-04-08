"""
Core metrics for Supreme Court GraphRAG evaluation.
Includes: ROUGE-L, BLEU, Context Signal-to-Noise, and LLM-as-a-Judge.
"""
import json
from rouge_score import rouge_scorer
import sacrebleu
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv

load_dotenv()
LM_STUDIO_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
client = AsyncOpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")

def calculate_text_metrics(prediction: str | list, reference: str | list) -> dict:
    """Calculate ROUGE and BLEU scores for text overlap."""
    if isinstance(prediction, list): prediction = " ".join(prediction)
    if isinstance(reference, list): reference = " ".join(reference)
    
    # ROUGE-L
    scorer = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=True)
    rouge_l = scorer.score(reference, prediction)['rougeL'].fmeasure
    
    # BLEU
    bleu = sacrebleu.sentence_bleu(prediction, [reference]).score / 100.0
    
    return {
        "rouge_l": round(rouge_l, 4),
        "bleu": round(bleu, 4)
    }

async def llm_judge(question: str, prediction: str, reference: str) -> dict:
    """Use LLM-as-a-Judge to evaluate semantic accuracy and legal reasoning."""
    prompt = f"""
    You are a Senior Supreme Court Judge. Evaluate the 'Assistant Answer' against the 'Gold Standard'.
    
    QUESTION: {question}
    GOLD STANDARD: {reference}
    ASSISTANT ANSWER: {prediction}
    
    SCORING CRITERIA (1-10):
    1. Accuracy: Does it match the gold standard's facts?
    2. Reasoning: Is the legal logic sound?
    3. Completeness: Did it miss any key legal nuances mentioned in the gold standard?
    
    RESPONSE FORMAT (JSON):
    {{
        "accuracy": 8,
        "reasoning": 9,
        "completeness": 7,
        "feedback": "..."
    }}
    """
    try:
        response = await client.chat.completions.create(
            model="default",
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        scores = json.loads(content)
        return scores
    except Exception as e:
        print(f"Judge error: {e}")
        return {"accuracy": 0, "reasoning": 0, "completeness": 0, "feedback": str(e)}

def calculate_graph_metrics(retrieved_entities: list, relevant_entities: list) -> dict:
    """
    Comprehensive Retrieval Metrics: Recall, Precision, F1, and MRR.
    """
    if not relevant_entities:
        return {
            "recall": 1.0, "precision": 1.0, "f1": 1.0, "mrr": 1.0,
            "snr_db": 20.0 # Perfect signal
        }
    
    retrieved_set = set(retrieved_entities)
    relevant_set = set(relevant_entities)
    
    hits = retrieved_set.intersection(relevant_set)
    recall = len(hits) / len(relevant_set)
    precision = len(hits) / len(retrieved_set) if retrieved_set else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    # Simple MRR based on first hit in retrieved list
    mrr = 0.0
    for i, entity in enumerate(retrieved_entities, 1):
        if entity in relevant_set:
            mrr = 1.0 / i
            break

    # Context Signal-to-Noise Ratio (SNR)
    # Ratio of relevant entities to total entities in context
    snr = len(hits) / (len(retrieved_set) - len(hits) + 1) # +1 to avoid div by zero
    import math
    snr_db = 10 * math.log10(snr) if snr > 0 else -20.0

    return {
        "entity_recall": round(recall, 4),
        "entity_precision": round(precision, 4),
        "f1_score": round(f1, 4),
        "mrr": round(mrr, 4),
        "snr_db": round(snr_db, 2)
    }
