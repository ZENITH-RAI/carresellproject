import json

import pandas as pd
from flask import Flask, render_template, request, jsonify

app = Flask(__name__, template_folder="templates", static_folder="static")

AUTOCOMPLETE_LIMIT = 12
CSV_PATH = "UsedCars.csv"
CATALOG_PATH = "static/vehicle_catalog.json"
DUMMY_PRICE_NPR = "NPR 500,000"
INDEX_COLUMNS = ['brand', 'model', 'label', 'brand_norm', 'model_norm', 'label_norm']
INDEX_COLUMNS_WITH_COUNT = ['brand', 'model', 'listing_count', 'label', 'brand_norm', 'model_norm', 'label_norm']

# Holds the catalog data in memory after startup
catalog_index = pd.DataFrame()


# Clean up text for consistent searching — lowercase, no extra spaces
def _normalize_text(value):
    return " ".join(str(value or "").strip().lower().split())


# Return an empty DataFrame with the exact columns expected by search logic.
def _empty_index(include_count=False):
    columns = INDEX_COLUMNS_WITH_COUNT if include_count else INDEX_COLUMNS
    return pd.DataFrame(columns=columns)


# Apply one shared cleanup pipeline so catalog and CSV indexes are shaped the same way.
def _prepare_index(df):
    df = df.copy()
    df['brand'] = df['brand'].fillna('').astype(str).str.strip()
    df['model'] = df['model'].fillna('').astype(str).str.strip()
    df = df[(df['brand'] != '') | (df['model'] != '')].copy()

    if df.empty:
        has_count = 'listing_count' in df.columns
        return _empty_index(include_count=has_count)

    df['label'] = (df['brand'] + ' ' + df['model']).str.strip()
    df['brand_norm'] = df['brand'].map(_normalize_text)
    df['model_norm'] = df['model'].map(_normalize_text)
    df['label_norm'] = df['label'].map(_normalize_text)
    return df


# Load the vehicle_catalog.json file into memory once when the app starts
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

        catalog_df = pd.DataFrame(rows).drop_duplicates(subset=['brand', 'model']).reset_index(drop=True)
        catalog_index = _prepare_index(catalog_df)

    except (FileNotFoundError, json.JSONDecodeError, OSError):
        catalog_index = _empty_index()


# Read the CSV file directly and return a brand/model index with listing counts
def _read_csv_index():
    try:
        df = pd.read_csv(CSV_PATH, usecols=['name'])
        split_name = df['name'].astype(str).str.strip().str.split()
        df['brand'] = split_name.str[0].fillna('')
        df['model'] = split_name.str[1:].str.join(' ').fillna('')

        grouped = (
            df.groupby(['brand', 'model'], dropna=False)
            .size()
            .reset_index(name='listing_count')
        )
        return _prepare_index(grouped)

    except (FileNotFoundError, OSError):
        return _empty_index(include_count=True)


# Search through an index and return ranked suggestions matching the query
def _search_index(index_df, query, brand_filter, include_counts=False):
    if index_df.empty:
        return []

    query_norm = _normalize_text(query)
    filtered = index_df.copy()

    brand_filter_norm = _normalize_text(brand_filter)
    if brand_filter_norm:
        filtered = filtered[filtered['brand_norm'] == brand_filter_norm]

    if filtered.empty:
        return []

    if not query_norm:
        filtered['match_score'] = 1
    else:
        contains_mask = (
            filtered['label_norm'].str.contains(query_norm, regex=False)
            | filtered['brand_norm'].str.contains(query_norm, regex=False)
            | filtered['model_norm'].str.contains(query_norm, regex=False)
        )
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
        filtered = filtered[contains_mask].copy()
        if filtered.empty:
            return []

        filtered['match_score'] = 70
        filtered.loc[prefix_mask, 'match_score'] = 90
        filtered.loc[exact_mask, 'match_score'] = 120

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


# Validate that all required fields are present and numeric fields are valid numbers
def _validate_prediction_input(form_data):
    required_fields = [
        'year', 'km_driven', 'fuel', 'seller_type', 'transmission',
        'owner', 'engine', 'max_power', 'seats', 'brand', 'model',
    ]

    missing = [field for field in required_fields if not str(form_data.get(field, '')).strip()]
    if missing:
        return f"Missing required fields: {', '.join(missing)}"

    numeric_validators = {
        'year': int,
        'km_driven': float,
        'engine': float,
        'max_power': float,
        'seats': float,
    }

    for field, caster in numeric_validators.items():
        try:
            caster(form_data[field])
        except (TypeError, ValueError):
            return f"Invalid value for '{field}'."

    return None


# Read request data in one place and return (is_json, payload) for a simple predict flow.
def _read_prediction_payload():
    if request.is_json:
        return True, request.get_json(silent=True)
    return False, request.form.to_dict(flat=True)


# Build the final success response for both API calls and template rendering.
def _prediction_success_response(formatted_price, form_data):
    if request.is_json:
        return jsonify({'price': formatted_price, 'error': None})
    return render_template('estimate.html', price=formatted_price, error=None, form_data=form_data)


# Build one consistent error response for both JSON and non-JSON requests.
def _prediction_error_response(message, form_data, status_code=400):
    if request.is_json:
        return jsonify({'price': None, 'error': message}), status_code
    return render_template('estimate.html', price=None, error=message, form_data=form_data)


# Load catalog once at startup
_load_catalog_index()


# ---------------------------------------------------------
# PAGE ROUTES
# ---------------------------------------------------------

@app.route('/')
def home_page():
    return render_template('index.html')


@app.route('/estimate')
def estimate_page():
    return render_template('estimate.html')


@app.route('/about')
def about_page():
    return render_template('about.html')


# ---------------------------------------------------------
# AUTOCOMPLETE
# Reads CSV directly each time, falls back to catalog if CSV has no results
# ---------------------------------------------------------

@app.route('/autocomplete', methods=['GET'])
def autocomplete():
    query = request.args.get('q', default='', type=str)
    brand_filter = request.args.get('brand', default='', type=str)

    # Try the real CSV data first
    csv_index = _read_csv_index()
    csv_results = _search_index(csv_index, query=query, brand_filter=brand_filter, include_counts=True)

    if csv_results:
        return jsonify({
            'source': 'operational',
            'query': query,
            'brand_filter': brand_filter,
            'suggestions': [{**item, 'source': 'operational'} for item in csv_results],
        })

    # Fall back to the catalog if CSV gave nothing
    catalog_results = _search_index(catalog_index, query=query, brand_filter=brand_filter, include_counts=False)

    return jsonify({
        'source': 'catalog',
        'query': query,
        'brand_filter': brand_filter,
        'suggestions': [{**item, 'source': 'catalog'} for item in catalog_results],
    })


# ---------------------------------------------------------
# PREDICT
# Validates input and returns a dummy price for now.
# Replace DUMMY_PRICE_NPR with the real model output later.
# ---------------------------------------------------------

@app.route('/predict', methods=['POST'])
def predict():
    try:
        is_json_request, form_data = _read_prediction_payload()

        if not form_data:
            return jsonify({'error': 'No input data received.'}), 400

        validation_error = _validate_prediction_input(form_data)
        if validation_error:
            return _prediction_error_response(validation_error, form_data)

        # --- Replace this line with the real model prediction later ---
        formatted_price = DUMMY_PRICE_NPR
        # --------------------------------------------------------------

        return _prediction_success_response(formatted_price, form_data)

    except Exception as e:
        fallback_form_data = form_data if isinstance(locals().get('form_data'), dict) else request.form.to_dict(flat=True)
        return _prediction_error_response(str(e), fallback_form_data)


if __name__ == '__main__':
    app.run(debug=True)