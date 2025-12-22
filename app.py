import os
import json
import datetime
from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import firebase_admin
from firebase_admin import credentials, firestore

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
            raise FileNotFoundError("Could not find serviceAccountKey.json or FIREBASE_CREDENTIALS env var.")
            
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- WEB ROUTES ---

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Simple ID-based login. 
        # In a real app, integrate Firebase Auth SDK on frontend for passwords/OTP.
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
    user_ref = db.collection('users').document(user_id)
    doc = user_ref.get()
    
    user_data = doc.to_dict() if doc.exists else {}
    points = user_data.get('points', 0)
    
    # Fetch Recent Transactions (Optional: Create a subcollection for history)
    # This is just a placeholder for now
    history = [] 
    
    return render_template('dashboard.html', user_id=user_id, points=points)

# --- MACHINE API ROUTES ---
# Your RVM machine sends data here

@app.route('/api/deposit', methods=['POST'])
def deposit():
    try:
        data = request.json
        secret = data.get('machine_secret')
        
        # Verify it's actually your machine
        if secret != os.environ.get("MACHINE_SECRET", "my_rvm_secret_123"):
            return jsonify({"status": "error", "message": "Unauthorized Machine"}), 403

        user_id = data.get('user_id')
        item_type = data.get('item_type', 'bottle')
        count = int(data.get('count', 1))
        
        # Point Logic: 10 pts for plastic, 20 for metal
        points_per_item = 20 if item_type == 'can' else 10
        total_points = points_per_item * count
        
        # Update Database Atomically
        user_ref = db.collection('users').document(user_id)
        
        # Use Firestore Increment to prevent race conditions
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
            
        return jsonify({"status": "success", "added_points": total_points, "user": user_id})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)