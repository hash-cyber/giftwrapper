from flask import Flask, render_template, request, redirect, session, make_response, jsonify, url_for
from config import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
import re
import json

app = Flask(__name__)
app.secret_key = "secret123"

# =========================
# 🔐 LOGIN
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        if conn is None:
            return "Database error"

        cursor = conn.cursor(pymysql.cursors.DictCursor)

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user:
            if check_password_hash(user['password'], password):
                session['user_id'] = user['user_id']
                session['user_name'] = user['name']
                session['role'] = user['role']

                response = make_response(redirect("/dashboard"))

                if 'remember' in request.form:
                    response.set_cookie("remember_user", str(user['user_id']), max_age=86400*30)

                if user['role'] == 'admin':
                    return redirect("/admin/dashboard")
                elif user['role'] == 'staff':
                    return redirect("/staff/dashboard")
                else:
                    return response
            else:
                error = "Invalid password"
        else:
            error = "User not found"

    return render_template("login.html", error=error)


# =========================
# 📝 REGISTER
# =========================
@app.route("/register", methods=["GET", "POST"])
def register():
    message = ""

    if request.method == "POST":
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        address = request.form['address']

        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            message = "Invalid email format!"

        elif not re.match(r"^[0-9]{10}$", phone):
            message = "Phone must be 10 digits!"

        else:
            conn = get_db_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            if cursor.fetchone():
                message = "Email already registered!"
            else:
                hashed_password = generate_password_hash(password)

                cursor.execute("""
                    INSERT INTO users (name, email, password, phone, address)
                    VALUES (%s, %s, %s, %s, %s)
                """, (name, email, hashed_password, phone, address))

                conn.commit()
                return redirect("/login")

            cursor.close()
            conn.close()

    return render_template("register.html", message=message)


# =========================
# 🏠 DASHBOARD
# =========================
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


# =========================
# 🛍 PRODUCTS
# =========================
@app.route("/products")
def products():
    return render_template("products.html")

@app.route("/check_unread")
def check_unread():

    if 'user_id' not in session:
        return jsonify({'count': 0})

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    cursor.execute("""
        SELECT COUNT(*) AS unread
        FROM messages
        WHERE user_id=%s
        AND sender='admin'
        AND is_read=0
    """, (session['user_id'],))

    data = cursor.fetchone()

    cursor.close()
    conn.close()

    return jsonify({'count': data['unread']})

# =========================
# 🛍 ADD TO CART (FIXED IMAGE PATHS)
# =========================
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():

    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Login required'})

    item_id = request.form.get('id')
    qty = int(request.form.get('quantity', 1))
    if qty < 1:
        qty = 1

    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # 🧠 AI HAMPER
    if item_id.startswith('ai_'):
        hamper_id = int(item_id.replace('ai_', ''))
        cursor.execute("SELECT * FROM hamper_templates WHERE id=%s", (hamper_id,))
        product = cursor.fetchone()
        if not product:
            return jsonify({'status': 'error', 'message': 'Hamper not found'})

        cart_key = f"ai_{hamper_id}"

        if cart_key in cart:
            cart[cart_key]['quantity'] = 1
        else:
            # Store only filename for AI images
            image_filename = product['image'].replace('img/templates/', '')
            cart[cart_key] = {
                'id': hamper_id,
                'hamper_id': hamper_id,
                'title': product['title'],
                'price': product['original_price'],
                'quantity': 1,
                'image': image_filename,
                'is_ai': 1,
                'source': 'ai_hamper',
                'items_json': product['items']
            }

    # 🛒 NORMAL PRODUCT
    else:
        product_id = int(item_id)
        cursor.execute("SELECT * FROM products WHERE id=%s", (product_id,))
        product = cursor.fetchone()
        if not product:
            return jsonify({'status': 'error', 'message': 'Product not found'})

        cart_key = str(product_id)

        if cart_key in cart:
            cart[cart_key]['quantity'] += qty
        else:
            # Store only filename for normal images
            image_filename = product['image'].replace('img/', '')
            cart[cart_key] = {
                'id': product_id,
                'title': product['title'],
                'price': float(product['price']),
                'quantity': qty,
                'image': image_filename,
                'is_ai': 0,
                'source': 'normal'
            }

    session['cart'] = cart
    cursor.close()
    conn.close()

    cart_count = sum(item['quantity'] for item in cart.values())

    return jsonify({
        'status': 'success',
        'message': 'Product added to cart',
        'cart_count': cart_count
    })


# =========================
# 🔄 UPDATE CART
# =========================
@app.route('/update_cart', methods=['POST'])
def update_cart():

    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Login required'})

    item_id = request.form.get('id')
    qty = int(request.form.get('quantity', 0))

    cart = session.get('cart', {})

    if qty <= 0:
        if item_id in cart:
            del cart[item_id]
    else:
        if item_id in cart:
            if cart[item_id].get('is_ai') == 1:
                cart[item_id]['quantity'] = 1
            else:
                cart[item_id]['quantity'] = qty

    session['cart'] = cart

    cart_count = sum(item['quantity'] for item in cart.values())

    return jsonify({
        'status': 'success',
        'cart_count': cart_count
    })

@app.route("/category")
def category():

    if 'user_id' not in session:
        return redirect("/login")

    conn = get_db_connection()
    if conn is None:
        return "Database error"

    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # 🔹 Pagination
    limit = 8
    page = int(request.args.get('page', 1))
    start = (page - 1) * limit

    # 🔹 Filters
    type_ = request.args.get('type', 'birthday')
    search = request.args.get('search', '')
    sort = request.args.get('sort', '')

    # 🔹 Sorting
    order = ""
    if sort == "low":
        order = " ORDER BY price ASC"
    elif sort == "high":
        order = " ORDER BY price DESC"

    # 🔹 Query
    if search:
        query = f"""
            SELECT * FROM products
            WHERE category=%s
            AND (title LIKE %s OR tags LIKE %s)
            {order}
            LIMIT %s,%s
        """
        values = (type_, f"%{search}%", f"%{search}%", start, limit)
    else:
        query = f"""
            SELECT * FROM products
            WHERE category=%s
            {order}
            LIMIT %s,%s
        """
        values = (type_, start, limit)

    cursor.execute(query, values)
    products = cursor.fetchall()

    # 🔹 Total count
    if search:
        cursor.execute("""
            SELECT COUNT(*) as total FROM products
            WHERE category=%s
            AND (title LIKE %s OR tags LIKE %s)
        """, (type_, f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("SELECT COUNT(*) as total FROM products WHERE category=%s", (type_,))

    total = cursor.fetchone()['total']
    total_pages = (total + limit - 1) // limit

    cursor.close()
    conn.close()

    return render_template(
        "category.html",
        products=products,
        type=type_,
        search=search,
        sort=sort,
        page=page,
        total_pages=total_pages
    )


@app.route("/product_details/<int:id>")
def product_details(id):

    if 'user_id' not in session:
        return redirect("/login")

    conn = get_db_connection()
    if conn is None:
        return "Database error"

    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # 🔹 Get product
    cursor.execute("SELECT * FROM products WHERE id=%s", (id,))
    product = cursor.fetchone()

    if not product:
        return "Product not found"

    # 🔹 Suggestions (related products)
    cursor.execute("""
        SELECT * FROM products 
        WHERE category=%s AND id!=%s 
        LIMIT 4
    """, (product['category'], id))

    suggestions = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "product_details.html",
        product=product,
        suggestions=suggestions
    )


# =========================
# 🧾 CART LIST
# =========================
@app.route("/cart_list")
def cart_list():

    if 'user_id' not in session:
        return "<p>Please login</p>"

    cart = session.get('cart', {})

    if not cart:
        return "<p style='padding:15px;text-align:center;color:#888'>Your cart is empty 💝</p>"

    total = 0
    html = "<ul style='list-style:none;padding:0;margin:0;'>"

    for key, item in cart.items():
        price = float(item.get('price', 0))
        qty = int(item.get('quantity', 1))
        subtotal = price * qty
        total += subtotal

        ai_tag = "<em>(AI)</em>" if item.get('is_ai') else ""

        # 🔹 FIX IMAGE PATHS
        if item.get('is_ai'):
            image_path = f"templates/{item.get('image').replace('img/templates/', '')}"
        else:
            image_path = f"{item.get('image').replace('img/', '')}"

        html += f"""
        <li style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #eee">
            <img src="/static/img/{image_path}" 
                 style="width:50px;height:50px;object-fit:cover;border-radius:6px;">
            <div style="flex:1;">
                <strong>{item.get('title')} {ai_tag}</strong><br>
                ₹{price} ×
                <input type="number" class="cart-qty"
                       data-id="{key}"
                       value="{qty}"
                       min="1"
                       style="width:50px;padding:2px;border-radius:6px;border:1px solid #ddd;">
                <br>
                <small>Subtotal: ₹{subtotal}</small>
            </div>
            <button class="cart-remove"
                    data-id="{key}"
                    style="background:#ff7f50;border:none;color:#fff;padding:5px 8px;border-radius:6px;cursor:pointer;">
                ✖
            </button>
        </li>
        """

    html += "</ul>"

    html += f"""
    <p style="text-align:right;font-weight:600;margin-top:10px;">
        Total: ₹{total}
    </p>
    <a href="/checkout"
       style="display:block;text-align:center;background:#ff7f50;color:white;
              padding:10px;border-radius:8px;text-decoration:none;margin-top:10px;">
       Proceed to Checkout
    </a>
    """

    # 🔹 JS FOR CART ACTIONS
    html += """
    <script>
    function loadCartDropdown(){
        fetch('/cart_list')
        .then(res => res.text())
        .then(html => {
            const dropdown = document.getElementById('cart-dropdown');
            dropdown.innerHTML = html;
            dropdown.style.display = 'block';
            attachCartEvents();
        });
    }

    function attachCartEvents(){
        document.querySelectorAll('.cart-qty').forEach(input=>{
            input.addEventListener('input', function(){
                const id = this.dataset.id;
                const qty = parseInt(this.value);
                fetch('/update_cart',{
                    method:'POST',
                    headers:{'Content-Type':'application/x-www-form-urlencoded'},
                    body:`id=${id}&quantity=${qty}`
                }).then(()=>loadCartDropdown());
            });
        });

        document.querySelectorAll('.cart-remove').forEach(btn=>{
            btn.addEventListener('click', function(){
                const id = this.dataset.id;
                fetch('/update_cart',{
                    method:'POST',
                    headers:{'Content-Type':'application/x-www-form-urlencoded'},
                    body:`id=${id}&quantity=0`
                }).then(()=>loadCartDropdown());
            });
        });
    }
    </script>
    """

    return html


# =====================
#  ai chat
#======================
@app.route("/ai_chat")
def ai_chat():

    if 'user_id' not in session:
        return redirect("/login")

    return render_template("ai_chat.html")


@app.route("/ai_chat_fetch", methods=["POST"])
def ai_chat_fetch():

    data = request.get_json()
    prompt = data.get("prompt", "").lower()

    import re

    # 🎯 Budget
    numbers = re.findall(r'\d+', prompt)
    min_price = 0
    max_price = 100000

    if len(numbers) == 1:
        max_price = int(numbers[0])
    elif len(numbers) >= 2:
        min_price = int(numbers[0])
        max_price = int(numbers[1])

    # 🎯 Occasion
    occasion = ""
    if "birthday" in prompt:
        occasion = "birthday"
    elif "anniversary" in prompt:
        occasion = "anniversary"
    elif "wedding" in prompt:
        occasion = "wedding"
    elif "corporate" in prompt:
        occasion = "corporate"

    # 🎯 Style
    style = ""
    if "luxury" in prompt:
        style = "luxury"
    elif "premium" in prompt:
        style = "premium"
    elif "cute" in prompt:
        style = "cute"
    elif "minimal" in prompt:
        style = "minimal"
    elif "corporate" in prompt:
        style = "corporate"

    # 🎯 Gender
    gender = ""
    if any(x in prompt for x in ["him", "male"]):
        gender = "male"
    elif any(x in prompt for x in ["her", "female", "girlfriend"]):
        gender = "female"
    elif any(x in prompt for x in ["kids", "baby"]):
        gender = "kids"
    elif "unisex" in prompt:
        gender = "unisex"

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    query = "SELECT * FROM hamper_templates WHERE 1=1"
    values = []

    query += " AND original_price BETWEEN %s AND %s"
    values += [min_price, max_price]

    # ✅ Occasion filter
    if occasion:
        query += " AND LOWER(occasion) LIKE %s"
        values.append(f"%{occasion}%")
    else:
        query += " AND LOWER(occasion) IN ('birthday','anniversary','wedding','corporate')"

    # ✅ Style filter
    if style:
        query += " AND LOWER(hamper_type) LIKE %s"
        values.append(f"%{style}%")

    # ✅ Gender filter
    if gender:
        query += " AND LOWER(gender) LIKE %s"
        values.append(f"%{gender}%")

    query += " ORDER BY RAND() LIMIT 1"

    cursor.execute(query, tuple(values))
    row = cursor.fetchone()

    if not row:
        return jsonify({"status": "error"})

    # 🎁 Fetch product names
    items = []
    import json

    ids = json.loads(row['items'])

    if ids:
        placeholders = ",".join(["%s"] * len(ids))
        cursor.execute(f"SELECT title FROM products WHERE id IN ({placeholders})", ids)
        items = [p['title'] for p in cursor.fetchall()]

    cursor.close()
    conn.close()

    return jsonify({
        "status": "success",
        "title": row['title'],
        "description": row['description'],
        "image": row['image'],
        "price": row['original_price'],
        "items": items,
        "id": row['id']
    })


#====================
#index page
#====================
@app.route("/")
def index():
    return render_template("index.html")   


#=====================
#About Us
#=====================
@app.route("/about")
def about():

    return render_template("about.html")


#=========================
#checkout
#=========================
@app.route('/checkout')
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Use cart safely
    cart_items = session.get('cart', {})

    items_total = 0

    # ✅ FIX: use .values() if cart is dict
    for item in cart_items.values():
        items_total += float(item['price']) * int(item['quantity'])

    # Charges (UNCHANGED)
    shipping_charge = 80 if items_total < 1000 else 0
    grand_total = items_total + shipping_charge

    return render_template(
        'checkout.html',
        cart_items=cart_items.values(),  # ✅ pass values to template
        items_total=items_total,
        shipping_charge=shipping_charge,
        grand_total=grand_total,
        custom_notes=session.get('custom_notes', '')
    )


#=======================
#Terms and Condition
#=======================
@app.route('/terms_condition')
def terms():
    return render_template('terms_condition.html')

#=========================
# Cancellation Policy
#=========================
@app.route('/cancellation_policy')
def cancellation_policy():
    return render_template('cancellation_policy.html')


#=========================
# Payment
#=========================
from flask import request, session, redirect, render_template, jsonify

@app.route('/payment', methods=['POST'])
def payment():
    # Ensure user logged in
    if 'user_id' not in session:
        return redirect('/login')

    # Check cart
    cart_items = session.get('cart', {})
    if not cart_items:
        return "<h2>Your cart is empty.</h2>"

    # Store custom notes
    session['custom_notes'] = request.form.get('custom_notes', '')

    # Calculate totals
    items_total = 0
    for item in cart_items.values():
        items_total += float(item['price']) * int(item['quantity'])

    shipping_charge = 80 if items_total < 1000 else 0
    grand_total = items_total + shipping_charge

    return render_template(
        'payment.html',
        grand_total=grand_total,
        custom_notes=session['custom_notes']
    )


#=========================
# Payment Process
#=========================
@app.route('/payment_process', methods=['POST'])
def payment_process():

    conn = get_db_connection()
    cursor = conn.cursor()

    # =========================
    # GET REQUIRED DATA
    # =========================
    payment_id   = request.form.get('payment_id')
    custom_notes = request.form.get('custom_notes')
    user_id      = session.get('user_id')
    cart_items   = session.get('cart', {})

    # =========================
    # VALIDATION
    # =========================
    if not payment_id or not user_id or not cart_items:
        return jsonify({
            'status': 'error',
            'message': 'Invalid session or payment'
        }), 400

    # =========================
    # CALCULATE TOTALS
    # =========================
    items_total = 0

    for key in cart_items:
        item = cart_items[key]

        item['quantity'] = int(item.get('quantity', 1))
        item['price']    = float(item.get('price', 0))

        items_total += item['price'] * item['quantity']

        # Ensure AI hamper has hamper_id
        if item.get('is_ai') == 1:
            if not item.get('hamper_id'):
                if item.get('id'):
                    item['hamper_id'] = int(item['id'])
                else:
                    return jsonify({
                        'status': 'error',
                        'message': f"AI hamper missing hamper_id for item: {item.get('title','Unknown')}"
                    }), 400
            else:
                item['hamper_id'] = int(item['hamper_id'])

    shipping_charge = 80 if items_total < 1000 else 0
    grand_total     = items_total + shipping_charge

    # =========================
    # INSERT ORDER
    # =========================
    order_sql = """
        INSERT INTO orders
        (user_id, amount, items_total, shipping_charge, custom_notes, payment_id, payment_status, order_status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'Success', 'Pending', NOW())
    """

    cursor.execute(order_sql, (
        user_id,
        grand_total,
        items_total,
        shipping_charge,
        custom_notes,
        payment_id
    ))

    order_id = cursor.lastrowid

    # =========================
    # INSERT ORDER ITEMS
    # =========================
    order_item_sql = """
        INSERT INTO order_items
        (order_id, product_id, hamper_id, is_ai, quantity, price, product_title, product_image, items_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    for key in cart_items:
        item = cart_items[key]

        is_ai = 1 if item.get('is_ai') == 1 else 0

        product_id = None if is_ai else item.get('id')
        hamper_id  = item.get('hamper_id') if is_ai else None

        items_json = ""

        # =========================
        # GET ITEMS FROM HAMPER TEMPLATE
        # =========================
        if hamper_id:
            cursor.execute("SELECT items FROM hamper_templates WHERE id = %s", (hamper_id,))
            row = cursor.fetchone()

            if row:
                items_json = row[0]

        cursor.execute(order_item_sql, (
            order_id,
            product_id,
            hamper_id,
            is_ai,
            item['quantity'],
            item['price'],
            item.get('title'),
            item.get('image'),
            items_json
        ))

    conn.commit()

    # =========================
    # FINALIZE
    # =========================
    session['transaction_id'] = payment_id
    session['payment_status'] = "Success"
    session['order_id']       = order_id

    session.pop('cart', None)
    session.pop('custom_notes', None)

    return jsonify({
        'status': 'success',
        'order_id': order_id,
        'amount': grand_total,
        'message': 'Payment processed successfully'
    })


#==========================
# PAYMENT SUCESS
#==========================
@app.route('/payment_success')
def payment_success():
    if 'payment_status' not in session:
        return redirect('/dashboard')

    order_id = request.args.get('order_id')
    transaction_id = session.get('transaction_id')

    session.pop('payment_status', None)
    session.pop('transaction_id', None)

    return render_template(
        'payment_success.html',
        transaction_id=transaction_id,
        order_id=order_id
    )


# =========================
# 🚪 LOGOUT
# =========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# =========================
# ▶️ RUN
# =========================
if __name__ == "__main__":
    app.run(port=8000, debug=True)