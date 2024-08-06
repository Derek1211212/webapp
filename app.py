from flask import Flask, render_template, request, redirect, url_for, flash, session, g
import mysql.connector
from mysql.connector import Error
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash
from functools import wraps
from flask import jsonify


app = Flask(__name__)
app.secret_key = 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3h4i5j6k7l8m9n0o1p2q3r4s5t6u7v8w9x0y1z2' 

def get_db():
    if 'db' not in g:
        g.db = mysql.connector.connect(
            host='108.181.197.186',
            port=10017,
            user="admin",
            password="SfSsSIft",
            database="new_schema"
        )
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def verify_user(username, password):
    db = get_db()
    cursor = db.cursor()
    query = 'SELECT * FROM tblusers WHERE Username = %s AND Password = %s'
    cursor.execute(query, (username, password))
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
        user = verify_user(username, password)
        if user:
            session['user_id'] = user[0]  # Store user ID or any unique identifier
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password')
    if 'user_id' in session:
        return redirect(url_for('home'))
    return render_template('login.html')  # Ensure you have a login.html template

@app.route('/home')
@login_required
def home():
    return render_template('index.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))



@app.route('/view_products', methods=['GET', 'POST'])
@login_required
def view_products():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    search_query = request.form.get('search_query', '')

    try:
        if search_query:
            cursor.execute("SELECT * FROM products WHERE ProductName LIKE %s", ('%' + search_query + '%',))
        else:
            cursor.execute("SELECT * FROM products")
        products = cursor.fetchall()
    except Error as err:
        products = []
        print(f"Error: {err}")

    return render_template('view_products.html', products=products, search_query=search_query)

@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM products WHERE ProductID = %s", (product_id,))
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
            'dosage': request.form['dosage'],
            'price': request.form['price'],  # Keep Price field
            'selling_price': request.form['selling_price'],  # New SellingPrice field
            'stock_quantity': request.form['stock_quantity'],
            'expiry_date': request.form['expiry_date'],
            'supplier_id': request.form['supplier_id'],
            'usage': request.form['usage'],
            'description': request.form['description'],
            'mfg_date': request.form['mfg_date'],
            'drug_type': request.form['drug_type'],
            'reorder_on': request.form['reorder_on']
        }
        print("Received data:", data)  # Debugging line
        db = get_db()
        try:
            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO products (ProductName, Manufacturer, Dosage, Price, SellingPrice, StockQuantity, ExpiryDate, SupplierID, `Usage`, Description, MfgDate, DrugType, ReorderOn) 
                VALUES (%(product_name)s, %(manufacturer)s, %(dosage)s, %(price)s, %(selling_price)s, %(stock_quantity)s, %(expiry_date)s, %(supplier_id)s, %(usage)s, %(description)s, %(mfg_date)s, %(drug_type)s, %(reorder_on)s)
            """, data)
            db.commit()
            print("Product added successfully")  # Debugging line
        except Error as err:
            print(f"Error: {err}")
        return redirect(url_for('view_products'))
    return render_template('add_product.html')


@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    stats = {}
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    try:
        cursor = db.cursor(dictionary=True)
        
        # Existing queries
        cursor.execute("SELECT SUM(StockQuantity) as total_stock_quantity FROM products")
        stats['total_stock_quantity'] = cursor.fetchone()['total_stock_quantity']
        
        if start_date and end_date:
            cursor.execute("""
                SELECT SUM(Paid) as total_paid 
                FROM inventorytransactions 
                WHERE TransactionDate BETWEEN %s AND %s
            """, (start_date, end_date))
            stats['total_paid'] = cursor.fetchone()['total_paid']
            
            cursor.execute("""
                SELECT SUM(Amount) as total_expenses 
                FROM expenses 
                WHERE ExpenseDate BETWEEN %s AND %s
            """, (start_date, end_date))
            stats['total_expenses'] = cursor.fetchone()['total_expenses']
            
            cursor.execute("""
                SELECT SUM(Quantity) as total_quantity_sold 
                FROM orderdetails od 
                JOIN orders o ON od.OrderID = o.OrderID 
                WHERE o.OrderDate BETWEEN %s AND %s
            """, (start_date, end_date))
            stats['total_quantity_sold'] = cursor.fetchone()['total_quantity_sold']
            
            cursor.execute("""
                SELECT SUM(Quantity) as total_quantity_purchased 
                FROM inventorytransactions 
                WHERE TransactionDate BETWEEN %s AND %s
            """, (start_date, end_date))
            stats['total_quantity_purchased'] = cursor.fetchone()['total_quantity_purchased']
            
            cursor.execute("""
                SELECT 
                    SUM(it.Quantity * p.Price) as total_amount,
                    SUM(it.Paid) as total_paid
                FROM inventorytransactions it
                JOIN products p ON it.ProductID = p.ProductID
                WHERE it.TransactionDate BETWEEN %s AND %s
            """, (start_date, end_date))
        else:
            cursor.execute("SELECT SUM(Paid) as total_paid FROM inventorytransactions")
            stats['total_paid'] = cursor.fetchone()['total_paid']
            
            cursor.execute("SELECT SUM(Amount) as total_expenses FROM expenses")
            stats['total_expenses'] = cursor.fetchone()['total_expenses']
            
            cursor.execute("SELECT SUM(Quantity) as total_quantity_sold FROM `orderdetails`")
            stats['total_quantity_sold'] = cursor.fetchone()['total_quantity_sold']
            
            cursor.execute("SELECT SUM(Quantity) as total_quantity_purchased FROM `inventorytransactions`")
            stats['total_quantity_purchased'] = cursor.fetchone()['total_quantity_purchased']
            
            cursor.execute("""
                SELECT 
                    SUM(it.Quantity * p.Price) as total_amount,
                    SUM(it.Paid) as total_paid
                FROM inventorytransactions it
                JOIN products p ON it.ProductID = p.ProductID
            """)
        
        result = cursor.fetchone()
        total_amount = result['total_amount'] if result['total_amount'] is not None else 0
        total_paid = result['total_paid'] if result['total_paid'] is not None else 0
        balance = total_amount - total_paid
        stats['balance_to_pay_suppliers'] = balance
        
        if start_date and end_date:
            cursor.execute("""
                SELECT 
                    SUM((od.Quantity * p.SellingPrice) + ((od.Quantity * p.SellingPrice) * od.Tax) - od.Discount) as total_sales_amount
                FROM orderdetails od
                JOIN products p ON od.ProductName = p.ProductID
                JOIN orders o ON od.OrderID = o.OrderID
                WHERE o.OrderDate BETWEEN %s AND %s
            """, (start_date, end_date))
        else:
            cursor.execute("""
                SELECT 
                    SUM((od.Quantity * p.SellingPrice) + ((od.Quantity * p.SellingPrice) * od.Tax) - od.Discount) as total_sales_amount
                FROM orderdetails od
                JOIN products p ON od.ProductName = p.ProductID
            """)
        
        sales_result = cursor.fetchone()
        stats['total_sales_amount'] = sales_result['total_sales_amount']
        
        # Count products with StockQuantity below ReorderOn
        cursor.execute("""
            SELECT COUNT(*) as low_stock_count
            FROM products
            WHERE StockQuantity < ReorderOn
        """)
        low_stock_result = cursor.fetchone()
        stats['low_stock_products'] = low_stock_result['low_stock_count']
        
        # Count products expiring in the next 30 days
        cursor.execute("""
            SELECT COUNT(*) as expiring_soon_count
            FROM products
            WHERE ExpiryDate <= DATE_ADD(CURDATE(), INTERVAL 30 DAY)
        """)
        expiring_soon_result = cursor.fetchone()
        stats['expiring_soon_products'] = expiring_soon_result['expiring_soon_count']
    
    except Error as err:
        print(f"Error: {err}")
        stats = {key: 'Error fetching data' for key in [
            'total_stock_quantity', 'total_paid', 'total_expenses', 
            'total_quantity_sold', 'total_quantity_purchased', 
            'balance_to_pay_suppliers', 'total_sales_amount', 
            'low_stock_products', 'expiring_soon_products'
        ]}
    
    return render_template('dashboard.html', stats=stats)



@app.route('/add_order', methods=['GET', 'POST'])
@login_required
def add_order():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    if request.method == 'POST':
        order_date = request.form['order_date']
        
        cursor.execute("INSERT INTO orders (OrderDate) VALUES (%s)", (order_date,))
        order_id = cursor.lastrowid
        
        products = request.form.getlist('product_id')
        quantities = request.form.getlist('quantity')
        taxes = request.form.getlist('tax')
        discounts = request.form.getlist('discount')
        payment_modes = request.form.getlist('payment_mode')

        for i in range(len(products)):
            cursor.execute("""
                INSERT INTO orderdetails (OrderID, ProductName, Quantity, Tax, Discount, PaymentMode) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (order_id, products[i], quantities[i], taxes[i], discounts[i], payment_modes[i]))

            # Update the StockQuantity in the products table
            cursor.execute("""
                UPDATE products
                SET StockQuantity = StockQuantity - %s
                WHERE ProductID = %s
            """, (quantities[i], products[i]))

        db.commit()
        return redirect(url_for('order_details', order_id=order_id))

    cursor.execute("SELECT ProductID, ProductName, SellingPrice FROM products")
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
            'dosage': request.form['dosage'],
            'price': request.form['price'],
            'selling_price': request.form['SellingPrice'],  # Updated to match form field name
            'stock_quantity': request.form['stock_quantity'],
            'expiry_date': request.form['expiry_date'],
            'supplier_id': request.form['supplier_id'],
            'usage': request.form['usage'],
            'description': request.form['description'],
            'mfg_date': request.form['mfg_date'],
            'drug_type': request.form['drug_type'],
            'reorder_on': request.form['reorder_on'],
            'product_id': product_id
        }

        try:
            sql_query = """
                UPDATE products 
                SET ProductName = %(product_name)s, Manufacturer = %(manufacturer)s, Dosage = %(dosage)s, 
                    Price = %(price)s, SellingPrice = %(selling_price)s, StockQuantity = %(stock_quantity)s, 
                    ExpiryDate = %(expiry_date)s, SupplierID = %(supplier_id)s, `Usage` = %(usage)s, 
                    Description = %(description)s, MfgDate = %(mfg_date)s, DrugType = %(drug_type)s, 
                    ReorderOn = %(reorder_on)s 
                WHERE ProductID = %(product_id)s
            """
            cursor.execute(sql_query, data)
            db.commit()
        except Error as err:
            print(f"Error: {err}")
        
        return redirect(url_for('view_products'))
    
    # Fetch the current product details
    cursor.execute("SELECT * FROM products WHERE ProductID = %s", (product_id,))
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
    
    # Default query
    query = "SELECT * FROM orders"
    params = []

    # Modify query based on presence of start_date and end_date
    if start_date and end_date:
        query += " WHERE OrderDate BETWEEN %s AND %s"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE OrderDate >= %s"
        params = [start_date]
    elif end_date:
        query += " WHERE OrderDate <= %s"
        params = [end_date]

    cursor.execute(query, params)
    orders = cursor.fetchall()

    return render_template('order_list.html', orders=orders, start_date=start_date, end_date=end_date)


@app.route('/inventory_transaction', methods=['GET', 'POST'])
@login_required
def inventory_transaction():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    if request.method == 'POST':
        data = {
            'transaction_date': request.form['transaction_date'],
            'supplier_id': request.form['supplier_id'],
            'product_id': request.form['product_id'],
            'quantity': request.form['quantity'],
            'paid': request.form['paid'],
            'through': request.form['through'],
            'status': request.form['status'],
            'transaction_no': request.form['transaction_no'],
            'narration': request.form['narration']
        }
        
        # Fetch unit price
        cursor.execute("SELECT Price FROM products WHERE ProductID = %s", (data['product_id'],))
        unit_price = cursor.fetchone()['Price']
        
        # Convert unit_price to float
        unit_price = float(unit_price)
        
        data['unit_price'] = unit_price
        data['total_amount'] = float(data['quantity']) * unit_price
        data['balance'] = data['total_amount'] - float(data['paid'])
        
        # Insert into inventorytransactions table
        sql_query = """
            INSERT INTO inventorytransactions (TransactionDate, SupplierID, ProductID, Quantity, Paid, Through, Status, TransactionNo, Narration, TotalAmount, Balance) 
            VALUES (%(transaction_date)s, %(supplier_id)s, %(product_id)s, %(quantity)s, %(paid)s, %(through)s, %(status)s, %(transaction_no)s, %(narration)s, %(total_amount)s, %(balance)s)
        """
        cursor.execute(sql_query, data)
        db.commit()
        
        # Update stock quantity in products table
        cursor.execute("UPDATE products SET StockQuantity = StockQuantity + %s WHERE ProductID = %s", (data['quantity'], data['product_id']))
        db.commit()
        
        return redirect(url_for('inventory_transaction'))
    
    # Fetch suppliers and products for dropdowns
    cursor.execute("SELECT SupplierID, SupplierName FROM suppliers")
    suppliers = cursor.fetchall()
    
    cursor.execute("SELECT ProductID, ProductName FROM products")
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
    
    # Default query
    query = """
        SELECT it.TransactionID, it.TransactionDate, s.SupplierName, p.ProductName, p.Price AS UnitPrice,
               it.Quantity, it.Paid, it.TotalAmount, it.Balance, it.Through, it.Status, it.TransactionNo, it.Narration
        FROM inventorytransactions it
        JOIN suppliers s ON it.SupplierID = s.SupplierID
        JOIN products p ON it.ProductID = p.ProductID
    """
    params = []

    # Modify query based on presence of start_date and end_date
    if start_date and end_date:
        query += " WHERE it.TransactionDate BETWEEN %s AND %s"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE it.TransactionDate >= %s"
        params = [start_date]
    elif end_date:
        query += " WHERE it.TransactionDate <= %s"
        params = [end_date]

    cursor.execute(query, params)
    transactions = cursor.fetchall()
    
    return render_template('show_all_transactions.html', transactions=transactions, start_date=start_date, end_date=end_date)


@app.route('/edit_transaction/<int:transaction_id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(transaction_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    if request.method == 'POST':
        data = {
            'transaction_id': transaction_id,
            'transaction_date': request.form['transaction_date'],
            'supplier_id': request.form['supplier_id'],
            'product_id': request.form['product_id'],
            'quantity': request.form['quantity'],
            'paid': request.form['paid'],
            'through': request.form['through'],
            'status': request.form['status'],
            'transaction_no': request.form['transaction_no'],
            'narration': request.form['narration']
        }
        
        # Fetch unit price
        cursor.execute("SELECT Price FROM products WHERE ProductID = %s", (data['product_id'],))
        unit_price = cursor.fetchone()['Price']
        
        # Convert unit price to float if it's not already
        unit_price = float(unit_price)  # Ensure unit_price is a float
        
        # Calculate total amount and balance
        data['total_amount'] = float(data['quantity']) * unit_price
        data['balance'] = data['total_amount'] - float(data['paid'])
        
        # Update the inventorytransaction record
        sql_query = """
            UPDATE inventorytransactions
            SET TransactionDate = %(transaction_date)s,
                SupplierID = %(supplier_id)s,
                ProductID = %(product_id)s,
                Quantity = %(quantity)s,
                Paid = %(paid)s,
                TotalAmount = %(total_amount)s,
                Balance = %(balance)s,
                Through = %(through)s,
                Status = %(status)s,
                TransactionNo = %(transaction_no)s,
                Narration = %(narration)s
            WHERE TransactionID = %(transaction_id)s
        """
        cursor.execute(sql_query, data)
        db.commit()
        
        # Update StockQuantity in products table
        cursor.execute("UPDATE products SET StockQuantity = StockQuantity + %s WHERE ProductID = %s", (data['quantity'], data['product_id']))
        db.commit()
        
        return redirect(url_for('show_all_transactions'))
    
    # Fetch current transaction details
    cursor.execute("""
        SELECT it.TransactionID, it.TransactionDate, it.SupplierID, it.ProductID, it.Quantity, it.Paid, it.TotalAmount, it.Balance, it.Through, it.Status, it.TransactionNo, it.Narration,
               s.SupplierName, p.ProductName, p.Price AS UnitPrice
        FROM inventorytransactions it
        JOIN suppliers s ON it.SupplierID = s.SupplierID
        JOIN products p ON it.ProductID = p.ProductID
        WHERE it.TransactionID = %s
    """, (transaction_id,))
    transaction = cursor.fetchone()

    # Fetch suppliers and products for dropdowns
    cursor.execute("SELECT SupplierID, SupplierName FROM suppliers")
    suppliers = cursor.fetchall()
    
    cursor.execute("SELECT ProductID, ProductName FROM products")
    products = cursor.fetchall()
    
    return render_template('edit_transaction.html', transaction=transaction, suppliers=suppliers, products=products)


@app.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM inventorytransactions WHERE TransactionID = %s", (transaction_id,))
        db.commit()
    except Error as err:
        print(f"Error: {err}")
    return redirect(url_for('show_all_transactions'))



@app.route('/add_supplier', methods=['GET', 'POST'])
@login_required
def add_supplier():
    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor()
        
        data = {
            'supplier_name': request.form['supplier_name'],
            'contact_person': request.form['contact_person'],
            'address': request.form['address'],
            'phone': request.form['phone'],
            'email': request.form['email']
        }
        
        sql_query = """
            INSERT INTO suppliers (SupplierName, ContactPerson, Address, Phone, Email) 
            VALUES (%(supplier_name)s, %(contact_person)s, %(address)s, %(phone)s, %(email)s)
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
            'supplier_name': request.form['supplier_name'],
            'contact_person': request.form['contact_person'],
            'address': request.form['address'],
            'phone': request.form['phone'],
            'email': request.form['email']
        }
        
        sql_query = """
            UPDATE suppliers 
            SET SupplierName = %(supplier_name)s, ContactPerson = %(contact_person)s, Address = %(address)s, Phone = %(phone)s, Email = %(email)s
            WHERE SupplierID = %(supplier_id)s
        """
        cursor.execute(sql_query, data)
        db.commit()
        
        return redirect(url_for('show_all_suppliers'))
    
    cursor.execute("SELECT * FROM suppliers WHERE SupplierID = %s", (supplier_id,))
    supplier = cursor.fetchone()
    
    return render_template('add_edit_supplier.html', supplier=supplier)

@app.route('/show_all_suppliers', methods=['GET', 'POST'])
def show_all_suppliers():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    search_query = request.args.get('search', '')  # Get the search query from the URL
    
    if search_query:
        # Search for suppliers by name
        cursor.execute("SELECT * FROM suppliers WHERE SupplierName LIKE %s", (f'%{search_query}%',))
    else:
        # Get all suppliers if no search query
        cursor.execute("SELECT * FROM suppliers")
        
    suppliers = cursor.fetchall()
    
    return render_template('show_all_suppliers.html', suppliers=suppliers, search_query=search_query)

@app.route('/delete_supplier/<int:supplier_id>', methods=['POST'])
@login_required
def delete_supplier(supplier_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM suppliers WHERE SupplierID = %s", (supplier_id,))
        db.commit()
    except Error as err:
        print(f"Error: {err}")
        db.rollback()
    return redirect(url_for('show_all_suppliers'))



@app.route('/add_employee', methods=['GET', 'POST'])
@login_required
def add_employee():
    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor()
        
        data = {
            'first_name': request.form['first_name'],
            'last_name': request.form['last_name'],
            'position': request.form['position'],
            'hire_date': request.form['hire_date'],
            'salary': request.form['salary']
        }
        
        sql_query = """
            INSERT INTO employees (FirstName, LastName, Position, HireDate, Salary) 
            VALUES (%(first_name)s, %(last_name)s, %(position)s, %(hire_date)s, %(salary)s)
        """
        cursor.execute(sql_query, data)
        db.commit()
        
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
            'first_name': request.form['first_name'],
            'last_name': request.form['last_name'],
            'position': request.form['position'],
            'hire_date': request.form['hire_date'],
            'salary': request.form['salary']
        }
        
        sql_query = """
            UPDATE employees 
            SET FirstName = %(first_name)s, LastName = %(last_name)s, Position = %(position)s, HireDate = %(hire_date)s, Salary = %(salary)s
            WHERE EmployeeID = %(employee_id)s
        """
        cursor.execute(sql_query, data)
        db.commit()
        
        return redirect(url_for('show_all_employees'))
    
    cursor.execute("SELECT * FROM employees WHERE EmployeeID = %s", (employee_id,))
    employee = cursor.fetchone()
    
    return render_template('add_edit_employee.html', employee=employee)

@app.route('/show_all_employees', methods=['GET', 'POST'])
@login_required
def show_all_employees():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    search_query = request.args.get('search', '')  # Get the search query from the URL
    
    if search_query:
        # Search for employees by first name or last name
        cursor.execute("SELECT * FROM employees WHERE FirstName LIKE %s OR LastName LIKE %s", (f'%{search_query}%', f'%{search_query}%'))
    else:
        # Get all employees if no search query
        cursor.execute("SELECT * FROM employees")
        
    employees = cursor.fetchall()
    
    return render_template('show_all_employees.html', employees=employees, search_query=search_query)

@app.route('/delete_employee/<int:employee_id>', methods=['POST'])
@login_required
def delete_employee(employee_id):
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("DELETE FROM employees WHERE EmployeeID = %s", (employee_id,))
        db.commit()
    except Exception as e:
        print(f"An error occurred: {e}")
    
    return redirect(url_for('show_all_employees'))



@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor()
        
        data = {
            'expense_date': request.form['expense_date'],
            'description': request.form['description'],
            'amount': request.form['amount'],
            'category': request.form['category'],
            'added_by': request.form['added_by']
        }
        
        sql_query = """
            INSERT INTO expenses (ExpenseDate, Description, Amount, Category, AddedBy) 
            VALUES (%(expense_date)s, %(description)s, %(amount)s, %(category)s, %(added_by)s)
        """
        cursor.execute(sql_query, data)
        db.commit()
        
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
            'expense_date': request.form['expense_date'],
            'description': request.form['description'],
            'amount': request.form['amount'],
            'category': request.form['category'],
            'added_by': request.form['added_by']
        }
        
        sql_query = """
            UPDATE expenses 
            SET ExpenseDate = %(expense_date)s, Description = %(description)s, Amount = %(amount)s, Category = %(category)s, AddedBy = %(added_by)s
            WHERE ExpenseID = %(expense_id)s
        """
        cursor.execute(sql_query, data)
        db.commit()
        
        return redirect(url_for('show_all_expenses'))
    
    cursor.execute("SELECT * FROM expenses WHERE ExpenseID = %s", (expense_id,))
    expense = cursor.fetchone()
    
    return render_template('add_edit_expense.html', expense=expense)

@app.route('/show_all_expenses', methods=['GET'])
@login_required
def show_all_expenses():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    search_query = request.args.get('search', '')  # Get the search query from the URL
    
    if search_query:
        # Search for expenses by description or category
        cursor.execute("SELECT * FROM expenses WHERE Description LIKE %s OR Category LIKE %s", (f'%{search_query}%', f'%{search_query}%'))
    else:
        # Get all expenses if no search query
        cursor.execute("SELECT * FROM expenses")
        
    expenses = cursor.fetchall()
    
    return render_template('show_all_expenses.html', expenses=expenses, search_query=search_query)


@app.route('/delete_expense/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Execute the deletion query
        cursor.execute("DELETE FROM expenses WHERE ExpenseID = %s", (expense_id,))
        db.commit()
        # Optionally, flash a success message
        flash('Expense successfully deleted.', 'success')
    except Exception as e:
        # Print the error for debugging purposes
        print(f"An error occurred: {e}")
        # Optionally, flash an error message
        flash('An error occurred while deleting the expense. Please try again.', 'error')
    
    return redirect(url_for('show_all_expenses'))
    

@app.route('/order_list')
@login_required
def order_list():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Get all orders
    cursor.execute("SELECT OrderID, OrderDate FROM orders")
    orders = cursor.fetchall()
    
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
            GROUP BY
                p.ProductID, p.ProductName, p.StockQuantity, p.ReorderOn
        """
        if filter_due:
            query += " HAVING ReorderStatus = 'Due'"
        cursor.execute(query)
        report_data = cursor.fetchall()
    except Error as err:
        print(f"Error: {err}")
    
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
                ExpiryDate <= DATE_ADD(CURDATE(), INTERVAL 30 DAY)
        """
        cursor.execute(query)
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
            GROUP BY 
                p.ProductName
            ORDER BY 
                TotalAmount DESC
        """
        
        # Execute query with date range if provided
        if start_date and end_date:
            cursor.execute(query, (start_date, end_date))
        else:
            cursor.execute(query, ('1900-01-01', '9999-12-31'))
        
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
        FROM orderdetails od
        JOIN products p ON od.ProductName = p.ProductID
        JOIN orders o ON od.OrderID = o.OrderID
    """
    params = []
    
    # Apply date range filter if provided
    if start_date and end_date:
        query += " WHERE o.OrderDate BETWEEN %s AND %s"
        params.extend([start_date, end_date])
    elif start_date:
        query += " WHERE o.OrderDate >= %s"
        params.append(start_date)
    elif end_date:
        query += " WHERE o.OrderDate <= %s"
        params.append(end_date)
    
    # Group by ProductName and ProductID, and order by TotalProfit in descending order
    query += " GROUP BY p.ProductName, p.ProductID ORDER BY TotalProfit DESC"
    
    cursor.execute(query, params)
    profits = cursor.fetchall()
    
    # Calculate the grand total profit
    total_profit_query = """
        SELECT 
            SUM((od.Quantity * p.SellingPrice) - (od.Quantity * p.Price)) AS GrandTotalProfit
        FROM orderdetails od
        JOIN products p ON od.ProductName = p.ProductID
        JOIN orders o ON od.OrderID = o.OrderID
    """
    
    if start_date and end_date:
        total_profit_query += " WHERE o.OrderDate BETWEEN %s AND %s"
        params.extend([start_date, end_date])
    elif start_date:
        total_profit_query += " WHERE o.OrderDate >= %s"
        params.append(start_date)
    elif end_date:
        total_profit_query += " WHERE o.OrderDate <= %s"
        params.append(end_date)
    
    cursor.execute(total_profit_query, params)
    grand_total_profit = cursor.fetchone()['GrandTotalProfit'] or 0

    return render_template('profit_report.html', profits=profits, start_date=start_date, end_date=end_date, grand_total_profit=grand_total_profit)



@app.route('/forgot-password', methods=['GET'])
@login_required
def forgot_password():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT DISTINCT SecurityQuestion FROM tblusers")
    questions = cursor.fetchall()
    questions = [q[0] for q in questions]
    db.close()
    
    return render_template('forgot_password.html', questions=questions)

@app.route('/reset-password', methods=['POST'])
@login_required
def reset_password():
    username = request.form['username']
    security_question = request.form['security_question']
    security_answer = request.form['security_answer']
    new_password = request.form['new_password']
    confirm_new_password = request.form['confirm_new_password']

    if new_password != confirm_new_password:
        flash('Passwords do not match.', 'error')
        return redirect(url_for('forgot_password'))

    db = get_db()
    cursor = db.cursor()

    # Check if the username and security answer match
    cursor.execute("SELECT SecurityQuestion, SecurityAnswer FROM tblusers WHERE Username = %s", (username,))
    user = cursor.fetchone()

    if user and user[0] == security_question and user[1] == security_answer:
        cursor.execute("UPDATE tblusers SET Password = %s WHERE Username = %s", (new_password, username))
        db.commit()
        db.close()
        flash('Your password has been reset successfully. You can now log in.', 'success')
        return redirect(url_for('login'))
    else:
        db.close()
        flash('Username, security question, or answer is incorrect.', 'error')
        return redirect(url_for('forgot_password'))



# Function to close the database connection
@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Route to generate supplier report
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
    GROUP BY 
        s.SupplierID, s.SupplierName
    """

    # Get the database connection
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(query)
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
            WHERE OrderDetailsID = %s
        """, (product_id, quantity, tax, discount, payment_mode, order_detail_id))
        
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
        WHERE od.OrderDetailsID = %s
    """, (order_detail_id,))
    order_detail = cursor.fetchone()
    
    cursor.execute("SELECT ProductID, ProductName FROM products")
    products = cursor.fetchall()
    
    return render_template('edit_order_detail.html', order_detail=order_detail, products=products)


@app.route('/order_detail/<int:order_detail_id>/delete', methods=['POST'])
@login_required
def delete_order_detail(order_detail_id):
    db = get_db()
    cursor = db.cursor()
    
    # Delete the order detail
    cursor.execute("DELETE FROM orderdetails WHERE OrderDetailsID = %s", (order_detail_id,))
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
    WHERE o.OrderID = %s
    """
    
    cursor.execute(query, (order_id,))
    details = cursor.fetchall()

    # Calculate total payable amount
    total_payable = sum(item['TotalAmount'] for item in details)

    # Fetch order summary
    query_order_summary = "SELECT * FROM orders WHERE OrderID = %s"
    cursor.execute(query_order_summary, (order_id,))
    order_summary = cursor.fetchone()

    return render_template('invoice.html', order_summary=order_summary, invoice_details=details, total_payable=total_payable)

@app.route('/payment_confirmation', methods=['POST'])
def payment_confirmation():
    data = request.get_json()
    reference = data.get('reference')
    email = data.get('email')
    amount = data.get('amount')

    db = get_db()
    cursor = db.cursor()

    try:
        # Save payment details to database
        query = """
            INSERT INTO payments (reference, email, amount, status)
            VALUES (%s, %s, %s, 'completed')
        """
        cursor.execute(query, (reference, email, amount))
        db.commit()
        return jsonify({'status': 'success', 'message': 'Payment details recorded.'}), 200
    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to record payment details.'}), 500

@app.route('/view_transactions', methods=['GET'])
def view_transactions():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM payments ORDER BY created_at DESC")
    payments = cursor.fetchall()
    return render_template('view_transactions.html', payments=payments)


if __name__ == '__main__':
    app.run(debug=True)
