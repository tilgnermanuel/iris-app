import pandas as pd
from flask import Flask, request, jsonify
import joblib

app = Flask(__name__)

model = joblib.load('iris.mdl')

@app.route('/', methods=['GET'])
def home_page():
    return 'Iris Dataset Prediction API. Send your POST request to /predict'


@app.route('/predict', methods=['POST'])
def predict():
    try:
        petal_length = request.form['petal_length']
        petal_width = request.form['petal_width']
        sepal_length = request.form['sepal_length']
        sepal_width = request.form['sepal_width']

        data = pd.DataFrame(data=[[petal_length, petal_width,
                                   sepal_length, sepal_width]],
                            columns=['petal_length', 'petal_width',
                                     'sepal_length', 'sepal_width'],
                            dtype=float)

        prediction = list(model.predict(data))

        return jsonify({'prediction': prediction})
    except:
        return jsonify('Something went wrong. Please check your input.')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(5000))
