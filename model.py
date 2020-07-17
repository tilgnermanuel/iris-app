import pandas as pd
import joblib
from sklearn import datasets 
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics import accuracy_score


def fit_model(X, y):
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=.2)

    knn = KNeighborsClassifier(n_neighbors=1)

    knn.fit(X_train, y_train)

    preds = knn.predict(X_test)

    acc = accuracy_score(y_test, preds)

    print(f'Successfully trained model with accuracy of {acc:.2f}')

    return knn


if __name__ == '__main__':
    iris_data = datasets.load_iris()
    
    columns = ['sepal_length', 'sepal_width', 'petal_length', 'petal_width']
    target = {0: 'iris-setosa', 1: 'iris-versicolor', 2: 'iris-virginica'}

    X = pd.DataFrame(iris_data['data'], columns=columns)
    y = pd.Series(iris_data['target']).map(target)

    model = fit_model(X, y)

    joblib.dump(model, 'iris.mdl')
