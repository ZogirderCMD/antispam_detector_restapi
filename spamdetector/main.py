from transformers import AutoTokenizer, AutoModelForSequenceClassification
from flask import Flask, make_response
import psycopg2, os, datetime, torch


def log(text):
    try:
        was_txt = open("logs.txt", "r").read()
    except OSError:
        open("logs.txt", "w").write("\n")
        was_txt = open("logs.txt", "r").read()
    txt = f"[{datetime.datetime.now()}]: {text}"
    open("logs.txt", "w").write(f"{was_txt}{txt}\n")
    print(txt)

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

cur = con.cursor()

def query(a):
    try:
        cur.execute(a)
        con.commit()
    except Exception as e:
        log(f"Error in sql query, queried \" {a} \", got \" {e} \"")
        con.rollback()