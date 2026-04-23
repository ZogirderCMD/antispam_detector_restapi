from transformers import AutoTokenizer, AutoModelForSequenceClassification
from flask import Flask, make_response
import psycopg2, os, datetime, re, torch, sys


def log(text):
    try:
        was_txt = open("logs.txt", "r").read()
    except OSError:
        open("logs.txt", "w").write("")
        was_txt = open("logs.txt", "r").read()
    txt = f"[{datetime.datetime.now()}]: {text}"
    open("logs.txt", "w").write(f"{was_txt}{txt}\n")
    print(txt)

log("Starting service...")

try:
    class SpamDetector:
        model_name = 'RUSpam/spamNS_v1'
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=1).to(device).eval()
        tokenizer = AutoTokenizer.from_pretrained(model_name)

        is_spam = False

        def __init__(self, text):
            self.classify_message(text)

        def clean_text(self, text):
            text = re.sub(r'http\S+', '', text)
            text = re.sub(r'[^А-Яа-я0-9 ]+', ' ', text)
            text = text.lower().strip()
            return text

        def classify_message(self, message):
            message = self.clean_text(message)
            encoding = self.tokenizer(message, padding='max_length', truncation=True, max_length=128, return_tensors='pt')
            input_ids = encoding['input_ids'].to(self.device)
            attention_mask = encoding['attention_mask'].to(self.device)

            with torch.no_grad():
                outputs = self.model(input_ids, attention_mask=attention_mask).logits
                pred = torch.sigmoid(outputs).cpu().numpy()[0][0]

            self.is_spam = pred >= 0.5
except:
    log("Failed to load antispam agent")
    sys.exit()

try:
    con = psycopg2.connect(
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        database=os.getenv("POSTGRES_DB")
    )
except:
    log("Failed connection to database")
    sys.exit()

cur = con.cursor()

def query(q):
    try:
        cur.execute(q)
        con.commit()
    except Exception as e:
        log(f"Error in sql query, queried \" {q} \", got \" {e} \"")
        con.rollback()