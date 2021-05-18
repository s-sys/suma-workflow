FROM python:3.7

EXPOSE 8005
STOPSIGNAL SIGINT

ADD "./requirements.txt" "/data/requirements.txt"

RUN pip3 install --no-cache-dir -r "/data/requirements.txt"

WORKDIR "/data/"
ADD "." "/data/"

CMD ["python3", "/data/jira_integration.py"]
