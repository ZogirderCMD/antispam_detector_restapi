FROM python:3.12

WORKDIR /detector

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY schema.sql .
COPY templates/. templates/.

EXPOSE 8000

CMD ["python", "main.py"]