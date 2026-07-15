import pandas as pd
import numpy as np
import hmac
import os
import secrets
import csv
from io import StringIO
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask, flash, redirect, render_template, request, session, url_for, abort, Response
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

db = SQLAlchemy()

app = Flask(__name__, template_folder="templates")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-development-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:Messi.100@localhost:5432/carresell_db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

db.init_app(app)
migrate = Migrate(app, db)

from models import User, Estimate

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Please log in to view your profile."
login_manager.login_message_category = "error"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]

def csrf_is_valid():
    expected = session.get("_csrf_token", "")
    supplied = request.form.get("csrf_token", "")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))

def safe_next_url(next_url):
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return url_for("profile")

app.jinja_env.globals["csrf_token"] = csrf_token

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------
# GLOBAL VARIABLES FOR MODEL AND METRICS
# ---------------------------------------------------------
CURRENT_YEAR = 2025
pipeline_instance = None
model_instance = None
model_metrics = {}
reference_data = None # NEW: Store clean data for similar cars
feature_importances = [] # NEW: Store weights for dashboard
training_samples_count = 0
feature_count = 0

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

def initialize_and_train():
    global pipeline_instance, model_instance, model_metrics, reference_data
    global feature_importances, training_samples_count, feature_count
    
    print("Loading data and training model... This may take a moment.")
    np.random.seed(42)
    df = pd.read_csv(BASE_DIR / "UsedCars.csv")
    df['selling_price'] = df['selling_price'] * 2.2
    df = df.drop(columns=['torque'], errors='ignore')
    df = df.drop_duplicates()
    
    df['brand'] = df['name'].str.split().str[0]
    df['model'] = df['name'].str.split().str[1:].str.join(' ')
    
    for col, suffix in [('mileage', ' kmpl'), ('engine', ' CC'), ('max_power', ' bhp')]:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(suffix, '', regex=False), errors='coerce')
        
    q1 = df['selling_price'].quantile(0.01)
    q99 = df['selling_price'].quantile(0.99)
    df = df[(df['selling_price'] >= q1) & (df['selling_price'] <= q99)]
    
    top_models = df['model'].value_counts().head(25).index
    df['model'] = df['model'].apply(lambda x: x if x in top_models else "Other")
    df['brand_model'] = df['brand'] + "_" + df['model']
    
    reference_data = df.copy() # Store for recommendations
    
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

    mse = np.mean((y_true - y_pred) ** 2)
    rmse = np.sqrt(mse)
    mae = np.mean(np.abs(y_true - y_pred))
    r2 = 1 - (np.sum((y_true - y_pred) ** 2) / np.sum((y_true - np.mean(y_true)) ** 2))
    mape = np.mean(np.abs((y_true - y_pred) / y_true)) * 100

    model_metrics = {
        'R2': round(r2, 4),
        'MAE': round(mae, 2),
        'MSE': round(mse, 2),
        'RMSE': round(rmse, 2),
        'MAPE': f"{round(mape, 2)}%"
    }
    
    training_samples_count = len(train)
    feature_count = len(pipeline_instance.feature_columns)
    
    # Store top 10 absolute feature importances for the dashboard
    importances = list(zip(pipeline_instance.feature_columns, model_instance.coef_))
    importances.sort(key=lambda x: abs(x[1]), reverse=True)
    feature_importances = importances[:10]

    print("Training complete! Server ready.")

initialize_and_train()

def render_page(template_name, active_page, **context):
    context["active_page"] = active_page
    return render_template(template_name, **context)

# ---------------------------------------------------------
# ADMIN & HELPER FUNCTIONS
# ---------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def find_similar_cars(user_input, pred_price, top_n=5):
    if reference_data is None or reference_data.empty:
        return []
    
    df = reference_data.copy()
    
    # Hard filters
    df = df[(df['brand'] == user_input['brand']) & 
            (df['fuel'] == user_input['fuel'])]
    
    if len(df) == 0:
        # Fallback to just fuel and transmission if brand not found
        df = reference_data[(reference_data['fuel'] == user_input['fuel']) &
                            (reference_data['transmission'] == user_input['transmission'])].copy()

    # Calculate basic similarity distance (lower is better)
    # Using absolute differences normalized roughly
    df['sim_score'] = (
        abs(df['year'] - user_input['year']) * 1000 + 
        abs(df['engine'] - user_input['engine']) * 10 +
        abs(df['selling_price'] - pred_price) * 0.1
    )
    
    recommendations = df.sort_values('sim_score').head(top_n)
    
    results = []
    for _, row in recommendations.iterrows():
        diff = row['selling_price'] - pred_price
        results.append({
            'name': row.get('name', f"{row['brand']} {row['model']}"),
            'year': row['year'],
            'mileage': row.get('mileage', 'N/A'),
            'fuel': row['fuel'],
            'transmission': row['transmission'],
            'actual_price': f"NPR {int(row['selling_price']):,}",
            'diff': f"+NPR {int(diff):,}" if diff > 0 else f"-NPR {abs(int(diff)):,}"
        })
    return results

# ---------------------------------------------------------
# FLASK ROUTES
# ---------------------------------------------------------
@app.route('/', methods=['GET'])
def index():
    return render_page('index.html', 'home', metrics=model_metrics, price=None)

@app.route('/about')
def about():
    return render_page('about.html', 'about')

@app.route('/metrics')
def metrics():
    # Format data for Chart.js
    labels = [f[0] for f in feature_importances]
    data = [round(f[1], 4) for f in feature_importances]
    
    return render_page('metrics.html', 'metrics', 
                       metrics=model_metrics, 
                       samples=training_samples_count,
                       features=feature_count,
                       chart_labels=labels,
                       chart_data=data)

@app.route('/admin')
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_preds = Estimate.query.count()
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_preds = Estimate.query.filter(Estimate.created_at >= today_start).count()
    
    avg_price = db.session.query(func.avg(Estimate.predicted_price)).scalar()
    avg_price = f"NPR {int(avg_price):,}" if avg_price else "NPR 0"
    
    recent_estimates = Estimate.query.order_by(Estimate.created_at.desc()).limit(10).all()
    
    return render_page('admin.html', 'admin',
                       total_users=total_users,
                       total_preds=total_preds,
                       today_preds=today_preds,
                       avg_price=avg_price,
                       recent_estimates=recent_estimates)

@app.route('/admin/export')
@admin_required
def export_csv():
    estimates = Estimate.query.all()
    
    def generate():
        data = StringIO()
        writer = csv.writer(data)
        writer.writerow(['ID', 'User ID', 'Brand', 'Model', 'Year', 'Fuel', 'Transmission', 'Predicted Price', 'Min Price', 'Max Price', 'Date'])
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)
        
        for est in estimates:
            writer.writerow([est.id, est.user_id, est.brand, est.model, est.year, est.fuel, est.transmission, 
                             est.predicted_price, est.min_price, est.max_price, est.created_at.strftime('%Y-%m-%d %H:%M:%S')])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    response = Response(generate(), mimetype='text/csv')
    response.headers.set("Content-Disposition", "attachment", filename="prediction_history.csv")
    return response

@app.route('/estimate')
def estimate():
    return render_page('estimate.html', 'estimate', metrics=model_metrics, price=None, error=None, form_data={})

# --- KEEP YOUR EXISTING /login, /signup, /profile, /logout ROUTES EXACTLY AS THEY WERE ---
# (I am omitting them here for brevity, but they require no modifications for these features to work)

@app.route('/predict', methods=['POST'])
def predict():
    form_data = request.form.to_dict(flat=True)
    if not csrf_is_valid():
        return render_page('estimate.html', 'estimate', metrics=model_metrics, price=None,
            error='Your form expired. Please submit the estimate again.', form_data=form_data), 400

    try:
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
        
        # Calculate Range using MAE
        mae_value = float(model_metrics['MAE'])
        min_price = max(0, price - mae_value)
        max_price = price + mae_value
        
        formatted_price = f"NPR {int(price):,}"
        formatted_min = f"NPR {int(min_price):,}"
        formatted_max = f"NPR {int(max_price):,}"

        # Get Similar Cars
        similar_cars = find_similar_cars(user_input, price)

        save_error = None
        if current_user.is_authenticated:
            try:
                estimate_record = Estimate(
                    user_id=current_user.id,
                    brand=user_input['brand'],
                    model=user_input['model'],
                    year=user_input['year'],
                    fuel=user_input['fuel'],
                    transmission=user_input['transmission'],
                    predicted_price=price,
                    min_price=min_price,
                    max_price=max_price
                )
                db.session.add(estimate_record)
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                save_error = 'Your estimate was generated, but it could not be saved to history.'
        
        return render_page(
            'estimate.html', 'estimate', metrics=model_metrics, 
            price=formatted_price, min_price=formatted_min, max_price=formatted_max,
            similar_cars=similar_cars, error=None, save_error=save_error, form_data=form_data,
            estimate_saved=current_user.is_authenticated and save_error is None
        )
    
    except Exception as e:
        return render_page(
            'estimate.html', 'estimate', metrics=model_metrics, price=None,
            error='Could not generate an estimate from those details. Please check the fields and try again.',
            form_data=form_data
        )

if __name__ == '__main__':
    app.run(debug=True)
