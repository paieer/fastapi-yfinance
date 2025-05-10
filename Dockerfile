FROM python:3.11-slim

WORKDIR /app/
ADD requirements.txt /app/

RUN pip install -r requirements.txt

ADD . /app/

CMD ["hypercorn", "main:app", "-b", "0.0.0.0:3000", "--reload"]