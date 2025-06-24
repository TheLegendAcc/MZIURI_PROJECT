from flask import Flask, render_template, request, redirect, url_for, session, flash, get_flashed_messages
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "your_secret_key"

DB_NAME = 'database.db'




def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            seller_id INTEGER,
            FOREIGN KEY (seller_id) REFERENCES users(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER,
            product_id INTEGER,
            FOREIGN KEY (buyer_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )''')
        conn.commit()




def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn




@app.route('/')
def index():
    db = get_db()
    products = db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return render_template("index.html", products=products)




@app.route('/product/<int:product_id>')
def product(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for('index'))
    return render_template("product.html", product=product)




@app.route('/buy/<int:product_id>', methods=['POST'])
def buy(product_id):
    if 'user_id' not in session:
        flash("Please log in to buy products.", "warning")
        return redirect(url_for('login'))

    db = get_db()

    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for('index'))

    if product['seller_id'] == session['user_id']:
        flash("You can't buy your own product!", "danger")
        return redirect(url_for('product', product_id=product_id))

    already_bought = db.execute(
        "SELECT * FROM purchases WHERE product_id = ?", (product_id,)
    ).fetchone()
    if already_bought:
        flash("This product has already been purchased.", "warning")
        return redirect(url_for('product', product_id=product_id))

    db.execute(
        "INSERT INTO purchases (buyer_id, product_id) VALUES (?, ?)",
        (session['user_id'], product_id)
    )
    db.commit()
    flash("Product purchased successfully!", "success")
    return redirect(url_for('index'))




@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        db = get_db()
        try:
            db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            db.commit()
            flash('Registered successfully. Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists.', 'danger')
    return render_template("register.html")




@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Logged in successfully.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template("login.html")




@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))




@app.route('/post', methods=['GET', 'POST'])
def post():
    if 'user_id' not in session:
        flash('Please log in to post products.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = float(request.form['price'])
        seller_id = session['user_id']

        db = get_db()
        db.execute('''INSERT INTO products (title, description, price, seller_id)
                      VALUES (?, ?, ?, ?)''', (title, description, price, seller_id))
        db.commit()
        flash('Product posted!', 'success')
        return redirect(url_for('index'))

    return render_template("post.html")




@app.route('/search')
def search():
    query = request.args.get('query', '')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')

    db = get_db()
    sql = "SELECT * FROM products WHERE 1=1"
    params = []

    if query:
        sql += " AND (title LIKE ? OR description LIKE ?)"
        params += [f'%{query}%', f'%{query}%']
    if min_price:
        sql += " AND price >= ?"
        params.append(min_price)
    if max_price:
        sql += " AND price <= ?"
        params.append(max_price)

    products = db.execute(sql, params).fetchall()
    return render_template("search.html", products=products, query=query)




@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        flash("Please log in to checkout.", "warning")
        return redirect(url_for('login'))

    cart = session.get('cart', {})
    if not cart:
        flash("Your cart is empty.", "info")
        return redirect(url_for('index'))

    db = get_db()
    product_ids = list(cart.keys())
    query = f"SELECT * FROM products WHERE id IN ({','.join('?'*len(product_ids))})"
    products = db.execute(query, product_ids).fetchall()

    if request.method == 'POST':
        for p in products:
            product_id = p['id']
            already_bought = db.execute(
                "SELECT * FROM purchases WHERE product_id = ?", (product_id,)
            ).fetchone()
            if not already_bought:
                db.execute(
                    "INSERT INTO purchases (buyer_id, product_id) VALUES (?, ?)",
                    (session['user_id'], product_id)
                )
        db.commit()
        session['cart'] = {}
        flash("Purchase successful! Thank you.", "success")
        return redirect(url_for('index'))

    total = sum(p['price'] * cart[str(p['id'])] for p in products)

    return render_template('checkout.html', products=products, cart=cart, total=total)




@app.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'user_id' not in session:
        flash("Please log in to add products to cart.", "warning")
        return redirect(url_for('login'))

    cart = session.get('cart', {})

    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session['cart'] = cart
    flash("Product added to cart.", "success")
    return redirect(request.referrer or url_for('index'))




@app.route('/cart')
def cart():
    if 'user_id' not in session:
        flash("Please log in to view your cart.", "warning")
        return redirect(url_for('login'))

    cart = session.get('cart', {})
    product_ids = list(cart.keys())

    db = get_db()
    if product_ids:
        query = f"SELECT * FROM products WHERE id IN ({','.join('?'*len(product_ids))})"
        products = db.execute(query, product_ids).fetchall()
    else:
        products = []


    cart_items = []
    for p in products:
        cart_items.append({
            'product': p,
            'quantity': cart.get(str(p['id']), 0)
        })

    return render_template('cart.html', cart_items=cart_items)




@app.context_processor
def inject_flashes():
    messages = get_flashed_messages(with_categories=True)
    return dict(flashed_messages=messages)




if __name__ == '__main__':
    if not os.path.exists(DB_NAME):
        init_db()
    app.run(debug=True)