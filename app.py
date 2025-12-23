import os
import json
import datetime
from flask import Flask, render_template, request, jsonify, redirect, session, url_for, flash
import firebase_admin
from firebase_admin import credentials, firestore, auth

app = Flask(__name__)
# Change this to a random random string for production security
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_key_8823_secure")

# --- FIREBASE INITIALIZATION ---
# This block allows the code to work on both Local (using file) and Render (using Env Var)
if not firebase_admin._apps:
    # Check if we are on Render (Production)
    if os.environ.get('FIREBASE_CREDENTIALS'):
        cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
        cred = credentials.Certificate(cred_dict)
    # Fallback to Local Development
    else:
        if os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
        else:
            print("Warning: No Firebase credentials found. Database features may fail.")
            cred = None
            
    if cred:
        firebase_admin.initialize_app(cred)

db = firestore.client() if firebase_admin._apps else None

# --- WEB ROUTES ---

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html') # Show the Login/Landing page

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # The Frontend (Google Button) sends the EMAIL here to create a Flask session.
        user_email = request.form.get('email')
        
        if user_email:
            session['user_id'] = user_email
            return redirect(url_for('dashboard'))
        else:
            flash("Login failed. No email received.", "danger")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    points = 0
    transactions = []
    
    if db:
        # Check if user exists in Firestore database
        user_ref = db.collection('users').document(user_id)
        doc = user_ref.get()
        
        if doc.exists:
            points = doc.to_dict().get('points', 0)
        else:
            # First time setup: If they just logged in with Google for the first time
            user_ref.set({
                "points": 0,
                "created_at": datetime.datetime.now()
            })
            
        # Fetch History
        try:
            history_ref = db.collection('history').where('user_id', '==', user_id).order_by('timestamp', direction=firestore.Query.DESCENDING).limit(10)
            for h in history_ref.stream():
                transactions.append(h.to_dict())
        except Exception as e:
            print(f"History Error: {e}")

    return render_template('dashboard.html', user_id=user_id, points=points, transactions=transactions)

# --- INFO PAGES ---

@app.route('/why')
def why_revend():
    return render_template('why.html')

@app.route('/map')
def machine_map():
    return render_template('map.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        # In a real app, you would send an email here
        flash("Message sent successfully! We will contact you soon.", "success")
        return redirect(url_for('contact'))
    return render_template('contact.html')

@app.route('/admin')
def admin_panel():
    all_transactions = []
    if db:
        try:
            # Log limit set to 1000 as requested
            history_ref = db.collection('history').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1000)
            for h in history_ref.stream():
                all_transactions.append(h.to_dict())
        except Exception as e:
            print(f"Admin Error: {e}")
            
    return render_template('admin.html', transactions=all_transactions)

# --- MACHINE API ROUTES ---
# The Raspberry Pi sends data here

@app.route('/api/deposit', methods=['POST'])
def deposit():
    try:
        data = request.json
        secret = data.get('machine_secret')
        
        # Verify it's actually your machine
        if secret != os.environ.get("MACHINE_SECRET", "my_rvm_secret_123"):
            return jsonify({"status": "error", "message": "Unauthorized Machine"}), 403

        user_id = data.get('user_id') # This will now be the EMAIL address
        item_type = data.get('item_type', 'bottle')
        count = int(data.get('count', 1))
        
        # Point Logic: 10 pts for plastic, 20 for metal
        points_per_item = 20 if item_type == 'can' else 10
        total_points = points_per_item * count
        
        if db:
            user_ref = db.collection('users').document(user_id)
            
            # Update Database Atomically
            if user_ref.get().exists:
                user_ref.update({
                    "points": firestore.Increment(total_points),
                    "last_active": datetime.datetime.now()
                })
            else:
                user_ref.set({
                    "points": total_points,
                    "created_at": datetime.datetime.now()
                })
            
            # Log the Deposit
            db.collection('history').add({
                "user_id": user_id,
                "type": "deposit",
                "description": f"Deposited {count} {item_type}(s)",
                "points": total_points,
                "timestamp": datetime.datetime.now()
            })
            
        return jsonify({"status": "success", "added_points": total_points, "user": user_id})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/redeem', methods=['POST'])
def redeem():
    try:
        data = request.json
        user_id = data.get('user_id')
        cost = int(data.get('cost'))
        reward_name = data.get('reward_name')
        
        if db:
            user_ref = db.collection('users').document(user_id)
            doc = user_ref.get()
            
            if not doc.exists:
                return jsonify({"status": "error", "message": "User not found"}), 404
                
            current_points = doc.to_dict().get('points', 0)
            
            if current_points < cost:
                return jsonify({"status": "error", "message": "Insufficient points"}), 400
                
            # Deduct points
            user_ref.update({
                "points": firestore.Increment(-cost)
            })
            
            # Log the Redemption
            db.collection('history').add({
                "user_id": user_id,
                "type": "redemption",
                "description": f"Redeemed: {reward_name}",
                "points": -cost,
                "timestamp": datetime.datetime.now()
            })
            
            return jsonify({"status": "success", "new_balance": current_points - cost})
        else:
             return jsonify({"status": "error", "message": "Database disconnected"}), 500

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)