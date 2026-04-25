import json
import os
import time

import pandas as pd
import numpy as np
from flask import Flask, render_template, request, jsonify

app = Flask(__name__, template_folder="templates", static_folder="static")

CURRENT_YEAR = 2026
AUTOCOMPLETE_LIMIT = 12
CSV_CACHE_TTL_SECONDS = 15
CSV_PATH = "UsedCars.csv"
CATALOG_PATH = "static/vehicle_catalog.json"

pipeline_instance = None
model_instance = None
model_metrics = {}
catalog_index = pd.DataFrame()
csv_cache = {
    'loaded_at': 0.0,
    'file_mtime': None,
    'data': pd.DataFrame(),
}


# Normalize any text input for case-insensitive and space-consistent matching.
def _normalize_text(value):
    return " ".join(str(value or "").strip().lower().split())


# Score how well a brand/model label matches a user query for autocomplete ranking.
def _score_match(brand_norm, model_norm, label_norm, query_norm):
    if not query_norm:
        return 1

    if (
        label_norm == query_norm
        or brand_norm == query_norm
        or model_norm == query_norm
    ):
        return 120
    if (
        label_norm.startswith(query_norm)
        or brand_norm.startswith(query_norm)
        or model_norm.startswith(query_norm)
    ):
        return 90
    if query_norm in label_norm:
        return 70
    return 0


# Build a deduplicated searchable index of brand/model pairs with listing counts.
def _build_search_index(df):
    grouped = (
        df.groupby(['brand', 'model'], dropna=False)
        .size()
        .reset_index(name='listing_count')
    )
    grouped['brand'] = grouped['brand'].fillna('').astype(str).str.strip()
    grouped['model'] = grouped['model'].fillna('').astype(str).str.strip()
    grouped = grouped[(grouped['brand'] != '') | (grouped['model'] != '')].copy()

    grouped['label'] = (grouped['brand'] + ' ' + grouped['model']).str.strip()
    grouped['brand_norm'] = grouped['brand'].map(_normalize_text)
    grouped['model_norm'] = grouped['model'].map(_normalize_text)
    grouped['label_norm'] = grouped['label'].map(_normalize_text)
    return grouped


# Load static catalog JSON once and transform it into a normalized in-memory index.
def _load_catalog_index():
    global catalog_index

    try:
        with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
            payload = json.load(f)

        rows = []
        models_by_brand = payload.get('modelsByBrand', {})
        for brand in payload.get('brands', []):
            for model in models_by_brand.get(brand, []):
                rows.append({'brand': brand, 'model': model})

        catalog_df = pd.DataFrame(rows)
        if catalog_df.empty:
            catalog_index = pd.DataFrame(
                columns=['brand', 'model', 'label', 'brand_norm', 'model_norm', 'label_norm']
            )
            return

        catalog_df = catalog_df.drop_duplicates(subset=['brand', 'model']).reset_index(drop=True)
        catalog_df['brand'] = catalog_df['brand'].fillna('').astype(str).str.strip()
        catalog_df['model'] = catalog_df['model'].fillna('').astype(str).str.strip()
        catalog_df['label'] = (catalog_df['brand'] + ' ' + catalog_df['model']).str.strip()
        catalog_df['brand_norm'] = catalog_df['brand'].map(_normalize_text)
        catalog_df['model_norm'] = catalog_df['model'].map(_normalize_text)
        catalog_df['label_norm'] = catalog_df['label'].map(_normalize_text)
        catalog_index = catalog_df
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        catalog_index = pd.DataFrame(
            columns=['brand', 'model', 'label', 'brand_norm', 'model_norm', 'label_norm']
        )


# Return cached operational CSV index, refreshing by TTL or file timestamp change.
def _get_operational_index():
    now = time.time()
    try:
        current_mtime = os.path.getmtime(CSV_PATH)
    except OSError:
        return pd.DataFrame(
            columns=[
                'brand', 'model', 'listing_count',
                'label', 'brand_norm', 'model_norm', 'label_norm',
            ]
        )

    is_fresh = (now - csv_cache['loaded_at']) < CSV_CACHE_TTL_SECONDS
    is_same_file = csv_cache['file_mtime'] == current_mtime
    if is_fresh and is_same_file and not csv_cache['data'].empty:
        return csv_cache['data']

    df = pd.read_csv(CSV_PATH, usecols=['name'])
    split_name = df['name'].astype(str).str.strip().str.split()
    df['brand'] = split_name.str[0].fillna('')
    df['model'] = split_name.str[1:].str.join(' ').fillna('')
    index_df = _build_search_index(df)

    csv_cache['loaded_at'] = now
    csv_cache['file_mtime'] = current_mtime
    csv_cache['data'] = index_df
    return index_df


# Filter and rank a search index by query and optional brand, then return top suggestions.
def _search_index(index_df, query, brand_filter, include_counts=False):
    if index_df.empty:
        return []

    query_norm = _normalize_text(query)
    filtered = index_df

    brand_filter_norm = _normalize_text(brand_filter)
    if brand_filter_norm:
        filtered = filtered[filtered['brand_norm'] == brand_filter_norm]

    if query_norm:
        exact_mask = (
            (filtered['label_norm'] == query_norm)
            | (filtered['brand_norm'] == query_norm)
            | (filtered['model_norm'] == query_norm)
        )
        prefix_mask = (
            filtered['label_norm'].str.startswith(query_norm)
            | filtered['brand_norm'].str.startswith(query_norm)
            | filtered['model_norm'].str.startswith(query_norm)
        )
        contains_mask = (
            filtered['label_norm'].str.contains(query_norm, regex=False)
            | filtered['brand_norm'].str.contains(query_norm, regex=False)
            | filtered['model_norm'].str.contains(query_norm, regex=False)
        )
        filtered = filtered[exact_mask | prefix_mask | contains_mask].copy()
    else:
        filtered = filtered.copy()

    if filtered.empty:
        return []

    filtered['match_score'] = filtered.apply(
        lambda row: _score_match(
            row['brand_norm'],
            row['model_norm'],
            row['label_norm'],
            query_norm,
        ),
        axis=1,
    )
    filtered = filtered[filtered['match_score'] > 0]
    if filtered.empty:
        return []

    sort_columns = ['match_score']
    ascending = [False]

    if include_counts and 'listing_count' in filtered.columns:
        sort_columns.append('listing_count')
        ascending.append(False)

    sort_columns.append('label')
    ascending.append(True)
    filtered = filtered.sort_values(sort_columns, ascending=ascending)

    records = []
    for _, row in filtered.head(AUTOCOMPLETE_LIMIT).iterrows():
        record = {
            'brand': row['brand'],
            'model': row['model'],
            'label': row['label'],
        }
        if include_counts and 'listing_count' in filtered.columns:
            record['listing_count'] = int(row['listing_count'])
        records.append(record)

    return records


# Feature pipeline that prepares tabular data for model training and inference.
class FullPipeline:
    # Initialize reusable preprocessing metadata and domain-specific brand flags.
    def __init__(self):
        self.numeric_cols = []
        self.mean_std = {}
        self.fill_values = {}
        self.feature_columns = []
        self.luxury_brands = ['BMW', 'Audi', 'Mercedes-Benz', 'Jaguar', 'Land', 'Volvo']

    # Create engineered features from the raw car attributes.
    def feature_engineering(self, df):
        df = df.copy()
        df['car_age'] = CURRENT_YEAR - df['year']
        df['km_per_year'] = df['km_driven'] / (df['car_age'] + 1)
        df['is_7_seater'] = (df['seats'] >= 7).astype(int)
        df['engine_power_ratio'] = df['engine'] / (df['max_power'] + 1)
        df['power_per_cc'] = df['max_power'] / (df['engine'] + 1)
        df['is_luxury'] = df['brand'].isin(self.luxury_brands).astype(int)
        return df

    # Fit preprocessing statistics on training data and return transformed features.
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

    # Apply learned preprocessing to new rows using fitted schema and scaling.
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


# Lightweight SGD-based linear regressor used for price prediction.
class SGDRegressor:
    # Store optimizer hyperparameters and model weights.
    def __init__(self, lr=0.01, epochs=450, l2=0.01, batch_size=32):
        self.lr = lr
        self.epochs = epochs
        self.l2 = l2
        self.batch_size = batch_size
        self.coef_ = None
        self.intercept_ = 0

    # Train the model using mini-batch gradient descent with L2 regularization.
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

    # Predict target values for transformed feature rows.
    def predict(self, X):
        X = np.asarray(X, dtype=np.float64)
        return np.dot(X, self.coef_) + self.intercept_


# Load dataset, train preprocessing/model objects, and compute quality metrics.
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


_load_catalog_index()


# Render the landing page.
@app.route('/')
def home_page():
    return render_template('index.html')


# Render the estimator page with the form UI.
@app.route('/estimate')
def estimate_page():
    return render_template('estimate.html')


# Render the about page.
@app.route('/about')
def about_page():
    return render_template('about.html')


# Serve tiered autocomplete suggestions from operational data with catalog fallback.
@app.route('/autocomplete', methods=['GET'])
def autocomplete():
    query = request.args.get('q', default='', type=str)
    brand_filter = request.args.get('brand', default='', type=str)

    operational_index = _get_operational_index()
    operational_results = _search_index(
        operational_index,
        query=query,
        brand_filter=brand_filter,
        include_counts=True,
    )

    if operational_results:
        return jsonify({
            'source': 'operational',
            'query': query,
            'brand_filter': brand_filter,
            'suggestions': [
                {**item, 'source': 'operational'} for item in operational_results
            ],
        })

    catalog_results = _search_index(
        catalog_index,
        query=query,
        brand_filter=brand_filter,
        include_counts=False,
    )

    return jsonify({
        'source': 'catalog',
        'query': query,
        'brand_filter': brand_filter,
        'suggestions': [
            {**item, 'source': 'catalog'} for item in catalog_results
        ],
    })

# dummy price shown now
# after final ML model, we replace it here


# Validate request data, run the pricing pipeline, and return formatted prediction.
@app.route('/predict', methods=['POST'])
def predict():

    try:
        if pipeline_instance is None or model_instance is None:
            initialize_and_train()

        # Support both AJAX JSON payloads and regular form submissions.
        is_json_request = request.is_json
        form_data = request.get_json(silent=True) if is_json_request else request.form.to_dict(flat=True)
        if not form_data:
            return jsonify({'error': 'No input data received.'}), 400

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
        # price = 500000
        
        # Format the price nicely
        formatted_price = f"NPR {int(price):,}"

        if is_json_request:
            return jsonify({'price': formatted_price, 'error': None})

        return render_template(
            'estimate.html',
            price=formatted_price,
            error=None,
            form_data=form_data
        )
    
    except Exception as e:
        if request.is_json:
            return jsonify({'price': None, 'error': str(e)}), 400

        return render_template(
            'estimate.html',
            price=None,
            error=str(e),
            form_data=request.form.to_dict(flat=True)
        )


if __name__ == '__main__':
    app.run(debug=True)
