import os
import json
import torch
import evaluate
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSeq2SeqLM,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
    EarlyStoppingCallback
)
from peft import get_peft_model, LoraConfig, TaskType

# --- Пути ---
MODEL_NAME = "cointegrated/rut5-base"  # или "google/flan-t5-base"
DATASET_PATH  = os.path.join(os.path.dirname(__file__), "dataset.jsonl")
FEEDBACK_PATH = os.path.join(os.path.dirname(__file__), "feedback.jsonl")
OUTPUT_DIR    = os.path.join(os.path.dirname(__file__), "model")
LOG_DIR       = os.path.join(os.path.dirname(__file__), "logs")

# --- Устройство ---
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🚀 Тренировка будет запущена на: {device}")

# --- Утилиты ---
def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

def is_valid_output(obj):
    return (
        isinstance(obj, list)
        and all(isinstance(x, dict) and {"date","time","address"} <= set(x) for x in obj)
    )

# --- Загружаем датасеты ---
data = load_jsonl(DATASET_PATH)
if os.path.exists(FEEDBACK_PATH):
    data += load_jsonl(FEEDBACK_PATH)

cleaned = []
prompt = (
    "Извлеки все адресные блоки с датой и временем в формате JSON: "
)
for i, row in enumerate(data):
    # Покажем оригинал для первых 3
    if i < 3:
        print("ORIG INPUT:", row["input"])
        print("ORIG OUTPUT:", row.get("output", ""))
    row["input"] = prompt + row["input"].strip()
    out = row.get("output", [])
    if is_valid_output(out):
        row["output"] = json.dumps(out, ensure_ascii=False)
        cleaned.append(row)
    else:
        print("⛔ Пропущен невалидный output:", row.get("input"))

raw_ds = Dataset.from_list(cleaned)
split = raw_ds.train_test_split(test_size=0.1)

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

def preprocess(ex):
    inp = tokenizer(ex["input"], truncation=True, padding="max_length", max_length=512)
    tgt = tokenizer(ex["output"], truncation=True, padding="max_length", max_length=512)
    inp["labels"] = tgt["input_ids"]
    return inp

tokenized = split.map(preprocess, batched=False, remove_columns=raw_ds.column_names)

# Выводим 3 примера после токенизации
for j in range(3):
    print(f"== Токенизированный пример {j+1} ==")
    print("Decoded input :", tokenizer.decode(tokenized['train'][j]['input_ids'], skip_special_tokens=True))
    print("Decoded output:", tokenizer.decode(tokenized['train'][j]['labels'], skip_special_tokens=True))

# --- Метрика BLEU ---
bleu = evaluate.load("bleu")
def post(text): return text.strip()
def compute_metrics(p):
    preds, labels = p
    dp = tokenizer.batch_decode(preds, skip_special_tokens=True)
    dl = tokenizer.batch_decode(labels, skip_special_tokens=True)
    dp = [post(x) for x in dp]
    dl = [post(x) for x in dl]
    return {"bleu": bleu.compute(predictions=dp, references=[[l] for l in dl])["bleu"]}

# --- Модель и LoRA ---
# base_model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME).to(device)
if os.path.exists(OUTPUT_DIR):
    base_model = AutoModelForSeq2SeqLM.from_pretrained(OUTPUT_DIR).to(device)
else:
    base_model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME).to(device)

lora_cfg   = LoraConfig(
    r=8,
    lora_alpha=16,
    target_modules=["q","v"],
    lora_dropout=0.1,
    bias="none",
    task_type=TaskType.SEQ_2_SEQ_LM
)
model = get_peft_model(base_model, lora_cfg)

# --- Аргументы обучения с валидацией по эпохе ---
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=4,
    num_train_epochs=10,
    logging_dir=LOG_DIR,
    logging_steps=10,
    report_to="none",
    disable_tqdm=False
)

# --- Trainer с EarlyStopping по BLEU ---
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized["train"],
    eval_dataset=tokenized["test"],
    tokenizer=tokenizer,
    data_collator=DataCollatorForSeq2Seq(tokenizer, model=model),
    compute_metrics=compute_metrics,
    # callbacks=[EarlyStoppingCallback]  # <- закомментировать
)
# --- Запуск ---
model.print_trainable_parameters()
trainer.train()

# --- Сохранение финальной модели и токенизатора ---
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
