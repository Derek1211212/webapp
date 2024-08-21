from flask import Flask, render_template, request, redirect, url_for, flash, session, g
import mysql.connector
from mysql.connector import Error
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash
from functools import wraps
from flask import jsonify
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from datetime import datetime, timedelta
import os
import requests
import logging
logging.basicConfig(level=logging.DEBUG)


load_dotenv()
app = Flask(__name__)
app.secret_key = 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k7l8m9n0o1p2q3r4s5t6u7v8w9x0y1z2'

def get_db():
    if 'db' not in g:

       

        g.db = mysql.connector.connect(
            host=os.getenv('DATABASE_HOST'),
            port=int(os.getenv('DATABASE_PORT', 10005)),  # Default to 3306 if not set
            user=os.getenv('DATABASE_USER'),
            password=os.getenv('DATABASE_PASSWORD'),
            database=os.getenv('DATABASE_NAME')
        )
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def verify_user(username, password, company_id):
    db = get_db()
    cursor = db.cursor()
    query = 'SELECT * FROM tblusers WHERE Username = %s AND Password = %s AND CompanyID = %s'
    cursor.execute(query, (username, password, company_id))
    user = cursor.fetchone()
    cursor.close()
    return user

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        company_id = request.form['company_id']  # Capture company ID from form

        db = get_db()
        cursor = db.cursor()

        # Check the company's subscription status and due date
        cursor.execute("""
            SELECT SubscriptionStatus, DueDate 
            FROM company 
            WHERE CompanyID = %s
        """, (company_id,))
        company = cursor.fetchone()

        if company:
            subscription_status, due_date = company
            current_date = datetime.now().date()

            # Check if the DueDate has passed
            if due_date <= current_date:
                # Update the subscription status to 'Suspended'
                cursor.execute("""
                    UPDATE company 
                    SET SubscriptionStatus = 'Suspended' 
                    WHERE CompanyID = %s
                """, (company_id,))
                db.commit()
                flash('Subscription expired. Please renew your subscription.')
                return redirect(url_for('login'))

            # Check if the subscription status is valid for login
            if subscription_status not in ['Free', 'Paid']:
                flash('Your subscription is suspended. Please contact support.')
                return redirect(url_for('login'))

            # Verify user credentials
            user = verify_user(username, password, company_id)
            if user:
                session['user_id'] = user[0]  # Store user ID
                session['company_id'] = company_id  # Store company ID
                return redirect(url_for('home'))
            else:
                flash('Invalid username, password, or company ID')
        else:
            flash('Invalid company ID')

    if 'user_id' in session:
        return redirect(url_for('home'))
    
    return render_template('login.html')



@app.route('/renew', methods=['GET', 'POST'])
def renew():
    if request.method == 'POST':
        company_id = request.form['company_id']
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        db = get_db()
        cursor = db.cursor()

        # Verify user credentials
        cursor.execute("""
            SELECT Password 
            FROM tblusers 
            WHERE CompanyID = %s AND Username = %s
        """, (company_id, username))
        user = cursor.fetchone()

        if user and user[0] == password:
            return jsonify({'status': 'success'})
        else:
            return jsonify({'status': 'failure', 'message': 'Invalid credentials. Please check your username, password, and Company ID.'})

    return render_template('renew.html')



@app.route('/renew_payment_confirmation', methods=['POST'])
def renew_payment_confirmation():
    data = request.json
    reference = data.get('reference')
    company_id = data.get('company_id')
    email = data.get('email')
    username = data.get('username')

    db = get_db()
    cursor = db.cursor()

    # Fetch old due date
    cursor.execute("""
        SELECT DueDate 
        FROM company 
        WHERE CompanyID = %s
    """, (company_id,))
    old_due_date = cursor.fetchone()[0]

    # Calculate new due date
    if old_due_date and old_due_date > datetime.now().date():
        days_left = (old_due_date - datetime.now().date()).days
        new_due_date = datetime.now().date() + timedelta(days=days_left + 30)
    else:
        new_due_date = datetime.now().date() + timedelta(days=30)

    # Update subscription status and due date
    cursor.execute("""
        UPDATE company 
        SET SubscriptionStatus = 'Paid', DueDate = %s 
        WHERE CompanyID = %s
    """, (new_due_date, company_id))
    
    # Store payment details in subscriptionpayment table
    cursor.execute("""
        INSERT INTO subscriptionpayment (reference, email, username, companyID, time_of_payment)
        VALUES (%s, %s, %s, %s, %s)
    """, (reference, email, username, company_id, datetime.now()))
    
    db.commit()

    return jsonify({'status': 'success'})



@app.route('/success')
def success():
    return render_template('success.html')





@app.route('/home')
@login_required
def home():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    company_id = session.get('company_id')
    
    # Fetch the company name based on the logged-in company ID
    cursor.execute("SELECT CompanyName FROM company WHERE CompanyID = %s", (company_id,))
    company = cursor.fetchone()
    
    if not company:
        # Handle case where company is not found
        company_name = 'DEFAULT NAME'  # Fallback name
    else:
        company_name = company['CompanyName']
    
    # Construct the full company name for the template
    full_company_name = f"{company_name} PHARMACY".upper()
    
    return render_template('index.html', full_company_name=full_company_name)

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('company_id', None)  # Clear company ID from session
    return redirect(url_for('login'))

@app.route('/view_products', methods=['GET', 'POST'])
@login_required
def view_products():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    search_query = request.form.get('search_query', '')
    company_id = session.get('company_id')  # Get company ID from session

    try:
        if search_query:
            cursor.execute("""
                SELECT * FROM products 
                WHERE ProductName LIKE %s AND CompanyID = %s
            """, ('%' + search_query + '%', company_id))
        else:
            cursor.execute("""
                SELECT * FROM products 
                WHERE CompanyID = %s
            """, (company_id,))
        products = cursor.fetchall()
    except Error as err:
        products = []
        print(f"Error: {err}")

    return render_template('view_products.html', products=products, search_query=search_query)

@app.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    db = get_db()
    cursor = db.cursor()
    company_id = session.get('company_id')  # Get company ID from session
    try:
        cursor.execute("""
            DELETE FROM products 
            WHERE ProductID = %s AND CompanyID = %s
        """, (product_id, company_id))
        db.commit()
    except Error as err:
        print(f"Error: {err}")
    return redirect(url_for('view_products'))

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        data = {
            'product_name': request.form['product_name'],
            'manufacturer': request.form['manufacturer'],
           
            'price': request.form['price'],
            'selling_price': request.form['selling_price'],
            'stock_quantity': request.form['stock_quantity'],
           
            'supplier_id': request.form['supplier_id'],
            'usage': request.form['usage'],
            'description': request.form['description'],
           
            'drug_type': request.form['drug_type'],
            'reorder_on': request.form['reorder_on']
        }
        print("Received data:", data)  # Debugging line
        db = get_db()
        company_id = session.get('company_id')  # Get company ID from session
        try:
            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO products 
                (ProductName, Manufacturer, Price, SellingPrice, StockQuantity, SupplierID, `Usage`, Description, DrugType, ReorderOn, CompanyID) 
                VALUES (%(product_name)s, %(manufacturer)s, %(price)s, %(selling_price)s, %(stock_quantity)s, %(supplier_id)s, %(usage)s, %(description)s, %(drug_type)s, %(reorder_on)s, %(company_id)s)
            """, {**data, 'company_id': company_id})
            db.commit()
            print("Product added successfully")  # Debugging line
        except Exception as err:
            print(f"Error: {err}")
            db.rollback()
        return redirect(url_for('view_products'))
    return render_template('add_product.html')


@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    stats = {}
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    company_id = session.get('company_id')  # Get company ID from session

    try:
        cursor = db.cursor(dictionary=True)
        
        # Total stock quantity
        cursor.execute("""
            SELECT SUM(StockQuantity) as total_stock_quantity 
            FROM products 
            WHERE CompanyID = %s
        """, (company_id,))
        stats['total_stock_quantity'] = cursor.fetchone()['total_stock_quantity']
        
        if start_date and end_date:
            # Total paid in the specified date range
            cursor.execute("""
                SELECT SUM(Paid) as total_paid 
                FROM inventorytransactions 
                WHERE TransactionDate BETWEEN %s AND %s AND CompanyID = %s
            """, (start_date, end_date, company_id))
            stats['total_paid'] = cursor.fetchone()['total_paid']
            
            # Total expenses in the specified date range
            cursor.execute("""
                SELECT SUM(Amount) as total_expenses 
                FROM expenses 
                WHERE ExpenseDate BETWEEN %s AND %s AND CompanyID = %s
            """, (start_date, end_date, company_id))
            stats['total_expenses'] = cursor.fetchone()['total_expenses']
            
            # Total quantity sold in the specified date range
            cursor.execute("""
                SELECT SUM(Quantity) as total_quantity_sold 
                FROM orderdetails od 
                JOIN orders o ON od.OrderID = o.OrderID 
                WHERE o.OrderDate BETWEEN %s AND %s AND o.CompanyID = %s
            """, (start_date, end_date, company_id))
            stats['total_quantity_sold'] = cursor.fetchone()['total_quantity_sold']
            
            # Total quantity purchased in the specified date range
            cursor.execute("""
                SELECT SUM(Quantity) as total_quantity_purchased 
                FROM inventorytransactions 
                WHERE TransactionDate BETWEEN %s AND %s AND CompanyID = %s
            """, (start_date, end_date, company_id))
            stats['total_quantity_purchased'] = cursor.fetchone()['total_quantity_purchased']
            
            # Total amount and total paid in the specified date range
            cursor.execute("""
                SELECT 
                    SUM(it.Quantity * p.Price) as total_amount,
                    SUM(it.Paid) as total_paid
                FROM inventorytransactions it
                JOIN products p ON it.ProductID = p.ProductID
                WHERE it.TransactionDate BETWEEN %s AND %s AND it.CompanyID = %s
            """, (start_date, end_date, company_id))
        else:
            # Total paid (no date range)
            cursor.execute("""
                SELECT SUM(Paid) as total_paid 
                FROM inventorytransactions 
                WHERE CompanyID = %s
            """, (company_id,))
            stats['total_paid'] = cursor.fetchone()['total_paid']
            
            # Total expenses (no date range)
            cursor.execute("""
                SELECT SUM(Amount) as total_expenses 
                FROM expenses 
                WHERE CompanyID = %s
            """, (company_id,))
            stats['total_expenses'] = cursor.fetchone()['total_expenses']
            
            # Total quantity sold (no date range)
            cursor.execute("""
                SELECT SUM(Quantity) as total_quantity_sold 
                FROM orderdetails od
                JOIN orders o ON od.OrderID = o.OrderID
                WHERE o.CompanyID = %s
            """, (company_id,))
            stats['total_quantity_sold'] = cursor.fetchone()['total_quantity_sold']
            
            # Total quantity purchased (no date range)
            cursor.execute("""
                SELECT SUM(Quantity) as total_quantity_purchased 
                FROM inventorytransactions 
                WHERE CompanyID = %s
            """, (company_id,))
            stats['total_quantity_purchased'] = cursor.fetchone()['total_quantity_purchased']
            
            # Total amount and total paid (no date range)
            cursor.execute("""
                SELECT 
                    SUM(it.Quantity * p.Price) as total_amount,
                    SUM(it.Paid) as total_paid
                FROM inventorytransactions it
                JOIN products p ON it.ProductID = p.ProductID
                WHERE it.CompanyID = %s
            """, (company_id,))
        
        result = cursor.fetchone()
        total_amount = result['total_amount'] if result['total_amount'] is not None else 0
        total_paid = result['total_paid'] if result['total_paid'] is not None else 0
        balance = total_amount - total_paid
        stats['balance_to_pay_suppliers'] = balance
        
        if start_date and end_date:
            # Total sales amount in the specified date range
            cursor.execute("""
                SELECT 
                    SUM((od.Quantity * p.SellingPrice) + ((od.Quantity * p.SellingPrice) * od.Tax) - od.Discount) as total_sales_amount
                FROM orderdetails od
                JOIN products p ON od.ProductName = p.ProductID
                JOIN orders o ON od.OrderID = o.OrderID
                WHERE o.OrderDate BETWEEN %s AND %s AND o.CompanyID = %s
            """, (start_date, end_date, company_id))
        else:
            # Total sales amount (no date range)
            cursor.execute("""
                SELECT 
                    SUM((od.Quantity * p.SellingPrice) + ((od.Quantity * p.SellingPrice) * od.Tax) - od.Discount) as total_sales_amount
                FROM orderdetails od
                JOIN products p ON od.ProductName = p.ProductID
                JOIN orders o ON od.OrderID = o.OrderID
                WHERE o.CompanyID = %s
            """, (company_id,))
        
        sales_result = cursor.fetchone()
        stats['total_sales_amount'] = sales_result['total_sales_amount']
        
        # Count products with StockQuantity below ReorderOn
        cursor.execute("""
            SELECT COUNT(*) as low_stock_count
            FROM products
            WHERE StockQuantity < ReorderOn AND CompanyID = %s
        """, (company_id,))
        low_stock_result = cursor.fetchone()
        stats['low_stock_products'] = low_stock_result['low_stock_count']
        
        # Count products expiring in the next 30 days
        cursor.execute("""
            SELECT COUNT(*) as expiring_soon_count
            FROM products
            WHERE ExpiryDate <= DATE_ADD(CURDATE(), INTERVAL 30 DAY) AND CompanyID = %s
        """, (company_id,))
        expiring_soon_result = cursor.fetchone()
        stats['expiring_soon_products'] = expiring_soon_result['expiring_soon_count']

        # Fetch data for distribution chart
        if start_date and end_date:
            cursor.execute("""
                SELECT p.ProductName, SUM(od.Quantity) as total_quantity
                FROM orderdetails od
                JOIN orders o ON od.OrderID = o.OrderID
                JOIN products p ON od.ProductName = p.ProductID
                WHERE o.OrderDate BETWEEN %s AND %s AND o.CompanyID = %s
                GROUP BY p.ProductName
            """, (start_date, end_date, company_id))
        else:
            cursor.execute("""
                SELECT p.ProductName, SUM(od.Quantity) as total_quantity
                FROM orderdetails od
                JOIN orders o ON od.OrderID = o.OrderID
                JOIN products p ON od.ProductName = p.ProductID
                WHERE o.CompanyID = %s
                GROUP BY p.ProductName
            """, (company_id,))

        distribution_data = cursor.fetchall()
        stats['distribution_data'] = distribution_data

    except Error as err:
        print(f"Error: {err}")
        stats = {key: 'Error fetching data' for key in [
            'total_stock_quantity', 'total_paid', 'total_expenses', 
            'total_quantity_sold', 'total_quantity_purchased', 
            'balance_to_pay_suppliers', 'total_sales_amount', 
            'low_stock_products', 'expiring_soon_products',
            'distribution_data'
        ]}
    
    return render_template('dashboard.html', stats=stats)


#1


@app.route('/add_order', methods=['GET', 'POST'])
@login_required
def add_order():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    if request.method == 'POST':
        try:
            order_date = request.form['order_date']
            company_id = session.get('company_id')  # Get company ID from session
            
            # Insert order with company ID
            cursor.execute("INSERT INTO orders (OrderDate, CompanyID) VALUES (%s, %s)", (order_date, company_id))
            order_id = cursor.lastrowid
            
            products = request.form.getlist('product_id')
            quantities = request.form.getlist('quantity')
            taxes = request.form.getlist('tax')
            discounts = request.form.getlist('discount')
            payment_modes = request.form.getlist('payment_mode')

            for i in range(len(products)):
                cursor.execute("""
                    INSERT INTO orderdetails (OrderID, ProductName, Quantity, Tax, Discount, PaymentMode, CompanyID) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (order_id, products[i], quantities[i], taxes[i], discounts[i], payment_modes[i], company_id))

                # Update the StockQuantity in the products table
                cursor.execute("""
                    UPDATE products
                    SET StockQuantity = StockQuantity - %s
                    WHERE ProductID = %s AND CompanyID = %s
                """, (quantities[i], products[i], company_id))

            db.commit()
            return redirect(url_for('order_details', order_id=order_id))
        except Exception as err:
            db.rollback()
            print(f"Error: {err}")
            # Handle the error appropriately (e.g., show an error message to the user)

    # Fetch products with company ID
    company_id = session.get('company_id')
    cursor.execute("SELECT ProductID, ProductName, SellingPrice FROM products WHERE CompanyID = %s", (company_id,))
    products = cursor.fetchall()
    
    return render_template('sales_point.html', products=products)


@app.route('/order/<int:order_id>')
@login_required
def order_details(order_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Get order details
    cursor.execute("SELECT OrderID, OrderDate FROM orders WHERE OrderID = %s", (order_id,))
    order = cursor.fetchone()
    
    # Get order extended details
    cursor.execute("""
        SELECT od.OrderDetailsID, p.ProductName, od.Quantity, p.SellingPrice AS Price, od.Tax, od.Discount,
               (od.Quantity * p.SellingPrice) + ((od.Quantity * p.SellingPrice) * od.Tax) - od.Discount AS TotalAmount,
               od.PaymentMode
        FROM orderdetails od
        JOIN products p ON od.ProductName = p.ProductID
        WHERE od.OrderID = %s
    """, (order_id,))
    order_details = cursor.fetchall()
    
    return render_template('order_details.html', order=order, order_details=order_details)

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    if request.method == 'POST':
        data = {
            'product_name': request.form['product_name'],
            'manufacturer': request.form['manufacturer'],
           
            'price': request.form['price'],
            'selling_price': request.form['SellingPrice'],
            'stock_quantity': request.form['stock_quantity'],
            
            'supplier_id': request.form['supplier_id'],
            'usage': request.form['usage'],
            'description': request.form['description'],
         
            'drug_type': request.form['drug_type'],
            'reorder_on': request.form['reorder_on'],
            'product_id': product_id
        }

        try:
            sql_query = """
                UPDATE products 
                SET ProductName = %(product_name)s, Manufacturer = %(manufacturer)s, 
                    Price = %(price)s, SellingPrice = %(selling_price)s, StockQuantity = %(stock_quantity)s, 
                    SupplierID = %(supplier_id)s, `Usage` = %(usage)s, 
                    Description = %(description)s, DrugType = %(drug_type)s, 
                    ReorderOn = %(reorder_on)s 
                WHERE ProductID = %(product_id)s AND CompanyID = %(company_id)s
            """
            company_id = session.get('company_id')
            data['company_id'] = company_id
            cursor.execute(sql_query, data)
            db.commit()
        except Error as err:
            db.rollback()
            print(f"Error: {err}")
            # Handle the error appropriately (e.g., show an error message to the user)
        
        return redirect(url_for('view_products'))
    
    # Fetch the current product details
    company_id = session.get('company_id')
    cursor.execute("SELECT * FROM products WHERE ProductID = %s AND CompanyID = %s", (product_id, company_id))
    product = cursor.fetchone()
    
    return render_template('edit_product.html', product=product)

@app.route('/view_orders', methods=['GET', 'POST'])
@login_required
def view_orders():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Get the start and end dates from the form if present
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    company_id = session.get('company_id')  # Get company ID from session
    
    # Default query
    query = "SELECT * FROM orders WHERE CompanyID = %s"
    params = [company_id]

    # Modify query based on presence of start_date and end_date
    if start_date and end_date:
        query += " AND OrderDate BETWEEN %s AND %s"
        params.extend([start_date, end_date])
    elif start_date:
        query += " AND OrderDate >= %s"
        params.append(start_date)
    elif end_date:
        query += " AND OrderDate <= %s"
        params.append(end_date)

    cursor.execute(query, params)
    orders = cursor.fetchall()

    return render_template('order_list.html', orders=orders, start_date=start_date, end_date=end_date)


@app.route('/inventory_transaction', methods=['GET', 'POST'])
@login_required
def inventory_transaction():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    if request.method == 'POST':
        try:
            data = {
                'transaction_date': request.form['transaction_date'],
                'supplier_id': request.form['supplier_id'],
                'product_id': request.form['product_id'],
                'quantity': float(request.form['quantity']),  # Ensure quantity is a float
                'paid': float(request.form['paid']),          # Ensure paid amount is a float
                'through': request.form['through'],
                'status': request.form['status'],
                'transaction_no': request.form['transaction_no'],
                'narration': request.form['narration']
            }
            
            # Fetch unit price
            cursor.execute("SELECT Price FROM products WHERE ProductID = %s AND CompanyID = %s", (data['product_id'], session.get('company_id')))
            product = cursor.fetchone()
            if not product:
                # Handle case where product is not found
                raise ValueError("Product not found")
            unit_price = float(product['Price'])
            
            data['unit_price'] = unit_price
            data['total_amount'] = data['quantity'] * unit_price
            data['balance'] = data['total_amount'] - data['paid']
            
            # Insert into inventorytransactions table with company ID
            sql_query = """
                INSERT INTO inventorytransactions (TransactionDate, SupplierID, ProductID, Quantity, Paid, Through, Status, TransactionNo, Narration, TotalAmount, Balance, CompanyID) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            company_id = session.get('company_id')
            cursor.execute(sql_query, (
                data['transaction_date'],
                data['supplier_id'],
                data['product_id'],
                data['quantity'],
                data['paid'],
                data['through'],
                data['status'],
                data['transaction_no'],
                data['narration'],
                data['total_amount'],
                data['balance'],
                company_id
            ))
            db.commit()
            
            # Update stock quantity in products table
            cursor.execute("UPDATE products SET StockQuantity = StockQuantity + %s WHERE ProductID = %s AND CompanyID = %s", (data['quantity'], data['product_id'], company_id))
            db.commit()
            
            return redirect(url_for('inventory_transaction'))
        except Exception as err:
            db.rollback()
            print(f"Error: {err}")
            # Handle the error appropriately (e.g., show an error message to the user)
        except ValueError as ve:
            print(f"Value Error: {ve}")
            # Handle value errors, such as missing product data

    # Fetch suppliers and products for dropdowns
    cursor.execute("SELECT SupplierID, SupplierName FROM suppliers")
    suppliers = cursor.fetchall()
    
    company_id = session.get('company_id')
    cursor.execute("SELECT ProductID, ProductName FROM products WHERE CompanyID = %s", (company_id,))
    products = cursor.fetchall()
    
    return render_template('inventory_transaction.html', suppliers=suppliers, products=products)


@app.route('/show_all_transactions', methods=['GET', 'POST'])
@login_required
def show_all_transactions():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Get the start and end dates from the form if present
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    
    # Get the company ID from the session
    company_id = session.get('company_id')
    
    # Default query
    query = """
        SELECT it.TransactionID, it.TransactionDate, s.SupplierName, p.ProductName, p.Price AS UnitPrice,
               it.Quantity, it.Paid, it.TotalAmount, it.Balance, it.Through, it.Status, it.TransactionNo, it.Narration
        FROM inventorytransactions it
        JOIN suppliers s ON it.SupplierID = s.SupplierID
        JOIN products p ON it.ProductID = p.ProductID
        WHERE it.CompanyID = %s
    """
    params = [company_id]

    # Modify query based on presence of start_date and end_date
    if start_date and end_date:
        query += " AND it.TransactionDate BETWEEN %s AND %s"
        params.extend([start_date, end_date])
    elif start_date:
        query += " AND it.TransactionDate >= %s"
        params.append(start_date)
    elif end_date:
        query += " AND it.TransactionDate <= %s"
        params.append(end_date)

    cursor.execute(query, params)
    transactions = cursor.fetchall()
    
    return render_template('show_all_transactions.html', transactions=transactions, start_date=start_date, end_date=end_date)

@app.route('/edit_transaction/<int:transaction_id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(transaction_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    if request.method == 'POST':
        try:
            data = {
                'transaction_date': request.form['transaction_date'],
                'supplier_id': request.form['supplier_id'],
                'product_id': request.form['product_id'],
                'quantity': float(request.form['quantity']),  # Ensure quantity is a float
                'paid': float(request.form['paid']),          # Ensure paid amount is a float
                'through': request.form['through'],
                'status': request.form['status'],
                'transaction_no': request.form['transaction_no'],
                'narration': request.form['narration']
            }
            
            # Fetch unit price
            cursor.execute("SELECT Price FROM products WHERE ProductID = %s", (data['product_id'],))
            product = cursor.fetchone()
            if not product:
                # Handle case where product is not found
                raise ValueError("Product not found")
            unit_price = float(product['Price'])
            
            # Calculate total amount and balance
            data['total_amount'] = data['quantity'] * unit_price
            data['balance'] = data['total_amount'] - data['paid']
            
            # Update the inventorytransaction record
            sql_query = """
                UPDATE inventorytransactions
                SET TransactionDate = %s,
                    SupplierID = %s,
                    ProductID = %s,
                    Quantity = %s,
                    Paid = %s,
                    TotalAmount = %s,
                    Balance = %s,
                    Through = %s,
                    Status = %s,
                    TransactionNo = %s,
                    Narration = %s
                WHERE TransactionID = %s AND CompanyID = %s
            """
            company_id = session.get('company_id')
            cursor.execute(sql_query, (
                data['transaction_date'],
                data['supplier_id'],
                data['product_id'],
                data['quantity'],
                data['paid'],
                data['total_amount'],
                data['balance'],
                data['through'],
                data['status'],
                data['transaction_no'],
                data['narration'],
                transaction_id,
                company_id
            ))
            db.commit()
            
            # Update StockQuantity in products table
            cursor.execute("UPDATE products SET StockQuantity = StockQuantity + %s WHERE ProductID = %s AND CompanyID = %s", (data['quantity'], data['product_id'], company_id))
            db.commit()
            
            return redirect(url_for('show_all_transactions'))
        except Exception as err:
            db.rollback()
            print(f"Error: {err}")
            # Handle the error appropriately (e.g., show an error message to the user)
        except ValueError as ve:
            print(f"Value Error: {ve}")
            # Handle value errors, such as missing product data
    
    # Fetch current transaction details
    cursor.execute("""
        SELECT it.TransactionID, it.TransactionDate, it.SupplierID, it.ProductID, it.Quantity, it.Paid, it.TotalAmount, it.Balance, it.Through, it.Status, it.TransactionNo, it.Narration,
               s.SupplierName, p.ProductName, p.Price AS UnitPrice
        FROM inventorytransactions it
        JOIN suppliers s ON it.SupplierID = s.SupplierID
        JOIN products p ON it.ProductID = p.ProductID
        WHERE it.TransactionID = %s AND it.CompanyID = %s
    """, (transaction_id, session.get('company_id')))
    transaction = cursor.fetchone()

    # Fetch suppliers and products for dropdowns
    cursor.execute("SELECT SupplierID, SupplierName FROM suppliers WHERE CompanyID = %s", (session.get('company_id'),))
    suppliers = cursor.fetchall()
    
    cursor.execute("SELECT ProductID, ProductName FROM products WHERE CompanyID = %s", (session.get('company_id'),))
    products = cursor.fetchall()
    
    return render_template('edit_transaction.html', transaction=transaction, suppliers=suppliers, products=products)


@app.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    db = get_db()
    cursor = db.cursor()
    try:
        # Delete the transaction
        cursor.execute("DELETE FROM inventorytransactions WHERE TransactionID = %s AND CompanyID = %s", (transaction_id, session.get('company_id')))
        db.commit()
        return redirect(url_for('show_all_transactions'))
    except Error as err:
        print(f"Error: {err}")
        db.rollback()
        # Optionally: show an error message to the user
        return redirect(url_for('show_all_transactions'))

@app.route('/add_supplier', methods=['GET', 'POST'])
@login_required
def add_supplier():
    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor()
        
        # Validate and sanitize input data
        data = {
            'supplier_name': request.form['supplier_name'].strip(),
            'contact_person': request.form['contact_person'].strip(),
            'address': request.form['address'].strip(),
            'phone': request.form['phone'].strip(),
            'email': request.form['email'].strip(),
            'company_id': session.get('company_id')
        }
        
        # Check if supplier already exists
        cursor.execute("SELECT * FROM suppliers WHERE SupplierName = %s AND CompanyID = %s", (data['supplier_name'], data['company_id']))
        if cursor.fetchone():
            # Handle case where supplier already exists
            return redirect(url_for('show_all_suppliers'))
        
        sql_query = """
            INSERT INTO suppliers (SupplierName, ContactPerson, Address, Phone, Email, CompanyID) 
            VALUES (%(supplier_name)s, %(contact_person)s, %(address)s, %(phone)s, %(email)s, %(company_id)s)
        """
        cursor.execute(sql_query, data)
        db.commit()
        
        return redirect(url_for('show_all_suppliers'))
    
    return render_template('add_edit_supplier.html', supplier=None)

@app.route('/edit_supplier/<int:supplier_id>', methods=['GET', 'POST'])
@login_required
def edit_supplier(supplier_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    if request.method == 'POST':
        data = {
            'supplier_id': supplier_id,
            'supplier_name': request.form['supplier_name'].strip(),
            'contact_person': request.form['contact_person'].strip(),
            'address': request.form['address'].strip(),
            'phone': request.form['phone'].strip(),
            'email': request.form['email'].strip()
        }
        
        try:
            sql_query = """
                UPDATE suppliers 
                SET SupplierName = %(supplier_name)s, ContactPerson = %(contact_person)s, Address = %(address)s, Phone = %(phone)s, Email = %(email)s
                WHERE SupplierID = %(supplier_id)s AND CompanyID = %s
            """
            cursor.execute(sql_query, (*data.values(), session.get('company_id')))
            db.commit()
            return redirect(url_for('show_all_suppliers'))
        except Error as err:
            print(f"Error: {err}")
            db.rollback()
            # Optionally: show an error message to the user
    
    cursor.execute("SELECT * FROM suppliers WHERE SupplierID = %s AND CompanyID = %s", (supplier_id, session.get('company_id')))
    supplier = cursor.fetchone()
    
    return render_template('add_edit_supplier.html', supplier=supplier)

@app.route('/show_all_suppliers', methods=['GET'])
@login_required
def show_all_suppliers():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    search_query = request.args.get('search', '')  # Get the search query from the URL
    company_id = session.get('company_id')
    
    if search_query:
        # Search for suppliers by name
        cursor.execute("SELECT * FROM suppliers WHERE SupplierName LIKE %s AND CompanyID = %s", (f'%{search_query}%', company_id))
    else:
        # Get all suppliers if no search query
        cursor.execute("SELECT * FROM suppliers WHERE CompanyID = %s", (company_id,))
        
    suppliers = cursor.fetchall()
    
    return render_template('show_all_suppliers.html', suppliers=suppliers, search_query=search_query)

@app.route('/delete_supplier/<int:supplier_id>', methods=['POST'])
@login_required
def delete_supplier(supplier_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM suppliers WHERE SupplierID = %s AND CompanyID = %s", (supplier_id, session.get('company_id')))
        db.commit()
        return redirect(url_for('show_all_suppliers'))
    except Error as err:
        print(f"Error: {err}")
        db.rollback()
        # Optionally: show an error message to the user
        return redirect(url_for('show_all_suppliers'))

#3



@app.route('/add_employee', methods=['GET', 'POST'])
@login_required
def add_employee():
    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor()

        # Validate and sanitize input data
        data = {
            'first_name': request.form['first_name'].strip(),
            'last_name': request.form['last_name'].strip(),
            'position': request.form['position'].strip(),
            'hire_date': request.form['hire_date'].strip(),
            'salary': request.form['salary'].strip(),
            'company_id': session['company_id']
        }

        try:
            sql_query = """
                INSERT INTO employees (FirstName, LastName, Position, HireDate, Salary, CompanyID) 
                VALUES (%(first_name)s, %(last_name)s, %(position)s, %(hire_date)s, %(salary)s, %(company_id)s)
            """
            cursor.execute(sql_query, data)
            db.commit()
            flash('Employee successfully added.', 'success')
        except Exception as e:
            print(f"An error occurred: {e}")
            db.rollback()
            flash('An error occurred while adding the employee. Please try again.', 'error')

        return redirect(url_for('show_all_employees'))

    return render_template('add_edit_employee.html', employee=None)


@app.route('/edit_employee/<int:employee_id>', methods=['GET', 'POST'])
@login_required
def edit_employee(employee_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        data = {
            'employee_id': employee_id,
            'first_name': request.form['first_name'].strip(),
            'last_name': request.form['last_name'].strip(),
            'position': request.form['position'].strip(),
            'hire_date': request.form['hire_date'].strip(),
            'salary': request.form['salary'].strip(),
            'company_id': session['company_id']
        }

        try:
            sql_query = """
                UPDATE employees 
                SET FirstName = %(first_name)s, LastName = %(last_name)s, Position = %(position)s, HireDate = %(hire_date)s, Salary = %(salary)s
                WHERE EmployeeID = %(employee_id)s AND CompanyID = %(company_id)s
            """
            cursor.execute(sql_query, data)
            db.commit()
            flash('Employee details successfully updated.', 'success')
        except Exception as e:
            print(f"An error occurred: {e}")
            db.rollback()
            flash('An error occurred while updating the employee. Please try again.', 'error')

        return redirect(url_for('show_all_employees'))

    cursor.execute("SELECT * FROM employees WHERE EmployeeID = %s AND CompanyID = %s", (employee_id, session['company_id']))
    employee = cursor.fetchone()

    return render_template('add_edit_employee.html', employee=employee)


@app.route('/show_all_employees', methods=['GET'])
@login_required
def show_all_employees():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    search_query = request.args.get('search', '')  # Get the search query from the URL

    if search_query:
        # Search for employees by first name or last name within the company
        cursor.execute("SELECT * FROM employees WHERE CompanyID = %s AND (FirstName LIKE %s OR LastName LIKE %s)", 
                       (session['company_id'], f'%{search_query}%', f'%{search_query}%'))
    else:
        # Get all employees for the company
        cursor.execute("SELECT * FROM employees WHERE CompanyID = %s", (session['company_id'],))

    employees = cursor.fetchall()

    return render_template('show_all_employees.html', employees=employees, search_query=search_query)


@app.route('/delete_employee/<int:employee_id>', methods=['POST'])
@login_required
def delete_employee(employee_id):
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("DELETE FROM employees WHERE EmployeeID = %s AND CompanyID = %s", (employee_id, session['company_id']))
        db.commit()
        flash('Employee successfully deleted.', 'success')
    except Exception as e:
        print(f"An error occurred: {e}")
        db.rollback()
        flash('An error occurred while deleting the employee. Please try again.', 'error')

    return redirect(url_for('show_all_employees'))




@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor()

        # Validate and sanitize input data
        data = {
            'expense_date': request.form['expense_date'].strip(),
            'description': request.form['description'].strip(),
            'amount': request.form['amount'].strip(),
            'category': request.form['category'].strip(),
            'added_by': request.form['added_by'].strip(),
            'company_id': session['company_id']
        }

        try:
            sql_query = """
                INSERT INTO expenses (ExpenseDate, Description, Amount, Category, AddedBy, CompanyID) 
                VALUES (%(expense_date)s, %(description)s, %(amount)s, %(category)s, %(added_by)s, %(company_id)s)
            """
            cursor.execute(sql_query, data)
            db.commit()
            flash('Expense successfully added.', 'success')
        except Exception as e:
            print(f"An error occurred: {e}")
            db.rollback()
            flash('An error occurred while adding the expense. Please try again.', 'error')

        return redirect(url_for('show_all_expenses'))

    return render_template('add_edit_expense.html', expense=None)


@app.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        data = {
            'expense_id': expense_id,
            'expense_date': request.form['expense_date'].strip(),
            'description': request.form['description'].strip(),
            'amount': request.form['amount'].strip(),
            'category': request.form['category'].strip(),
            'added_by': request.form['added_by'].strip(),
            'company_id': session['company_id']
        }

        try:
            sql_query = """
                UPDATE expenses 
                SET ExpenseDate = %(expense_date)s, Description = %(description)s, Amount = %(amount)s, Category = %(category)s, AddedBy = %(added_by)s
                WHERE ExpenseID = %(expense_id)s AND CompanyID = %(company_id)s
            """
            cursor.execute(sql_query, data)
            db.commit()
            flash('Expense details successfully updated.', 'success')
        except Exception as e:
            print(f"An error occurred: {e}")
            db.rollback()
            flash('An error occurred while updating the expense. Please try again.', 'error')

        return redirect(url_for('show_all_expenses'))

    cursor.execute("SELECT * FROM expenses WHERE ExpenseID = %s AND CompanyID = %s", (expense_id, session['company_id']))
    expense = cursor.fetchone()

    return render_template('add_edit_expense.html', expense=expense)


@app.route('/show_all_expenses', methods=['GET'])
@login_required
def show_all_expenses():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    search_query = request.args.get('search', '')  # Get the search query from the URL

    if search_query:
        # Search for expenses by description or category within the company
        cursor.execute("SELECT * FROM expenses WHERE CompanyID = %s AND (Description LIKE %s OR Category LIKE %s)", 
                       (session['company_id'], f'%{search_query}%', f'%{search_query}%'))
    else:
        # Get all expenses for the company
        cursor.execute("SELECT * FROM expenses WHERE CompanyID = %s", (session['company_id'],))

    expenses = cursor.fetchall()

    return render_template('show_all_expenses.html', expenses=expenses, search_query=search_query)


@app.route('/delete_expense/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("DELETE FROM expenses WHERE ExpenseID = %s AND CompanyID = %s", (expense_id, session['company_id']))
        db.commit()
        flash('Expense successfully deleted.', 'success')
    except Exception as e:
        print(f"An error occurred: {e}")
        db.rollback()
        flash('An error occurred while deleting the expense. Please try again.', 'error')

    return redirect(url_for('show_all_expenses'))


@app.route('/order_list')
@login_required
def order_list():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    try:
        # Get all orders for the company
        cursor.execute("SELECT OrderID, OrderDate FROM orders WHERE CompanyID = %s", (session['company_id'],))
        orders = cursor.fetchall()
    except Exception as e:
        print(f"An error occurred: {e}")
        orders = []

    return render_template('order_list.html', orders=orders)


@app.route('/report')
@login_required
def report():
    db = get_db()
    report_data = []
    filter_due = request.args.get('filter_due', 'false').lower() == 'true'
    
    try:
        cursor = db.cursor(dictionary=True)
        query = """
            SELECT 
                p.ProductID,
                p.ProductName,
                COALESCE(SUM(od.Quantity), 0) AS QuantitySold,
                COALESCE(SUM(it.Quantity), 0) AS QuantityPurchased,
                p.StockQuantity,
                p.ReorderOn,
                CASE
                    WHEN p.StockQuantity < p.ReorderOn THEN 'Due'
                    ELSE 'Not Due'
                END AS ReorderStatus
            FROM
                products p
                LEFT JOIN orderdetails od ON p.ProductID = od.ProductName
                LEFT JOIN inventorytransactions it ON p.ProductID = it.ProductID
            WHERE
                p.CompanyID = %s
            GROUP BY
                p.ProductID, p.ProductName, p.StockQuantity, p.ReorderOn
        """
        if filter_due:
            query += " HAVING ReorderStatus = 'Due'"
        cursor.execute(query, (session['company_id'],))
        report_data = cursor.fetchall()
    except Exception as e:
        print(f"An error occurred: {e}")

    return render_template('report.html', report_data=report_data, filter_due=filter_due)


@app.route('/expiring-products')
@login_required
def expiring_products():
    db = get_db()
    expiring_products_data = []
    try:
        cursor = db.cursor(dictionary=True)
        query = """
            SELECT 
                ProductID, 
                ProductName, 
                Manufacturer, 
                StockQuantity, 
                ExpiryDate
            FROM 
                products
            WHERE 
                ExpiryDate <= DATE_ADD(CURDATE(), INTERVAL 30 DAY) AND CompanyID = %s
        """
        cursor.execute(query, (session['company_id'],))
        expiring_products_data = cursor.fetchall()
    except Error as err:
        print(f"Error: {err}")
    
    return render_template('expiring_products.html', expiring_products_data=expiring_products_data)


@app.route('/sales-report', methods=['GET', 'POST'])
@login_required
def sales_report():
    db = get_db()
    sales_data = []
    start_date = request.args.get('start_date', None)
    end_date = request.args.get('end_date', None)

    try:
        cursor = db.cursor(dictionary=True)
        
        # Base query
        query = """
            SELECT 
                p.ProductName,
                SUM((od.Quantity * p.SellingPrice) + ((od.Quantity * p.SellingPrice) * od.Tax) - od.Discount) AS TotalAmount
            FROM 
                orderdetails od
            JOIN 
                products p ON od.ProductName = p.ProductID
            JOIN
                orders o ON od.OrderID = o.OrderID
            WHERE
                o.OrderDate BETWEEN %s AND %s
                AND p.CompanyID = %s
            GROUP BY 
                p.ProductName
            ORDER BY 
                TotalAmount DESC
        """
        
        # Execute query with date range if provided
        if start_date and end_date:
            cursor.execute(query, (start_date, end_date, session['company_id']))
        else:
            cursor.execute(query, ('1900-01-01', '9999-12-31', session['company_id']))
        
        sales_data = cursor.fetchall()
    except Error as err:
        print(f"Error: {err}")
    
    return render_template('sales_report.html', sales_data=sales_data, start_date=start_date, end_date=end_date)


@app.route('/profit_report', methods=['GET', 'POST'])
@login_required
def profit_report():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Get start and end dates from form if present
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    
    # Base query to calculate profit with sorting
    query = """
        SELECT 
            p.ProductName,
            p.ProductID,
            SUM(od.Quantity) AS TotalQuantity,
            SUM((od.Quantity * p.SellingPrice) - (od.Quantity * p.Price)) AS TotalProfit,
            MIN(o.OrderDate) AS FirstOrderDate,
            MAX(o.OrderDate) AS LastOrderDate
        FROM 
            orderdetails od
        JOIN 
            products p ON od.ProductName = p.ProductID
        JOIN 
            orders o ON od.OrderID = o.OrderID
        WHERE 
            p.CompanyID = %s
    """
    params = [session['company_id']]
    
    # Apply date range filter if provided
    if start_date and end_date:
        query += " AND o.OrderDate BETWEEN %s AND %s"
        params.extend([start_date, end_date])
    elif start_date:
        query += " AND o.OrderDate >= %s"
        params.append(start_date)
    elif end_date:
        query += " AND o.OrderDate <= %s"
        params.append(end_date)
    
    # Group by ProductName and ProductID, and order by TotalProfit in descending order
    query += " GROUP BY p.ProductName, p.ProductID ORDER BY TotalProfit DESC"
    
    cursor.execute(query, params)
    profits = cursor.fetchall()
    
    # Calculate the grand total profit
    total_profit_query = """
        SELECT 
            SUM((od.Quantity * p.SellingPrice) - (od.Quantity * p.Price)) AS GrandTotalProfit
        FROM 
            orderdetails od
        JOIN 
            products p ON od.ProductName = p.ProductID
        JOIN 
            orders o ON od.OrderID = o.OrderID
        WHERE 
            p.CompanyID = %s
    """
    
    total_profit_params = [session['company_id']]
    if start_date and end_date:
        total_profit_query += " AND o.OrderDate BETWEEN %s AND %s"
        total_profit_params.extend([start_date, end_date])
    elif start_date:
        total_profit_query += " AND o.OrderDate >= %s"
        total_profit_params.append(start_date)
    elif end_date:
        total_profit_query += " AND o.OrderDate <= %s"
        total_profit_params.append(end_date)
    
    cursor.execute(total_profit_query, total_profit_params)
    grand_total_profit = cursor.fetchone()['GrandTotalProfit'] or 0

    return render_template('profit_report.html', profits=profits, start_date=start_date, end_date=end_date, grand_total_profit=grand_total_profit)



@app.route('/supplier_report')
@login_required
def supplier_report():
    query = """
    SELECT 
        s.SupplierID,
        s.SupplierName,
        SUM(i.Quantity) AS TotalQuantity,
        SUM(i.Quantity * p.Price) AS TotalAmount,
        SUM(i.Paid) AS TotalPaid,
        (SUM(i.Quantity * p.Price) - SUM(i.Paid)) AS Balance
    FROM 
        inventorytransactions i
    JOIN 
        products p ON i.ProductID = p.ProductID
    JOIN
        suppliers s ON i.SupplierID = s.SupplierID
    WHERE
        p.CompanyID = %s
    GROUP BY 
        s.SupplierID, s.SupplierName
    """

    # Get the database connection
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(query, (session['company_id'],))
    report_data = cursor.fetchall()
    cursor.close()

    return render_template('supplier_report.html', report_data=report_data)


@app.route('/order_detail/<int:order_detail_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_order_detail(order_detail_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    if request.method == 'POST':
        product_id = request.form['product_id']
        quantity = request.form['quantity']
        tax = request.form['tax']
        discount = request.form['discount']
        payment_mode = request.form['payment_mode']
        
        cursor.execute("""
            UPDATE orderdetails
            SET ProductName = %s, Quantity = %s, Tax = %s, Discount = %s, PaymentMode = %s
            WHERE OrderDetailsID = %s AND CompanyID = %s
        """, (product_id, quantity, tax, discount, payment_mode, order_detail_id, session['company_id']))
        
        db.commit()
        # Retrieve the order_id for redirection
        cursor.execute("SELECT OrderID FROM orderdetails WHERE OrderDetailsID = %s", (order_detail_id,))
        order_detail = cursor.fetchone()
        order_id = order_detail['OrderID']
        
        return redirect(url_for('order_details', order_id=order_id))
    
    cursor.execute("""
        SELECT od.*, p.ProductID
        FROM orderdetails od
        JOIN products p ON od.ProductName = p.ProductID
        WHERE od.OrderDetailsID = %s AND p.CompanyID = %s
    """, (order_detail_id, session['company_id']))
    order_detail = cursor.fetchone()
    
    cursor.execute("""
        SELECT ProductID, ProductName 
        FROM products 
        WHERE CompanyID = %s
    """, (session['company_id'],))
    products = cursor.fetchall()
    
    return render_template('edit_order_detail.html', order_detail=order_detail, products=products)



@app.route('/order_detail/<int:order_detail_id>/delete', methods=['POST'])
@login_required
def delete_order_detail(order_detail_id):
    db = get_db()
    cursor = db.cursor()
    
    # Delete the order detail
    cursor.execute("DELETE FROM orderdetails WHERE OrderDetailsID = %s AND CompanyID = %s", (order_detail_id, session['company_id']))
    db.commit()
    
    # Get the order_id from the form data
    order_id = request.form.get('order_id')
    
    # Debug print
    print(f"Order ID from form: {order_id}")
    
    # Redirect to the order_details page
    if not order_id:
        return "Error: Order ID is missing", 400
    
    return redirect(url_for('order_details', order_id=order_id))


@app.route('/invoice/<int:order_id>')
@login_required
def invoice(order_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Query to fetch order details
    query = """
    SELECT 
        o.OrderID,
        o.OrderDate,
        p.ProductName,
        d.Quantity,
        p.SellingPrice,
        d.Discount,
        d.Tax,
        (d.Quantity * p.SellingPrice) AS TotalAmount
    FROM orders o
    JOIN orderdetails d ON o.OrderID = d.OrderID
    JOIN products p ON d.ProductName = p.ProductID
    WHERE o.OrderID = %s AND p.CompanyID = %s
    """
    
    cursor.execute(query, (order_id, session['company_id']))
    details = cursor.fetchall()

    # Calculate total payable amount
    total_payable = sum(item['TotalAmount'] for item in details)

    # Fetch order summary
    query_order_summary = "SELECT * FROM orders WHERE OrderID = %s AND CompanyID = %s"
    cursor.execute(query_order_summary, (order_id, session['company_id']))
    order_summary = cursor.fetchone()

    return render_template('invoice.html', order_summary=order_summary, invoice_details=details, total_payable=total_payable)

@app.route('/payment_confirmation', methods=['POST'])
def payment_confirmation():
    data = request.get_json()
    reference = data.get('reference')
    email = data.get('email')
    amount = data.get('amount')
    order_id = data.get('order_id')  # Capture the OrderID from the form

    db = get_db()
    cursor = db.cursor()

    try:
        # Save payment details to the database, including OrderID
        query = """
            INSERT INTO payments (reference, email, amount, status, CompanyID, OrderID)
            VALUES (%s, %s, %s, 'completed', %s, %s)
        """
        cursor.execute(query, (reference, email, amount, session['company_id'], order_id))
        db.commit()
        return jsonify({'status': 'success', 'message': 'Payment details recorded.'}), 200
    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to record payment details.'}), 500


@app.route('/view_transactions', methods=['GET'])
def view_transactions():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM payments WHERE CompanyID = %s ORDER BY created_at DESC", (session['company_id'],))
    payments = cursor.fetchall()
    return render_template('view_transactions.html', payments=payments)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        company_name = request.form['companyName']
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        plan = request.form['plan']
        security_question = request.form['securityQuestion']
        security_answer = request.form['securityAnswer']

        if plan == 'paid':
            session['signup_data'] = {
                'company_name': company_name,
                'email': email,
                'username': username,
                'password': password,
                'security_question': security_question,
                'security_answer': security_answer
            }
            return redirect(url_for('pay'))

        # Handle free plan signup directly
        company_id = save_to_database(company_name, email, 'Free')
        save_user(username, password, company_id, security_question, security_answer)
        return redirect(url_for('signup_success', company_id=company_id))

    return render_template('signup.html')

@app.route('/pay', methods=['GET'])
def pay():
    signup_data = session.get('signup_data')
    if not signup_data:
        return redirect(url_for('signup'))
    
    # Pass data to your Paystack payment page
    return render_template('pay.html', data=signup_data)




@app.route('/confirm_payment', methods=['POST'])
def confirm_payment():
    data = request.json
    reference = data.get('reference')

    # Verify the payment with Paystack
    headers = {
        'Authorization': f'Bearer sk_test_9841b94baa622b81bc86987313d32a4eed88a9bf',  # Replace with your secret key
    }
    response = requests.get(f'https://api.paystack.co/transaction/verify/{reference}', headers=headers)
    result = response.json()

    if result['status'] and result['data']['status'] == 'success':
        signup_data = session.get('signup_data')
        company_id = save_to_database(signup_data['company_name'], signup_data['email'], 'Paid')
        
        # Ensure `signup_data` contains the additional fields
        security_question = signup_data.get('security_question')
        security_answer = signup_data.get('security_answer')
        
        # Pass all required arguments to `save_user`
        save_user(signup_data['username'], signup_data['password'], company_id, security_question, security_answer)
        
        session.pop('signup_data', None)
        return jsonify({'redirect': url_for('signup_success', company_id=company_id)})
    
    return jsonify({'message': 'Payment verification failed'}), 400




@app.route('/signup-success/<company_id>')
def signup_success(company_id):
    return render_template('signup_success.html', company_id=company_id)

def save_to_database(company_name, email, subscription_status):
    connection = get_db()  # Adjust this function as per your database connection
    with connection.cursor() as cursor:
        # Save to 'company' table
        cursor.execute(
            "INSERT INTO company (CompanyName, EmailAddress, SubscriptionStatus, DueDate) VALUES (%s, %s, %s, %s)",
            (company_name, email, subscription_status, datetime.now() + timedelta(days=30))
        )
        connection.commit()
        company_id = cursor.lastrowid
    return company_id

def save_user(username, password, company_id, security_question, security_answer):
    connection = get_db()
    with connection.cursor() as cursor:
        # Save to 'tblusers' table
        cursor.execute(
            "INSERT INTO tblusers (Username, Password, CompanyID, SecurityQuestion, SecurityAnswer) VALUES (%s, %s, %s, %s, %s)",
            (username, password, company_id, security_question, security_answer)
        )
        connection.commit()

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form['username']
        company_id = request.form['companyID']
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT SecurityQuestion FROM tblusers WHERE Username = %s AND CompanyID = %s",
            (username, company_id)
        )
        result = cursor.fetchone()
        if result:
            security_question = result[0]
            return render_template('reset_password.html', username=username, company_id=company_id, security_question=security_question)
        else:
            flash('Username or Company ID is incorrect.', 'error')
    return render_template('forgot_password.html')



@app.route('/reset-password', methods=['POST'])
def reset_password():
    username = request.form['username']
    company_id = request.form['companyID']
    security_question = request.form['securityQuestion']
    security_answer = request.form['securityAnswer']
    new_password = request.form['newPassword']
    confirm_password = request.form['confirmNewPassword']

    connection = get_db()
    cursor = connection.cursor()
    
    # Check if security answer is correct
    cursor.execute(
        "SELECT SecurityAnswer FROM tblusers WHERE Username = %s AND CompanyID = %s AND SecurityQuestion = %s",
        (username, company_id, security_question)
    )
    result = cursor.fetchone()

    if result and result[0] == security_answer:
        if new_password == confirm_password:
            # No hashing here, saving the new password directly
            cursor.execute(
                "UPDATE tblusers SET Password = %s WHERE Username = %s AND CompanyID = %s",
                (new_password, username, company_id)
            )
            connection.commit()
            flash('Password has been updated successfully.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Passwords do not match.', 'error')
    else:
        flash('Security answer is incorrect.', 'error')
    
    return render_template('reset_password.html', username=username, company_id=company_id, security_question=security_question)

@app.route('/subscription_history')
def subscription_history():
    # Get the company ID from the session
    company_id = session.get('company_id')
    if not company_id:
        flash('You must be logged in to view this page.')
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()

    # Fetch the due date from the company table
    cursor.execute("""
        SELECT DueDate 
        FROM company 
        WHERE CompanyID = %s
    """, (company_id,))
    due_date = cursor.fetchone()[0]

    # Fetch the subscription payment history
    cursor.execute("""
        SELECT id, reference, email, username, time_of_payment
        FROM subscriptionpayment
        WHERE companyID = %s
    """, (company_id,))
    payments = cursor.fetchall()

    return render_template('subscription_history.html', payments=payments, due_date=due_date)

@app.route('/add_service', methods=['GET', 'POST'])
def add_service():
    if request.method == 'POST':
        service_name = request.form['service_name']
        amount = request.form['amount']
        patient_name = request.form['patient_name']
        phone_number = request.form['phone_number']
        email = request.form['email']

        # Retrieve CompanyID from session
        company_id = session.get('company_id')

        # Save service details in the database with 'Pending' payment status
        connection = get_db()
        with connection.cursor() as cursor:
            cursor.execute('''
                INSERT INTO services (ServiceName, Amount, PatientName, PhoneNumber, Email, CompanyID, PaymentStatus)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (service_name, amount, patient_name, phone_number, email, company_id, 'Pending'))
            connection.commit()
        connection.close()

        # Redirect to Paystack payment page
        return redirect(url_for('pay_with_paystack', service_name=service_name, amount=amount, email=email))

    return render_template('add_service.html')

@app.route('/pay_with_paystack')
def pay_with_paystack():
    service_name = request.args.get('service_name')
    amount = request.args.get('amount')
    email = request.args.get('email')
    return render_template('paystack_payment.html', service_name=service_name, amount=amount, email=email)


@app.route('/confirm_service_payment', methods=['POST'])
def confirm_service_payment():
    data = request.get_json()
    reference = data['reference']
    service_name = data['service_name']
    amount = data['amount']
    patient_name = data['patient_name']
    phone_number = data['phone_number']
    email = data['email']

    # Retrieve CompanyID from session
    company_id = session.get('company_id')

    connection = get_db()
    with connection.cursor() as cursor:
        cursor.execute('''
            UPDATE services
            SET PaymentReference = %s, PaymentStatus = %s
            WHERE ServiceName = %s AND Amount = %s AND Email = %s AND CompanyID = %s
        ''', (reference, 'Completed', service_name, amount, email, company_id))
        connection.commit()
    connection.close()

    return jsonify({'status': 'success', 'message': 'Payment confirmed and service added successfully!'})

@app.route('/service_success')
def service_success():
    return 'Service added successfully with cash payment!'


@app.route('/chart-data')
@login_required
def chart_data():
    db = get_db()
    company_id = session.get('company_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    try:
        cursor = db.cursor(dictionary=True)

        if start_date and end_date:
            cursor.execute("""
                SELECT p.ProductName, SUM(od.Quantity) as total_quantity
                FROM orderdetails od
                JOIN orders o ON od.OrderID = o.OrderID
                JOIN products p ON od.ProductName = p.ProductID
                WHERE o.OrderDate BETWEEN %s AND %s AND o.CompanyID = %s
                GROUP BY p.ProductName
            """, (start_date, end_date, company_id))
        else:
            cursor.execute("""
                SELECT p.ProductName, SUM(od.Quantity) as total_quantity
                FROM orderdetails od
                JOIN orders o ON od.OrderID = o.OrderID
                JOIN products p ON od.ProductName = p.ProductID
                WHERE o.CompanyID = %s
                GROUP BY p.ProductName
            """, (company_id,))

        data = cursor.fetchall()
        labels = [row['ProductName'] for row in data]
        values = [row['total_quantity'] for row in data]

        return jsonify(labels=labels, values=values)
    
    except Error as err:
        print(f"Error: {err}")
        return jsonify(labels=[], values=[])

    
if __name__ == '__main__':
    app.run(debug=True)


