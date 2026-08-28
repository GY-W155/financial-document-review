FROM python:3.11-slim

WORKDIR /app

COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt

COPY app ./app
RUN mkdir -p /app/uploads

ENV DATABASE_URL=mysql+asyncmy://root:123456@mysql:3306/financial_doc_review
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
