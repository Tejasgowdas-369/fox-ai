import os
from pathlib import Path

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# In-Memory Only Guarantee
# Fox AI stores nothing — all data lives in RAM and is wiped when the app closes.
# No SQLite, no JSON files, no logging of conversation contents to disk.
IN_MEMORY_GUARANTEE = "Fox AI stores nothing — all data lives in RAM and is wiped when the app closes."

# Default Configuration
MODEL_PATH = os.getenv(
    "MODEL_PATH",
    str(BASE_DIR / "models" / "gemma-2-2b-it-Q4_K_M.gguf")
)
N_CTX = int(os.getenv("N_CTX", "4096"))
N_THREADS = int(os.getenv("N_THREADS", "4"))

def format_prompt(messages: list, model_name: str) -> str:
    """
    Formats the conversation history into the model's required template.
    Autodetects templates for Gemma-2 and Phi-3, with a fallback for generic instruct models.
    """
    model_lower = model_name.lower()
    
    # 1. Gemma 2 Instruct Template
    if "gemma-2" in model_lower or "gemma2" in model_lower:
        prompt = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            mapped_role = "model" if role == "assistant" else role
            prompt += f"<start_of_turn>{mapped_role}\n{content}<end_of_turn>\n"
        prompt += "<start_of_turn>model\n"
        return prompt

    # 2. Phi 3 Instruct Template
    elif "phi-3" in model_lower or "phi3" in model_lower:
        prompt = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            prompt += f"<|{role}|>\n{content}<|end|>\n"
        prompt += "<|assistant|>\n"
        return prompt

    # 3. ChatML Template (Qwen, TinyLlama)
    elif "qwen" in model_lower or "tinyllama" in model_lower:
        prompt = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
        prompt += "<|im_start|>assistant\n"
        return prompt

    # 4. Llama 3 / 3.2 Instruct Template
    elif "llama-3" in model_lower or "llama3" in model_lower:
        prompt = "<|begin_of_text|>"
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            prompt += f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>"
        prompt += "<|start_header_id|>assistant<|end_header_id|>\n\n"
        return prompt

    # 5. Fallback Instruct Template
    else:
        prompt = ""
        for msg in messages:
            role = msg["role"].capitalize()
            content = msg["content"]
            prompt += f"{role}: {content}\n"
        prompt += "Assistant: "
        return prompt

