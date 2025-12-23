import os
import json
import datetime
from flask import Flask, render_template, request, jsonify, redirect, session, url_for, flash
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)
# Change this to a random random string for production security
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_key_8823_secure")

# --- FIREBASE INITIALIZATION ---
if not firebase_admin._apps:
    if os.environ.get('FIREBASE_CREDENTIALS'):
        cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
        cred = credentials.Certificate(cred_dict)
    else:
        if os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
        else:
            # Fallback for local testing if file missing (optional)
            print("Warning: No Firebase credentials found.")
            cred = None
            
    if cred:
        firebase_admin.initialize_app(cred)

db = firestore.client() if firebase_admin._apps else None

# --- WEB ROUTES ---

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form.get('phone_number')
        if user_id:
            session['user_id'] = user_id
            return redirect(url_for('dashboard'))
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
    
    # Fetch User Data
    points = 0
    if db:
        user_ref = db.collection('users').document(user_id)
        doc = user_ref.get()
        if doc.exists:
            points = doc.to_dict().get('points', 0)
    
    # Fetch Recent Transactions
    transactions = []
    if db:
        try:
            history_ref = db.collection('history').where('user_id', '==', user_id).order_by('timestamp', direction=firestore.Query.DESCENDING).limit(10)
            history_docs = history_ref.stream()
            for h in history_docs:
                transactions.append(h.to_dict())
        except Exception as e:
            print(f"Error fetching history: {e}")

    return render_template('dashboard.html', user_id=user_id, points=points, transactions=transactions)

# --- NEW ROUTES (Why, Contact, Map) ---

@app.route('/why')
def why_revend():
    return render_template('why.html')

@app.route('/map')
def machine_map():
    return render_template('map.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        
        # In a real app, you would send an email here using SMTP
        # For now, we will log it to Firebase so you can read it
        if db:
            db.collection('messages').add({
                "name": name,
                "email": email,
                "message": message,
                "timestamp": datetime.datetime.now()
            })
        
        flash("Message sent successfully! We will contact you soon.", "success")
        return redirect(url_for('contact'))
        
    return render_template('contact.html')

@app.route('/admin')
def admin_panel():
    all_transactions = []
    if db:
        try:
            history_ref = db.collection('history').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1000)
            history_docs = history_ref.stream()
            for h in history_docs:
                all_transactions.append(h.to_dict())
        except Exception as e:
            print(f"Error fetching admin history: {e}")
            
    return render_template('admin.html', transactions=all_transactions)

# --- API ROUTES ---

@app.route('/api/deposit', methods=['POST'])
def deposit():
    try:
        data = request.json
        secret = data.get('machine_secret')
        
        if secret != os.environ.get("MACHINE_SECRET", "my_rvm_secret_123"):
            return jsonify({"status": "error", "message": "Unauthorized Machine"}), 403

        user_id = data.get('user_id')
        item_type = data.get('item_type', 'bottle')
        count = int(data.get('count', 1))
        
        points_per_item = 20 if item_type == 'can' else 10
        total_points = points_per_item * count
        
        if db:
            user_ref = db.collection('users').document(user_id)
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
                
            user_ref.update({
                "points": firestore.Increment(-cost)
            })
            
            db.collection('history').add({
                "user_id": user_id,
                "type": "redemption",
                "description": f"Redeemed: {reward_name}",
                "points": -cost,
                "timestamp": datetime.datetime.now()
            })
            
            return jsonify({"status": "success", "new_balance": current_points - cost})
        else:
             return jsonify({"status": "error", "message": "Database not connected"}), 500

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)