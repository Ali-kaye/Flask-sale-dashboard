import os
import io
import base64
import logging
from datetime import datetime
from fpdf import FPDF
from logging.handlers import RotatingFileHandler
from flask import Flask, request, render_template, session, jsonify, redirect, url_for, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib

matplotlib.use('Agg')  # Non-interactive backend

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config.update(
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///sales_dashboard.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.environ.get('SECRET_KEY', 'your-secret-key-here'),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max upload
    UPLOAD_EXTENSIONS=['.xlsx', '.csv'],
    LOG_FILE='app.log'
)

# Extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Logging
def configure_logging(app):
    handler = RotatingFileHandler(app.config['LOG_FILE'], maxBytes=10000, backupCount=3)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)

configure_logging(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploads = db.relationship('UserUpload', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class UserUpload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(120), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    data = db.Column(db.JSON)
    currency = db.Column(db.String(10), default='USD')  # e.g., 'USD' or 'KSH'


# Helper Functions
def get_currency_symbol(currency_code):
    mapping = {'USD': '$', 'KSH': 'KSh', 'Ksh': 'KSh'}
    return mapping.get(currency_code.upper(), currency_code)


def standardize_column_names(df):
    df = df.copy()
    df.columns = df.columns.str.strip()
    mapping = {
        'price (ksh)': 'price', 'price(ksh)': 'price', 'total (ksh)': 'total', 'total(ksh)': 'total',
        'price (usd)': 'price', 'price(usd)': 'price', 'total (usd)': 'total', 'total(usd)': 'total',
        'product': 'product', 'item': 'product', 'description': 'product', 'name': 'product',
        'quantity': 'quantity', 'qty': 'quantity', 'units': 'quantity',
        'date': 'date', 'sale date': 'date', 'transaction date': 'date', 'order date': 'date'
    }
    df.rename(columns=lambda x: mapping.get(x.lower(), x.lower()), inplace=True)
    return df


def validate_dataframe(df):
    df.columns = df.columns.str.strip()
    required = ['date', 'product', 'quantity']
    possible_names = {
        'date': ['date', 'sale date', 'transaction date', 'order date'],
        'product': ['product', 'item', 'description', 'name'],
        'quantity': ['quantity', 'qty', 'units']
    }

    found = {}
    for std, candidates in possible_names.items():
        for col in df.columns:
            if col.lower() in candidates:
                found[std] = col
                break

    if len(found) < 3:
        missing = [k for k in required if k not in found]
        return False, f"Missing required columns: {', '.join(missing)}"

    has_price_or_total = any('price' in col.lower() or 'total' in col.lower() for col in df.columns)
    if not has_price_or_total:
        return False, "Missing price or total column"

    try:
        pd.to_datetime(df[found['date']])
        pd.to_numeric(df[found['quantity']], errors='raise')
    except:
        return False, "Invalid date or quantity format"

    return True, ""


def detect_currency(df):
    cols = [c.lower() for c in df.columns]
    if any('ksh' in c for c in cols):
        return 'KSH'
    return 'USD'


def generate_charts(df, currency='USD'):
    symbol = get_currency_symbol(currency)
    charts = {}

    try:
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0)
        df['price'] = pd.to_numeric(df['price'], errors='coerce').fillna(0)
        df['total'] = pd.to_numeric(df['total'], errors='coerce')

        if df['total'].isnull().all() or (df['total'] == 0).all():
            df['total'] = df['quantity'] * df['price']

        df['month'] = df['date'].dt.to_period('M')
        df['day_of_week'] = df['date'].dt.day_name()

        plt.style.use('default')
        plt.rcParams.update({
            'figure.facecolor': 'white',
            'axes.facecolor': 'white',
            'savefig.facecolor': 'white',
            'font.size': 10
        })

        def save_to_base64():
            img = io.BytesIO()
            plt.savefig(img, format='png', dpi=150, bbox_inches='tight', pad_inches=0.6)
            img.seek(0)
            plt.close()
            return base64.b64encode(img.getvalue()).decode()

        # 1. Revenue by Product
        plt.figure(figsize=(10, max(6, len(df['product'].unique()) * 0.6)))
        sales_by_product = df.groupby('product')['total'].sum().sort_values(ascending=True)
        ax = sales_by_product.plot(kind='barh', color='#4e73df')
        plt.title('Total Revenue by Product', fontsize=14, pad=20)
        plt.xlabel(f'Revenue ({symbol})')
        plt.ylabel('Product')
        plt.grid(axis='x', alpha=0.3)
        for i, v in enumerate(sales_by_product):
            ax.text(v + v * 0.01, i, f'{symbol}{v:,.0f}', va='center', fontsize=10)
        charts['sales_by_product'] = save_to_base64()

        # 2. Monthly Sales Trend
        plt.figure(figsize=(12, 6))
        monthly_sales = df.groupby(df['date'].dt.to_period('M'))['total'].sum()
        ax = monthly_sales.plot(kind='line', marker='o', linewidth=3, color='#1cc88a')
        plt.title('Monthly Sales Trend', fontsize=14, pad=20)
        plt.ylabel(f'Total Sales ({symbol})')
        plt.xlabel('Month')
        plt.grid(alpha=0.3)
        for i, v in enumerate(monthly_sales):
            ax.text(i, v, f'{symbol}{v:,.0f}', ha='center', va='bottom', fontsize=9)
        charts['sales_trend'] = save_to_base64()

        # 3. Revenue Distribution (Pie)
        plt.figure(figsize=(8, 8))
        product_share = df.groupby('product')['total'].sum()
        product_share.plot(kind='pie', autopct='%1.1f%%', startangle=90, textprops={'fontsize': 11})
        plt.title('Revenue Distribution by Product', fontsize=14, pad=20)
        plt.ylabel('')
        charts['revenue_distribution'] = save_to_base64()

        # 4. Top Products by Quantity
        plt.figure(figsize=(10, 6))
        top_qty = df.groupby('product')['quantity'].sum().nlargest(8)
        ax = top_qty.plot(kind='bar', color='#36b9cc')
        plt.title('Top Selling Products (by Quantity)', fontsize=14, pad=20)
        plt.ylabel('Units Sold')
        plt.xticks(rotation=45, ha='right')
        plt.grid(axis='y', alpha=0.3)
        for i, v in enumerate(top_qty):
            ax.text(i, v + v * 0.01, f'{int(v):,}', ha='center', fontsize=10)
        charts['top_products_qty'] = save_to_base64()

        # 5. Sales by Day of Week
        plt.figure(figsize=(10, 6))
        order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekday_sales = df.groupby('day_of_week')['total'].sum().reindex(order, fill_value=0)
        ax = weekday_sales.plot(kind='bar', color='#858796')
        plt.title('Sales by Day of Week', fontsize=14, pad=20)
        plt.ylabel(f'Total Sales ({symbol})')
        plt.grid(axis='y', alpha=0.3)
        for i, v in enumerate(weekday_sales):
            ax.text(i, v + v * 0.01, f'{symbol}{v:,.0f}', ha='center', fontsize=9)
        charts['weekday_sales'] = save_to_base64()

        return charts

    except Exception as e:
        app.logger.error(f"Chart generation failed: {str(e)}", exc_info=True)
        return {}


# === NEW: Delete Upload Route ===
@app.route('/delete_upload/<int:upload_id>', methods=['POST'])
def delete_upload(upload_id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    upload = UserUpload.query.get_or_404(upload_id)
    if upload.user_id != session['user_id']:
        return jsonify({"error": "Forbidden"}), 403

    db.session.delete(upload)
    db.session.commit()
    flash('Upload deleted successfully', 'success')
    return jsonify({"success": True})


# === UPDATED: Dashboard with Multiple Uploads Support ===
@app.route("/dashboard")
@app.route("/dashboard/<int:upload_id>")
def dashboard(upload_id=None):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Get all uploads for this user
    user_uploads = UserUpload.query.filter_by(user_id=session['user_id']) \
        .order_by(UserUpload.upload_date.desc()).all()

    if not user_uploads:
        return render_template("dashboard.html",
                               uploads=[],
                               current_time=datetime.now())

    # Determine which upload to display
    if upload_id:
        selected_upload = UserUpload.query.get_or_404(upload_id)
        if selected_upload.user_id != session['user_id']:
            flash('You do not have permission to view this upload.', 'danger')
            selected_upload = user_uploads[0]
    else:
        selected_upload = user_uploads[0]  # Latest by default

    # Generate charts and data
    df = pd.DataFrame(selected_upload.data)
    charts = generate_charts(df, selected_upload.currency)
    symbol = get_currency_symbol(selected_upload.currency)

    # Prepare upload history list for template
    uploads_list = []
    for up in user_uploads:
        try:
            temp_df = pd.DataFrame(up.data)
            total_rev = temp_df['total'].sum()
            records = len(temp_df)
        except Exception:
            total_rev = 0
            records = 0

        uploads_list.append({
            'id': up.id,
            'filename': up.filename,
            'upload_date': up.upload_date.strftime('%b %d, %Y at %H:%M'),
            'total_revenue': total_rev,
            'records': records,
            'currency': up.currency,
            'symbol': get_currency_symbol(up.currency),
            'is_active': up.id == selected_upload.id
        })

    return render_template(
        "dashboard.html",
        uploads=uploads_list,
        data=selected_upload.data,
        charts=charts,
        currency_symbol=symbol,
        selected_upload=selected_upload,
        current_time=datetime.now()
    )


# === Keep your existing routes unchanged ===
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password', 'danger')
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.lower().endswith(tuple(app.config['UPLOAD_EXTENSIONS'])):
        return jsonify({"error": "Invalid file type"}), 400

    try:
        if file.filename.lower().endswith('.xlsx'):
            df = pd.read_excel(file)
        else:
            df = pd.read_csv(file)

        df.columns = df.columns.str.strip()

        is_valid, msg = validate_dataframe(df)
        if not is_valid:
            return jsonify({"error": msg}), 400

        currency = detect_currency(df)
        df = standardize_column_names(df)

        if not all(col in df.columns for col in ['date', 'product', 'quantity']):
            return jsonify({"error": "Column mapping failed"}), 400

        df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0)
        price_col = next((c for c in df.columns if 'price' in c), None)
        total_col = next((c for c in df.columns if 'total' in c), None)

        if price_col:
            df['price'] = pd.to_numeric(df[price_col].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce').fillna(0)
        if total_col:
            df['total'] = pd.to_numeric(df[total_col].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce').fillna(0)

        if 'total' not in df.columns or df['total'].sum() == 0:
            df['total'] = df['quantity'] * df.get('price', 0)

        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

        upload = UserUpload(
            user_id=session['user_id'],
            filename=file.filename,
            data=df.to_dict(orient='records'),
            currency=currency
        )
        db.session.add(upload)
        db.session.commit()

        return jsonify({
            "message": "File uploaded successfully",
            "stats": {
                "total_sales": float(df['total'].sum()),
                "total_products": int(df['product'].nunique()),
                "time_period": f"{df['date'].min()} to {df['date'].max()}",
                "currency": currency
            }
        })

    except Exception as e:
        app.logger.error(f"Upload error: {str(e)}")
        return jsonify({"error": "Processing failed"}), 500


@app.route('/export/pdf')
def export_pdf():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Use the currently selected upload (from session or latest)
    latest = UserUpload.query.filter_by(user_id=session['user_id']) \
        .order_by(UserUpload.upload_date.desc()).first()
    if not latest:
        flash('No data to export', 'warning')
        return redirect(url_for('dashboard'))

    df = pd.DataFrame(latest.data)
    charts = generate_charts(df, latest.currency)
    symbol = get_currency_symbol(latest.currency)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Sales Analytics Report", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Summary Statistics", ln=True)
    pdf.set_font("Arial", size=11)
    pdf.cell(0, 8, f"Total Revenue: {symbol}{df['total'].sum():,.2f}", ln=True)
    pdf.cell(0, 8, f"Total Items Sold: {int(df['quantity'].sum())}", ln=True)
    pdf.cell(0, 8, f"Unique Products: {df['product'].nunique()}", ln=True)
    pdf.cell(0, 8, f"Average Sale: {symbol}{(df['total'].sum() / len(df)) if len(df) > 0 else 0:,.2f}", ln=True)
    pdf.ln(10)

    for name, b64_data in charts.items():
        pdf.add_page()
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, name.replace('_', ' ').title(), ln=True, align='C')
        img_data = base64.b64decode(b64_data)
        img_io = io.BytesIO(img_data)
        pdf.image(img_io, x=10, y=30, w=190)

    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"sales_report_{datetime.now().strftime('%Y%m%d')}.pdf",
        mimetype='application/pdf'
    )


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(e):
    db.session.rollback()
    return render_template('500.html'), 500


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)