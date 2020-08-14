FROM python:3.7-slim
LABEL maintainer="tilgnermanuel"
WORKDIR /app
COPY requirements.txt app.py model.py test.py iris.mdl /app/
RUN pip3 install -r requirements.txt
ENTRYPOINT [ "python3" ]
CMD [ "app.py" ]
