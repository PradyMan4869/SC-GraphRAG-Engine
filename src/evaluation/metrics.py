"""
Generation-quality metrics: ROUGE-L, BLEU and LLM-as-a-Judge.

Retrieval metrics live in src/evaluation/retrieval_eval.py.

Caveats: the judge is the same local model that generated the answers and the
gold answers (self-preference bias), ROUGE/BLEU against a 1-2 sentence gold
answer mostly measure verbosity, and sentence-level BLEU on long answers is
nearly meaningless. Treat these as sanity checks, not headline numbers.
"""
import json
from rouge_score import rouge_scorer
import sacrebleu
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv

load_dotenv()
LM_STUDIO_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
JUDGE_MODEL = os.getenv("JUDGE_MODEL") or os.getenv("LM_STUDIO_MODEL", "default")
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
            model=JUDGE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=400,
        )
        content = response.choices[0].message.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        scores = json.loads(content)
        for k in ("accuracy", "reasoning", "completeness"):
            scores[k] = float(scores[k])
        return scores
    except Exception as e:
        # A failed judgement is *missing data*, not a score of zero: returning 0
        # would silently drag the mean down. Callers must skip `None` scores.
        print(f"Judge error: {e}")
        return {"accuracy": None, "reasoning": None, "completeness": None, "feedback": str(e)}
