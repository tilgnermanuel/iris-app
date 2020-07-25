FROM python:3.7-slim
RUN mkdir /app
WORKDIR /app
COPY requirements.txt app.py model.py test.py iris.mdl /app/
RUN pip3 install -r requirements.txt
EXPOSE 8080
ENTRYPOINT [ "python3" ]
CMD [ "app.py" ]
