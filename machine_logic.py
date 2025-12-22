import requests
import time
import keyboard  # pip install keyboard

# --- CONFIGURATION ---
SERVER_URL = "https://rvm-rewards-api.onrender.com/api/deposit"
MACHINE_SECRET = "my_rvm_secret_123"

current_user_id = None

def login():
    global current_user_id
    print("\n--- NEW SESSION ---")
    # In a real machine, this would be typed on a physical numpad
    current_user_id = input("🔢 Please Enter User ID to Start: ")
    print(f"✅ Welcome, User {current_user_id}! System Ready.")
    print("   (Press SPACE for Bottle, C for Can, ESC to Logout)")

def send_deposit(item_type="bottle"):
    if not current_user_id:
        print("⚠️  Please login first!")
        return

    print(f"🔄 Detected {item_type}... Sending to cloud...")
    
    payload = {
        "user_id": current_user_id,
        "count": 1,
        "item_type": item_type,
        "machine_secret": MACHINE_SECRET
    }
    
    try:
        # Use a timeout so the machine doesn't freeze if internet is bad
        response = requests.post(SERVER_URL, json=payload, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"💰 Success! Added points. Total Balance: {data.get('new_total_points', 'Updated')}")
        else:
            print(f"❌ Server Error: {response.text}")
            
    except Exception as e:
        print(f"⚠️  Internet Error: {e}")

# --- MAIN LOOP ---
login() # Ask for ID immediately on startup

while True:
    try:
        if keyboard.is_pressed('space'):
            send_deposit("bottle")
            time.sleep(1) # Wait 1 sec so it doesn't count 10 times for one press
            
        if keyboard.is_pressed('c'):
            send_deposit("can")
            time.sleep(1)
            
        if keyboard.is_pressed('esc'):
            print("👋 Logging out...")
            time.sleep(1)
            login() # Restart session for the next person
            
    except Exception as e:
        pass # Ignore keyboard errors