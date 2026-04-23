from transformers import AutoTokenizer, AutoModelForSequenceClassification
from flask import Flask, make_response, request
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
        pred:float=0.0

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
                self.pred = torch.sigmoid(outputs).cpu().numpy()[0][0]

            self.is_spam = self.pred >= 0.5
except:
    log("Failed to load antispam agent")
    sys.exit()

class HistoryRequest:
    text:str=""
    spam:bool=False
    model_name:str=""
    pred:float=0.0
    
    def req(self, text=None):
        if not text is None: 
            self.text = text
            try:
                sd = SpamDetector(text)
                self.spam = sd.is_spam
                self.model_name = sd.model_name
                self.pred = sd.pred
                query(f"INSERT INTO (input_text, spam, model_name, pred) requests_history VALUES ({self.text, self.spam, self.model_name, self.pred})")
                log(f"User made request with text: \" {text} \", result: {"POSITIVE" if self.spam else "NEGATIVE"}, prdiction score: {self.pred}")
                return make_response({"result": "POSITIVE" if self.spam else "NEGATIVE", "score": self.pred}, 200)
            except Exception as e:
                log(f"Error on model: {e}")
        else:
            log(f"User made request with empty text!")
            return make_response({"result": "Text area is empty!"}, 403)

def getHistory(typ=1, ids=None):
    if typ == 1:
        query("SELECT id, model_name, created_at FROM requests_history ORDER BY created_at DESC LIMIT 20")
        res = []
        for i in cur.fetchall():
            res.append({"id": i[0],"model_name": i[1],"created_at": i[2]})
        log(f"User get last 20 requests")
        return make_response({"result": res}, 200)
    if typ == 2:
        if ids is None:
            log(f"User made request with empty ID!")
            return make_response({"result": "Request ID is empty!"}, 403)
        else:
            query(f"SELECT input_text, spam, pred FROM requests_history WHERE id={ids}")
            try:
                res = cur.fetchall()
                log(f"User get request with ID: {ids}")
                return make_response({"input_text":res[0], "result": "POSITIVE" if res[1] else "NEGATIVE", "score": res[2]}, 200)
            except:
                log(f"User made request with unknown ID: {ids}")
                return make_response({"result": "Unknown request ID!"}, 403)


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

try:
    query(open("schema.sql","r").read())
except:
    log("Failed to load schema")

app = Flask(__name__)

@app.route("/analyze", methods=["POST"])
def analyze():
    return HistoryRequest().req(request.form.get('text', None))

@app.route("/history", methods=["GET"])
def history():
    return getHistory()

@app.route("/history/<int:ids>", methods=["GET"])
def historys(ids):
    return getHistory(2, ids)

@app.route("/health", methods=["GET"])
def health():
    return make_response({"status": "ok"}, 200)

app.route(port=8000)