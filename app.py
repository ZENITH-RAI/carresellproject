import pandas as pd
import numpy as np
from flask import Flask, render_template, request

app = Flask(__name__, template_folder="templates")

# ---------------------------------------------------------
# GLOBAL VARIABLES FOR MODEL AND METRICS
# ---------------------------------------------------------
CURRENT_YEAR = 2025
pipeline_instance = None
model_instance = None
model_metrics = {}
 
# --- PASTE YOUR CUSTOM CLASSES HERE ---
class FullPipeline:
    def __init__(self):
        self.numeric_cols = []
        self.mean_std = {}
        self.fill_values = {}
        self.feature_columns = []
        self.luxury_brands = ['BMW', 'Audi', 'Mercedes-Benz', 'Jaguar', 'Land', 'Volvo']

    def feature_engineering(self, df):
        df = df.copy()
        df['car_age'] = CURRENT_YEAR - df['year']
        df['km_per_year'] = df['km_driven'] / (df['car_age'] + 1)
        df['is_7_seater'] = (df['seats'] >= 7).astype(int)
        df['engine_power_ratio'] = df['engine'] / (df['max_power'] + 1)
        df['power_per_cc'] = df['max_power'] / (df['engine'] + 1)
        df['is_luxury'] = df['brand'].isin(self.luxury_brands).astype(int)
        return df

    def fit(self, df):
        df = self.feature_engineering(df)
        df = df.drop(columns=['selling_price'], errors='ignore')
        df = pd.get_dummies(df, drop_first=True)
        self.numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
        self.fill_values = df.mean(numeric_only=True)
        df = df.fillna(self.fill_values)
        
        for col in self.numeric_cols:
            mean = df[col].mean()
            std = df[col].std()
            if std == 0: std = 1
            self.mean_std[col] = (mean, std)
            df[col] = (df[col] - mean) / std
            
        self.feature_columns = df.columns.tolist()
        return df

    def transform(self, df):
        df = self.feature_engineering(df)
        df = pd.get_dummies(df, drop_first=True)
        
        missing_cols = list(set(self.feature_columns) - set(df.columns))
        if missing_cols:
            df_missing = pd.DataFrame(0, index=df.index, columns=missing_cols)
            df = pd.concat([df, df_missing], axis=1)
            
        df = df[self.feature_columns].copy()
        
        for col in self.numeric_cols:
            mean, std = self.mean_std[col]
            df[col] = (df[col] - mean) / std
        return df

class SGDRegressor:
    def __init__(self, lr=0.01, epochs=450, l2=0.01, batch_size=32):
        self.lr = lr
        self.epochs = epochs
        self.l2 = l2
        self.batch_size = batch_size
        self.coef_ = None
        self.intercept_ = 0

    def fit(self, X, y):
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        n, m = X.shape
        self.coef_ = np.zeros(m)

        for epoch in range(self.epochs):
            lr = self.lr / (1 + 0.01 * epoch)
            indices = np.random.permutation(n)
            X = X[indices]
            y = y[indices]

            for start in range(0, n, self.batch_size):
                end = start + self.batch_size
                X_batch = X[start:end]
                y_batch = y[start:end]
                y_pred = np.dot(X_batch, self.coef_) + self.intercept_
                error = y_pred - y_batch
                grad_w = (2 / len(X_batch)) * np.dot(X_batch.T, error) + 2 * self.l2 * self.coef_
                grad_b = 2 * np.mean(error)
                self.coef_ -= lr * grad_w
                self.intercept_ -= lr * grad_b

    def predict(self, X):
        X = np.asarray(X, dtype=np.float64)
        return np.dot(X, self.coef_) + self.intercept_

# ---------------------------------------------------------
# INITIALIZATION & TRAINING ROUTINE
# ---------------------------------------------------------
def initialize_and_train():
    global pipeline_instance, model_instance, model_metrics
    print("Loading data and training model... This may take a moment.")
    
    np.random.seed(42)
    df = pd.read_csv("UsedCars.csv")
    df['selling_price'] = df['selling_price'] * 2.2
    df = df.drop(columns=['torque'], errors='ignore')
    df = df.drop_duplicates()
    
    df['brand'] = df['name'].str.split().str[0]
    df['model'] = df['name'].str.split().str[1:].str.join(' ')
    df = df.drop(columns=['name'])
    
    for col, suffix in [('mileage', ' kmpl'), ('engine', ' CC'), ('max_power', ' bhp')]:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(suffix, '', regex=False), errors='coerce')
        
    q1 = df['selling_price'].quantile(0.01)
    q99 = df['selling_price'].quantile(0.99)
    df = df[(df['selling_price'] >= q1) & (df['selling_price'] <= q99)]
    
    top_models = df['model'].value_counts().head(25).index
    df['model'] = df['model'].apply(lambda x: x if x in top_models else "Other")
    df['brand_model'] = df['brand'] + "_" + df['model']
    
    train = df.sample(frac=0.8, random_state=42)
    test = df.drop(train.index)

    pipeline_instance = FullPipeline()
    X_train = pipeline_instance.fit(train)
    X_test = pipeline_instance.transform(test)

    y_train = np.log1p(train['selling_price'])
    y_test = np.log1p(test['selling_price'])

    model_instance = SGDRegressor()
    model_instance.fit(X_train, y_train)

    y_pred_log = model_instance.predict(X_test)
    y_pred = np.expm1(y_pred_log)
    y_true = np.expm1(y_test)

    # Calculate Metrics
    mse = np.mean((y_true - y_pred) ** 2)
    mae = np.mean(np.abs(y_true - y_pred))
    r2 = 1 - (np.sum((y_true - y_pred) ** 2) / np.sum((y_true - np.mean(y_true)) ** 2))
    mape = np.mean(np.abs((y_true - y_pred) / y_true)) * 100

    model_metrics = {
        'R2': round(r2, 4),
        'MAE': round(mae, 2),
        'MSE': round(mse, 2),
        'MAPE': f"{round(mape, 2)}%"
    }
    print("Training complete! Server ready.")

# Run training before requests
initialize_and_train()

# ---------------------------------------------------------
# FLASK ROUTES
# ---------------------------------------------------------
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', metrics=model_metrics, price=None)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/estimate')
def estimate():
    return render_template('estimate.html', metrics=model_metrics, price=None, error=None, form_data={})

@app.route('/predict', methods=['POST'])
def predict():
    # Extract form data and convert types safely
    try:
        form_data = request.form.to_dict(flat=True)
        user_input = {
            'year': int(form_data['year']),
            'km_driven': float(form_data['km_driven']),
            'fuel': form_data['fuel'],
            'seller_type': form_data['seller_type'],
            'transmission': form_data['transmission'],
            'owner': form_data['owner'],
            'mileage': float(form_data['mileage']) if form_data.get('mileage') else None,
            'engine': float(form_data['engine']),
            'max_power': float(form_data['max_power']),
            'seats': float(form_data['seats']),
            'brand': form_data['brand'],
            'model': form_data['model'],
            'brand_model': f"{form_data['brand']}_{form_data['model']}"
        }

        user_df = pd.DataFrame([user_input])
        processed = pipeline_instance.transform(user_df)
        pred_log = model_instance.predict(processed)
        price = float(np.expm1(pred_log[0]))
        
        # Format the price nicely
        formatted_price = f"NPR {int(price):,}"
        
        return render_template(
            'estimate.html',
            metrics=model_metrics,
            price=formatted_price,
            error=None,
            form_data=form_data
        )
    
    except Exception as e:
        return render_template(
            'estimate.html',
            metrics=model_metrics,
            price=None,
            error=str(e),
            form_data=request.form.to_dict(flat=True)
        )

if __name__ == '__main__':

    app.run(debug=True)
