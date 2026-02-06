from flask import Flask, render_template, request, redirect, url_for, session, send_file, Response, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime
import os
import csv
import matplotlib
matplotlib.use('Agg')  # Must come before pyplot import
import matplotlib.pyplot as plt
from io import StringIO
import secrets
import re
import json
import pandas as pd
import numpy as np
from werkzeug.utils import secure_filename
import uuid

# FIXED: Set template folder to current directory for Render deployment
# This line should be in your app.py
app = Flask(__name__, template_folder='.', static_folder='static', static_url_path='/static')

# Railway configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///sales_analyzer.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'xlsx', 'xls'}

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# Create necessary directories
for folder in ['uploads', 'static/charts']:
    os.makedirs(folder, exist_ok=True)

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200))
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)

class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    filename = db.Column(db.String(200))
    analysis_data = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Sample data
SAMPLE_DATA = [
    ['Order_ID', 'Date', 'Product', 'Category', 'Region', 'Quantity', 'Unit_Price', 'Total_Sales'],
    ['101', '2024-01-01', 'Laptop', 'Electronics', 'North', '1', '50000', '50000'],
    ['102', '2024-01-02', 'Mobile', 'Electronics', 'South', '2', '15000', '30000'],
    ['103', '2024-01-03', 'Headphones', 'Accessories', 'East', '3', '2000', '6000'],
    ['104', '2024-01-04', 'Laptop', 'Electronics', 'West', '1', '50000', '50000'],
    ['105', '2024-01-05', 'Keyboard', 'Accessories', 'North', '2', '1500', '3000'],
    ['106', '2024-01-06', 'Mouse', 'Accessories', 'South', '5', '500', '2500'],
    ['107', '2024-01-07', 'Monitor', 'Electronics', 'East', '1', '20000', '20000'],
    ['108', '2024-01-08', 'Printer', 'Electronics', 'West', '1', '8000', '8000'],
    ['109', '2024-01-09', 'Tablet', 'Electronics', 'North', '3', '12000', '36000'],
    ['110', '2024-01-10', 'Speaker', 'Accessories', 'South', '4', '3000', '12000'],
    ['111', '2024-01-11', 'Laptop', 'Electronics', 'East', '2', '52000', '104000'],
    ['112', '2024-01-12', 'Mobile', 'Electronics', 'West', '1', '16000', '16000'],
    ['113', '2024-01-13', 'Headphones', 'Accessories', 'North', '5', '2500', '12500'],
    ['114', '2024-01-14', 'Keyboard', 'Accessories', 'South', '3', '1800', '5400'],
    ['115', '2024-01-15', 'Mouse', 'Accessories', 'East', '2', '600', '1200']
]

def read_file_data(filepath):
    """Read file data (CSV or Excel) and return as list"""
    data = []
    try:
        if filepath.endswith('.csv'):
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    data.append(row)
        elif filepath.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(filepath)
            data = df.values.tolist()
            data.insert(0, df.columns.tolist())
    except Exception as e:
        print(f"Error reading file: {e}")
        if filepath.endswith('.csv'):
            encodings = ['latin-1', 'cp1252', 'iso-8859-1']
            for encoding in encodings:
                try:
                    with open(filepath, 'r', encoding=encoding) as f:
                        reader = csv.reader(f)
                        for row in reader:
                            data.append(row)
                    break
                except:
                    continue
    
    return data

def analyze_data(data):
    """Analyze sales data comprehensively"""
    if not data or len(data) <= 1:
        return {
            'total_sales': 0,
            'total_orders': 0,
            'avg_order_value': 0,
            'best_product': 'N/A',
            'top_category': 'N/A',
            'top_region': 'N/A',
            'total_quantity': 0,
            'products_count': 0,
            'sales_by_product': {},
            'sales_by_category': {},
            'sales_by_region': {},
            'monthly_sales': {}
        }
    
    headers = data[0]
    rows = data[1:]
    
    # Find column indices
    sales_idx = -1
    product_idx = -1
    category_idx = -1
    region_idx = -1
    quantity_idx = -1
    date_idx = -1
    price_idx = -1
    
    for i, header in enumerate(headers):
        header_lower = str(header).lower()
        if 'sales' in header_lower or 'amount' in header_lower or 'total' in header_lower:
            sales_idx = i
        if 'product' in header_lower or 'item' in header_lower:
            product_idx = i
        if 'category' in header_lower or 'type' in header_lower:
            category_idx = i
        if 'region' in header_lower or 'area' in header_lower or 'location' in header_lower:
            region_idx = i
        if 'quantity' in header_lower or 'qty' in header_lower:
            quantity_idx = i
        if 'date' in header_lower or 'time' in header_lower:
            date_idx = i
        if 'price' in header_lower or 'cost' in header_lower or 'unit' in header_lower:
            price_idx = i
    
    # Initialize results
    results = {
        'total_sales': 0,
        'total_orders': len(rows),
        'avg_order_value': 0,
        'best_product': 'N/A',
        'top_category': 'N/A',
        'top_region': 'N/A',
        'total_quantity': 0,
        'products_count': 0,
        'sales_by_product': {},
        'sales_by_category': {},
        'sales_by_region': {},
        'monthly_sales': {}
    }
    
    # Data structures for analysis
    product_sales = {}
    category_sales = {}
    region_sales = {}
    monthly_sales = {}
    products = set()
    
    # Calculate totals and build dictionaries
    if sales_idx >= 0:
        total = 0
        total_qty = 0
        
        for row in rows:
            try:
                if len(row) > sales_idx:
                    sales_val = float(str(row[sales_idx]).replace(',', ''))
                    total += sales_val
                    
                    # Product analysis
                    if product_idx >= 0 and len(row) > product_idx:
                        product = str(row[product_idx]).strip()
                        products.add(product)
                        product_sales[product] = product_sales.get(product, 0) + sales_val
                    
                    # Category analysis
                    if category_idx >= 0 and len(row) > category_idx:
                        category = str(row[category_idx]).strip()
                        category_sales[category] = category_sales.get(category, 0) + sales_val
                    
                    # Region analysis
                    if region_idx >= 0 and len(row) > region_idx:
                        region = str(row[region_idx]).strip()
                        region_sales[region] = region_sales.get(region, 0) + sales_val
                    
                    # Quantity analysis
                    if quantity_idx >= 0 and len(row) > quantity_idx:
                        try:
                            qty = float(str(row[quantity_idx]))
                            total_qty += qty
                        except:
                            pass
                    
                    # Monthly analysis
                    if date_idx >= 0 and len(row) > date_idx:
                        try:
                            date_str = str(row[date_idx])
                            if len(date_str) >= 7:
                                month_key = date_str[:7]  # YYYY-MM
                                monthly_sales[month_key] = monthly_sales.get(month_key, 0) + sales_val
                        except:
                            pass
                            
            except Exception as e:
                print(f"Error processing row: {e}")
                continue
        
        results['total_sales'] = total
        results['total_quantity'] = total_qty
        results['products_count'] = len(products)
        
        if rows:
            results['avg_order_value'] = total / len(rows)
    
    # Find best product
    if product_sales:
        results['best_product'] = max(product_sales, key=product_sales.get)
        results['sales_by_product'] = dict(sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:10])
    
    # Find top category
    if category_sales:
        results['top_category'] = max(category_sales, key=category_sales.get)
        results['sales_by_category'] = dict(sorted(category_sales.items(), key=lambda x: x[1], reverse=True))
    
    # Find top region
    if region_sales:
        results['top_region'] = max(region_sales, key=region_sales.get)
        results['sales_by_region'] = dict(sorted(region_sales.items(), key=lambda x: x[1], reverse=True))
    
    # Sort monthly sales
    if monthly_sales:
        results['monthly_sales'] = dict(sorted(monthly_sales.items()))
    
    return results

def create_charts(results, prefix):
    """Create charts from analysis results"""
    charts = {}
    
    try:
        # Clean old charts
        for file in os.listdir('static/charts'):
            if file.endswith('.png'):
                try:
                    os.remove(f'static/charts/{file}')
                except:
                    pass
    except:
        pass
    
    # Create products chart
    try:
        plt.figure(figsize=(10, 6))
        
        if results.get('sales_by_product'):
            products = list(results['sales_by_product'].keys())[:8]
            sales = list(results['sales_by_product'].values())[:8]
        else:
            products = ['Laptop', 'Mobile', 'Headphones', 'Keyboard', 'Mouse', 'Monitor', 'Printer', 'Tablet']
            sales = [100000, 45000, 6000, 3000, 2500, 20000, 8000, 36000]
        
        colors = plt.cm.Set3(np.linspace(0, 1, len(products)))
        bars = plt.bar(products, sales, color=colors)
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height,
                    f'₹{int(height):,}', ha='center', va='bottom', fontsize=9)
        
        plt.title('Top Products by Sales', fontsize=16, fontweight='bold')
        plt.xlabel('Products', fontsize=12)
        plt.ylabel('Sales (₹)', fontsize=12)
        plt.xticks(rotation=45, ha='right')
        plt.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        
        chart_path = f'static/charts/{prefix}_products.png'
        plt.savefig(chart_path, dpi=100, bbox_inches='tight')
        plt.close()
        charts['products'] = chart_path
    except Exception as e:
        print(f"Products chart error: {e}")
    
    # Create categories chart
    try:
        plt.figure(figsize=(8, 8))
        
        if results.get('sales_by_category'):
            categories = list(results['sales_by_category'].keys())
            sales = list(results['sales_by_category'].values())
        else:
            categories = ['Electronics', 'Accessories']
            sales = [245000, 11500]
        
        colors = plt.cm.Paired(np.linspace(0, 1, len(categories)))
        plt.pie(sales, labels=categories, autopct='%1.1f%%', startangle=90, 
                colors=colors, textprops={'fontsize': 11})
        plt.title('Sales by Category', fontsize=16, fontweight='bold')
        plt.tight_layout()
        
        chart_path = f'static/charts/{prefix}_categories.png'
        plt.savefig(chart_path, dpi=100, bbox_inches='tight')
        plt.close()
        charts['categories'] = chart_path
    except Exception as e:
        print(f"Categories chart error: {e}")
    
    # Create regions chart
    try:
        plt.figure(figsize=(10, 6))
        
        if results.get('sales_by_region'):
            regions = list(results['sales_by_region'].keys())
            sales = list(results['sales_by_region'].values())
        else:
            regions = ['North', 'South', 'East', 'West']
            sales = [58000, 62500, 28000, 58000]
        
        colors = plt.cm.tab20c(np.linspace(0, 1, len(regions)))
        bars = plt.bar(regions, sales, color=colors)
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height,
                    f'₹{int(height):,}', ha='center', va='bottom', fontsize=9)
        
        plt.title('Sales by Region', fontsize=16, fontweight='bold')
        plt.xlabel('Regions', fontsize=12)
        plt.ylabel('Sales (₹)', fontsize=12)
        plt.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        
        chart_path = f'static/charts/{prefix}_regions.png'
        plt.savefig(chart_path, dpi=100, bbox_inches='tight')
        plt.close()
        charts['regions'] = chart_path
    except Exception as e:
        print(f"Regions chart error: {e}")
    
    # Create monthly sales chart (if data available)
    try:
        if results.get('monthly_sales') and len(results['monthly_sales']) > 1:
            plt.figure(figsize=(12, 6))
            
            months = list(results['monthly_sales'].keys())
            sales = list(results['monthly_sales'].values())
            
            plt.plot(months, sales, marker='o', linewidth=2, markersize=8, color='#6a11cb')
            plt.fill_between(months, sales, alpha=0.2, color='#6a11cb')
            
            plt.title('Monthly Sales Trend', fontsize=16, fontweight='bold')
            plt.xlabel('Month', fontsize=12)
            plt.ylabel('Sales (₹)', fontsize=12)
            plt.xticks(rotation=45)
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            
            chart_path = f'static/charts/{prefix}_monthly.png'
            plt.savefig(chart_path, dpi=100, bbox_inches='tight')
            plt.close()
            charts['monthly'] = chart_path
    except Exception as e:
        print(f"Monthly chart error: {e}")
    
    return charts

# ==================== AUTHENTICATION ROUTES ====================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect('/dashboard')
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        name = request.form.get('name')
        
        # Validation
        if not email or not password or not confirm_password:
            flash('All fields are required', 'danger')
            return redirect('/register')
        
        # Validate email format
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            flash('Invalid email format', 'danger')
            return redirect('/register')
        
        # Validate password strength
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'danger')
            return redirect('/register')
        
        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect('/register')
        
        # Check if user exists
        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash('Email already registered', 'danger')
            return redirect('/register')
        
        # Create user
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(
            email=email,
            password=hashed_password,
            name=name,
            created_at=datetime.utcnow(),
            is_active=True
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect('/login')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/dashboard')
    
    if request.method == 'POST':
        email = request.form.get('identifier')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        # Find user by email
        user = User.query.filter_by(email=email).first()
        
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            flash('Login successful!', 'success')
            return redirect('/dashboard')
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect('/')

# ==================== MAIN APPLICATION ROUTES ====================

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/dashboard')
@login_required
def dashboard():
    analysis = session.get('analysis')
    
    if not analysis:
        return redirect('/sample')
    
    return render_template('dashboard.html', 
                         data=analysis.get('data', []),
                         results=analysis.get('results', {}),
                         charts=analysis.get('charts', {}),
                         timestamp=analysis.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                         filename=analysis.get('filename', 'Sample Data'))

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    try:
        if 'file' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect('/dashboard')
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect('/dashboard')
        
        if not allowed_file(file.filename):
            flash('Please upload CSV or Excel files only', 'danger')
            return redirect('/dashboard')
        
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        data = read_file_data(filepath)
        
        if not data or len(data) <= 1:
            flash('File is empty or cannot be read. Using sample data instead.', 'warning')
            data = SAMPLE_DATA
            filename = 'sample_data.csv'
        
        results = analyze_data(data)
        
        prefix = datetime.now().strftime('%Y%m%d_%H%M%S')
        charts = create_charts(results, prefix)
        
        session['analysis'] = {
            'data': data[:21],
            'results': results,
            'charts': charts,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'filename': filename,
            'total_rows': len(data) - 1 if len(data) > 1 else 0
        }
        
        flash(f'File "{filename}" uploaded and analyzed successfully! {len(data)-1} rows processed.', 'success')
        return redirect('/dashboard')
        
    except Exception as e:
        print(f"Upload error: {e}")
        flash(f'Error: {str(e)}', 'danger')
        return redirect('/dashboard')

@app.route('/upload_ajax', methods=['POST'])
@login_required
def upload_ajax():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'})
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Please upload CSV or Excel files only'})
        
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        data = read_file_data(filepath)
        
        if not data or len(data) <= 1:
            return jsonify({'success': False, 'error': 'File is empty or cannot be read'})
        
        results = analyze_data(data)
        
        prefix = datetime.now().strftime('%Y%m%d_%H%M%S')
        charts = create_charts(results, prefix)
        
        session['analysis'] = {
            'data': data[:21],
            'results': results,
            'charts': charts,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'filename': filename,
            'total_rows': len(data) - 1
        }
        
        return jsonify({
            'success': True,
            'message': f'File "{filename}" uploaded and analyzed successfully!',
            'rows_processed': len(data) - 1,
            'total_sales': f"₹{results['total_sales']:,.2f}",
            'total_orders': results['total_orders']
        })
        
    except Exception as e:
        print(f"AJAX Upload error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/sample')
@login_required
def sample():
    """Load sample data"""
    data = SAMPLE_DATA
    results = analyze_data(data)
    
    prefix = 'sample_' + datetime.now().strftime('%Y%m%d_%H%M%S')
    charts = create_charts(results, prefix)
    
    session['analysis'] = {
        'data': data[:21],
        'results': results,
        'charts': charts,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'filename': 'sample_data.csv',
        'total_rows': len(data) - 1
    }
    
    flash('Sample data loaded successfully!', 'success')
    return redirect('/dashboard')

@app.route('/export/csv')
@login_required
def export_csv():
    analysis = session.get('analysis')
    
    if not analysis:
        flash('No analysis data to export', 'warning')
        return redirect('/dashboard')
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['SALES ANALYSIS REPORT'])
    writer.writerow(['Generated on:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(['Generated by:', current_user.email])
    writer.writerow(['Source file:', analysis.get('filename', 'Sample Data')])
    writer.writerow([])
    
    writer.writerow(['SUMMARY'])
    writer.writerow(['Total Sales:', f"₹{analysis['results']['total_sales']:,.2f}"])
    writer.writerow(['Total Orders:', analysis['results']['total_orders']])
    writer.writerow(['Average Order Value:', f"₹{analysis['results']['avg_order_value']:,.2f}"])
    writer.writerow(['Best Product:', analysis['results']['best_product']])
    writer.writerow(['Top Category:', analysis['results']['top_category']])
    writer.writerow(['Top Region:', analysis['results']['top_region']])
    writer.writerow([])
    
    writer.writerow(['RAW DATA (First 100 rows)'])
    if analysis['data']:
        writer.writerow([])
        for row in analysis['data'][:101]:
            writer.writerow(row)
    
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=sales_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        }
    )

@app.route('/clear')
@login_required
def clear():
    session.pop('analysis', None)
    flash('Analysis data cleared. Upload new data or load sample.', 'info')
    return redirect('/dashboard')

@app.route('/profile')
@login_required
def profile():
    # Calculate days active
    if current_user.created_at:
        days_active = (datetime.utcnow() - current_user.created_at).days
    else:
        days_active = 0
    
    # Get user's analyses count
    analyses_count = Analysis.query.filter_by(user_id=current_user.id).count()
    
    return render_template('profile.html', 
                         user=current_user, 
                         days_active=days_active,
                         analyses_count=analyses_count,
                         now=datetime.utcnow())

@app.route('/api/analysis_data')
@login_required
def get_analysis_data():
    """API endpoint to get current analysis data"""
    analysis = session.get('analysis', {})
    return jsonify({
        'has_data': bool(analysis),
        'filename': analysis.get('filename', 'No file loaded'),
        'timestamp': analysis.get('timestamp', ''),
        'total_rows': analysis.get('total_rows', 0),
        'results': analysis.get('results', {})
    })

@app.route('/charts/<path:filename>')
def serve_chart(filename):
    try:
        return send_file(f'static/charts/{filename}')
    except:
        return "Chart not found", 404

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', error='Page not found'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error='Server error'), 500

# ==================== INITIAL SETUP ====================

# Create database tables and default users
with app.app_context():
    db.create_all()
    
    # Create default admin user
    if not User.query.filter_by(email='admin@example.com').first():
        hashed_password = bcrypt.generate_password_hash('admin123').decode('utf-8')
        admin = User(
            email='admin@example.com',
            password=hashed_password,
            name='Admin User',
            created_at=datetime.utcnow(),
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        print("✓ Default admin user created")
    
    # Create demo user
    if not User.query.filter_by(email='user@example.com').first():
        demo_user = User(
            email='user@example.com',
            password=bcrypt.generate_password_hash('user123').decode('utf-8'),
            name='Demo User',
            created_at=datetime.utcnow(),
            is_active=True
        )
        db.session.add(demo_user)
        db.session.commit()
        print("✓ Demo user created")

# ==================== RUN THE APP ====================
if __name__ == '__main__':
    # Railway/Render provides PORT environment variable
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 60)
    print("SALES DATA ANALYZER - READY")
    print("=" * 60)
    print(f"Server will run on port: {port}")
    print("=" * 60)
    print("Demo Accounts:")
    print("1. admin@example.com / admin123")
    print("2. user@example.com / user123")
    print("=" * 60)
    
    # Run the app
    app.run(host='0.0.0.0', port=port, debug=False)