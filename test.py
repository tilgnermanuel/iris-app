from flask import json
from app import app

payload = {
    'sepal_length': 1.,
    'sepal_width': 2.,
    'petal_length': 1.,
    'petal_width': .5
}


def test_app():
    response = app.test_client().post('/predict', data=payload)

    prediction = json.loads(response.get_data(as_text=True))['prediction'][0]

    assert prediction == 'iris-setosa'


