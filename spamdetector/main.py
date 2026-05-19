from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
from flask import Flask, make_response, request, abort
import psycopg2, os, datetime, re, torch, sys

try: os.mkdir("logs")
except FileExistsError: pass

adm_token = os.getenv("ADMIN_TOKEN")

def log(text):
    dt = datetime.datetime.now()
    date = dt.date()
    tim = str(dt.time()).split(".")[0]
    try:
        was_txt = open(f"logs/{date}.txt", "r").read()
    except OSError:
        open(f"logs/{date}.txt", "w").write("")
        was_txt = open(f"logs/{date}.txt", "r").read()
    txt = f"[{tim}] {text}"
    open(f"logs/{date}.txt", "w").write(f"{was_txt}{txt}\n")
    print(txt)

def get_logs():
    return make_response({"result": [i.split(".")[0] for i in os.listdir("logs")]}, 200)

def get_logg(date):
    j = {}
    try:
        for i in open(f"logs/{date}.txt", "r").read().split("\n"):
            s = i.split(" ")
            if len(s) > 0: j[s[0]] = " ".join(s[1:])
        return make_response({"result": j}, 200)
    except FileNotFoundError: return make_response({"result": "Log file with this date wasn't found!"}, 404)

log("Starting service...")

try:
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tokenisers = {
        'RUSpam/spamNS_v1': AutoTokenizer.from_pretrained('RUSpam/spamNS_v1'),
        'corall88/russian_spam_detector': AutoTokenizer.from_pretrained('corall88/russian_spam_detector')
    }
    models = {
        'RUSpam/spamNS_v1': AutoModelForSequenceClassification.from_pretrained('RUSpam/spamNS_v1', num_labels=1).to(device).eval(),
        'corall88/russian_spam_detector': AutoModelForSequenceClassification.from_pretrained('corall88/russian_spam_detector')
    }
    class SpamDetector:
        model_name = 'RUSpam/spamNS_v1'

        is_spam = False
        pred:float=0.0

        def __init__(self, text, modell='RUSpam/spamNS_v1'):
            self.model_name = modell
            self.tokenizer = tokenisers[self.model_name]
            self.mode = models[self.model_name]
            match (self.model_name):
                case 'corall88/russian_spam_detector':
                    self.detector = pipeline("text-classification", model=self.model_name, tokenizer=self.tokenizer)

            self.classify_message(text)

        def clean_text(self, text):
            text = re.sub(r'http\S+', '', text)
            text = re.sub(r'[^А-Яа-я0-9 ]+', ' ', text)
            text = text.lower().strip()
            return text

        def classify_message(self, message):
            match (self.model_name):
                case 'RUSpam/spamNS_v1':
                    message = self.clean_text(message)
                    encoding = self.tokenizer(message, padding='max_length', truncation=True, max_length=128, return_tensors='pt')
                    input_ids = encoding['input_ids'].to(self.device)
                    attention_mask = encoding['attention_mask'].to(self.device)

                    with torch.no_grad():
                        outputs = self.model(input_ids, attention_mask=attention_mask).logits
                        self.pred = torch.sigmoid(outputs).cpu().numpy()[0][0]

                    self.is_spam = self.pred >= 0.5
                case 'corall88/russian_spam_detector':
                    result = self.detector(message)
                    self.pred = result[0].get("score")
                    self.is_spam = True if result[0].get("label") == "LABEL_1" else False
except:
    log("Failed to load antispam agent")
    sys.exit()

class HistoryRequest:
    text:str=""
    spam:bool=False
    model_name:str=""
    pred:float=0.0
    
    def req(self, text=None, model='RUSpam/spamNS_v1'):
        if not text is None: 
            self.text = text
            try:
                sd = SpamDetector(text, model)
                self.spam = sd.is_spam
                self.model_name = sd.model_name
                self.pred = sd.pred
                query(f"INSERT INTO requests_history (input_text, spam, model_name, pred) VALUES ('{self.text}', {self.spam}, '{self.model_name}', {self.pred})")
                log(f"User made request with text: \" {text} \", result: {"POSITIVE" if self.spam else "NEGATIVE"}, prediction score: {self.pred}")
                return make_response({"result": "POSITIVE" if self.spam else "NEGATIVE", "score": str(self.pred)}, 200)
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
            log(f"User get request with ID: {ids}")
            query(f"SELECT input_text, spam, pred FROM requests_history WHERE id={ids}")
            try:
                res = cur.fetchall()[0]
                return make_response({"input_text":res[0], "result": "POSITIVE" if res[1] else "NEGATIVE", "score": str(res[2])}, 200)
            except Exception as e:
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
    return HistoryRequest().req(request.form.get('text', None), request.form.get('model', 'RUSpam/spamNS_v1'))

@app.route("/history", methods=["GET"])
def history():
    return getHistory()

@app.route("/history/<int:ids>", methods=["GET"])
def historys(ids):
    return getHistory(2, int(ids))

@app.route("/health", methods=["GET"])
def health():
    return make_response({"status": "ok"}, 200)

@app.route("/<adt>/all_logs", methods=["GET"])
def all_logs(adt):
    if adt != adm_token: abort(404)
    else: return get_logs()

@app.route("/<adt>/get_log/<date>", methods=["GET"])
def get_log(adt, date):
    if adt != adm_token: abort(404)
    else: return get_logg(date)

log("Service started!")

app.run(host="0.0.0.0", port=8000)
