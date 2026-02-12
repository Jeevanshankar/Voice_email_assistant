from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

# Load model + tokenizer once
model_name = "google/flan-t5-base"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

def summarize_text(text):
    if not text or len(text.strip()) < 50:
        return "Email too short to summarize."

    # Trim long emails
    text = text[:2000]

    prompt = f"Summarize the following email:\n\n{text}"

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=1024
    )

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_length=150,
            num_beams=4,
            early_stopping=True
        )

    summary = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return summary
