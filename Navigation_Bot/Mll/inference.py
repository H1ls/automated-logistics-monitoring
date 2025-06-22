import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import json

MODEL_PATH = "./model"  # путь к папке с обученной LoRA-моделью
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_PATH).to(DEVICE)


def parse_text(input_text, max_new_tokens=256):
    input_ids = tokenizer(input_text, return_tensors="pt", truncation=True, max_length=512).input_ids.to(DEVICE)
    with torch.no_grad():
        output_ids = model.generate(
            input_ids,
            max_new_tokens=256,
            eos_token_id=tokenizer.eos_token_id,
            do_sample=False,
            num_beams=4,  # Жёстче следит за структурой
            repetition_penalty=1.1
        )
    output_str = tokenizer.decode(output_ids[0], skip_special_tokens=True)
    if output_str.startswith("<extra_id_0>"):
        output_str = output_str.replace("<extra_id_0>", "").strip()
    try:
        parsed = json.loads(output_str)
    except Exception:
        parsed = None
    return parsed, output_str


if __name__ == "__main__":
    sample = (
        "Преобразуй список адресов с датой и временем в строго валидный JSON-массив объектов: 03.02.2025, 12:00:00, Ростовская обл.. г. Ростов-на-Дону, ул. Природная, д. 2 Етел 89281888607 Андрей "
    )
    result, raw = parse_text(sample)
    print("MODEL OUTPUT:", raw)
    print("PARSED:", result)
