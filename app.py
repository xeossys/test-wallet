import os, json, sqlite3
from flask import Flask, render_template_string, request, jsonify, session
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

# =====================================================================
# PASTE YOUR CENTRAL MINT RED PUBLIC KEY HERE
ADMIN_PUBKEY = "8ec94ddd8b99e3efdc85bc264d615782481bdaa810b945c1ce06291b6da43531"
# =====================================================================

DB_PATH = "xeos_enterprise.db"
app = Flask(__name__)
# Secret key for secure browser sessions (keeps users logged in)
app.secret_key = os.urandom(24)

# 1. DATABASE INITIALIZATION
def setup_db():
    conn = sqlite3.connect(DB_PATH)
    # Users table: maps @usernames to their cryptographic keys
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                    (username TEXT PRIMARY KEY, address TEXT, private_key TEXT)''')
    # The Immutable Blockchain Ledger
    conn.execute('''CREATE TABLE IF NOT EXISTS chain 
                    (signature TEXT PRIMARY KEY, manifest TEXT)''')
    conn.commit(); conn.close()

setup_db()

# 2. THE BLOCKCHAIN CONSENSUS ENGINE
def get_network_balances():
    balances = {}
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT manifest FROM chain ORDER BY ROWID").fetchall()
    conn.close()

    for row in rows:
        try:
            tx = json.loads(row[0])
            payload, sig, tx_type = tx["payload"], tx["signature"], tx.get("type", "TRANSFER")
            amt = int(payload["amount"])
            serialized = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')

            if tx_type == "BOND":
                if tx.get("authority", "").lower() != ADMIN_PUBKEY.lower(): continue
                try:
                    ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(ADMIN_PUBKEY)).verify(bytes.fromhex(sig), serialized)
                    balances[payload["recipient"].lower()] = balances.get(payload["recipient"].lower(), 0) + amt
                except: continue

            elif tx_type == "TRANSFER":
                sender, recipient = payload["sender"].lower(), payload["recipient"].lower()
                try:
                    ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(sender)).verify(bytes.fromhex(sig), serialized)
                    if balances.get(sender, 0) >= amt:
                        balances[sender] -= amt
                        balances[recipient] = balances.get(recipient, 0) + amt
                except: continue
        except: continue
    return balances

# 3.FRONTEND (HTML/JS)
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XEOS Enterprise Network</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #030305; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .glass-card { background: rgba(20, 15, 35, 0.7); backdrop-filter: blur(20px); border: 1px solid rgba(163, 112, 247, 0.2); border-radius: 20px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5); }
        .neon-text { color: #a370f7; text-shadow: 0 0 15px rgba(163, 112, 247, 0.6); }
        .btn-primary { background: linear-gradient(135deg, #7c52ed 0%, #5b3ab3 100%); transition: all 0.2s; }
        .btn-primary:hover { opacity: 0.9; transform: translateY(-2px); box-shadow: 0 10px 20px -10px rgba(124, 82, 237, 0.6); }
        input, textarea { background: rgba(0,0,0,0.4); border: 1px solid rgba(255,255,255,0.08); color: #fff; outline: none; width: 100%; padding: 14px; border-radius: 10px; margin-top: 6px; transition: border 0.2s; }
        input:focus, textarea:focus { border-color: #a370f7; }
        .sync-dot { height: 8px; width: 8px; background-color: #10b981; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px #10b981; animation: pulse 2s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
    </style>
</head>
<body class="min-h-screen flex items-center justify-center p-4 bg-[url('https://www.transparenttextures.com/patterns/stardust.png')]">
    
    <!-- AUTHENTICATION SCREEN -->
    <div id="auth-screen" class="glass-card w-full max-w-md p-8 space-y-6 {{ 'hidden' if session.get('username') else '' }}">
        <div class="text-center">
            <h1 class="text-3xl font-bold tracking-tighter">XEOS <span class="neon-text">Network</span></h1>
            <p class="text-gray-400 text-sm mt-2">Enterprise Decentralized Ledger</p>
        </div>
        <div class="space-y-4">
            <div>
                <label class="text-xs text-gray-400 font-semibold tracking-wider">CHOOSE USERNAME</label>
                <input id="auth-user" placeholder="e.g. @xeosdev">
            </div>
            <button onclick="authenticate()" class="btn-primary w-full py-4 rounded-xl font-bold tracking-wide">Enter Network</button>
        </div>
    </div>

    <!-- MAIN WALLET SCREEN -->
    <div id="wallet-screen" class="glass-card w-full max-w-md p-8 space-y-8 {{ '' if session.get('username') else 'hidden' }}">
        <div class="text-center space-y-2 relative">
            <div class="absolute top-0 right-0 flex items-center space-x-2 text-xs text-gray-500 font-medium tracking-wide">
                <span class="sync-dot"></span> <span>Global Sync</span>
            </div>
            <p class="text-gray-400 text-sm tracking-widest uppercase font-semibold">@<span id="display-user">{{ session.get('username') }}</span>'s Portfolio</p>
            <h1 class="text-6xl font-black tracking-tighter py-2"><span id="bal" class="neon-text">0</span> <span class="text-2xl text-gray-500 font-bold">XEOS</span></h1>
            <p class="text-xs text-gray-500 truncate mt-2 cursor-pointer hover:text-white bg-black/30 p-2 rounded-lg" onclick="navigator.clipboard.writeText('{{ session.get('address') }}'); alert('Address Copied!');">
                <span class="text-gray-400 font-bold">Address:</span> {{ session.get('address') }}
            </p>
            <button onclick="logout()" class="text-xs text-red-400 hover:text-red-300 underline mt-2">Secure Logout</button>
        </div>

        <div class="flex space-x-2 bg-black/40 p-1.5 rounded-xl">
            <button onclick="tab('send')" class="flex-1 py-2.5 rounded-lg bg-gray-800/60 font-semibold text-sm transition-all" id="t-send">Send Funds</button>
            <button onclick="tab('claim')" class="flex-1 py-2.5 rounded-lg text-gray-400 hover:text-white font-semibold text-sm transition-all" id="t-claim">Claim Bond</button>
        </div>

        <div id="v-send" class="space-y-4">
            <div>
                <label class="text-xs text-gray-400 font-semibold tracking-wider">RECIPIENT (@USERNAME OR ADDRESS)</label>
                <input id="dest" placeholder="e.g. @avishek or 64-char address">
            </div>
            <div>
                <label class="text-xs text-gray-400 font-semibold tracking-wider">AMOUNT TO SEND</label>
                <input id="amt" type="number" placeholder="0">
            </div>
            <button onclick="send()" class="btn-primary w-full py-4 rounded-xl font-bold tracking-wide mt-2">Sign & Broadcast</button>
            <textarea id="out-code" class="h-24 hidden text-xs font-mono" readonly></textarea>
        </div>

        <div id="v-claim" class="space-y-4 hidden">
            <div>
                <label class="text-xs text-gray-400 font-semibold tracking-wider">CRYPTOGRAPHIC MANIFEST</label>
                <textarea id="manifest" class="h-32 text-xs font-mono" placeholder="Paste JSON Bond or Transfer here..."></textarea>
            </div>
            <button onclick="claim()" class="btn-primary w-full py-4 rounded-xl font-bold tracking-wide">Verify Cryptography</button>
        </div>
    </div>

    <script>
        // UI Navigation
        function tab(t) {
            document.getElementById('v-send').classList.toggle('hidden', t !== 'send');
            document.getElementById('v-claim').classList.toggle('hidden', t !== 'claim');
            document.getElementById('t-send').classList.toggle('bg-gray-800/60', t === 'send');
            document.getElementById('t-send').classList.toggle('text-gray-400', t !== 'send');
            document.getElementById('t-claim').classList.toggle('bg-gray-800/60', t === 'claim');
            document.getElementById('t-claim').classList.toggle('text-gray-400', t !== 'claim');
        }

        // Auth Logic
        async function authenticate() {
            let user = document.getElementById('auth-user').value.trim();
            if(!user) return alert("Please enter a username.");
            if(user.startsWith('@')) user = user.substring(1);
            
            let r = await fetch('/api/auth', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: user.toLowerCase()})});
            let d = await r.json();
            if(d.success) window.location.reload();
            else alert(d.error);
        }

        async function logout() {
            await fetch('/api/logout');
            window.location.reload();
        }

        // Wallet Logic
        async function fetchBal() {
            try {
                let r = await fetch('/api/state'); 
                document.getElementById('bal').innerText = (await r.json()).balance;
            } catch(e) {}
        }

        async function send() {
            let dest = document.getElementById('dest').value.trim();
            let amt = parseInt(document.getElementById('amt').value);
            if(!dest || isNaN(amt) || amt <= 0) return alert("Invalid amount or destination.");

            let r = await fetch('/api/send', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({dest: dest, amount: amt})});
            let d = await r.json(); 
            if(d.error) return alert(d.error);
            
            document.getElementById('out-code').value = JSON.stringify(d.manifest); 
            document.getElementById('out-code').classList.remove('hidden');
            alert("Transfer generated! You can send this JSON code to the recipient, or they can claim it directly if you broadcasted it to their address.");
        }

        async function claim() {
            let r = await fetch('/api/claim', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({manifest:document.getElementById('manifest').value})});
            let d = await r.json(); 
            alert(d.error ? "REJECTED: " + d.error : "SUCCESS: " + d.message); 
            fetchBal(); 
            document.getElementById('manifest').value = '';
        }
        
        // Polling if logged in
        if (document.getElementById('wallet-screen').classList.contains('hidden') === false) {
            fetchBal();
            setInterval(fetchBal, 2500);
        }
    </script>
</body>
</html>
"""

# 4. API & ROUTING
@app.route('/')
def index(): 
    return render_template_string(HTML)

@app.route('/api/auth', methods=['POST'])
def auth():
    username = request.json.get('username', '').strip().lower()
    if not username or not username.isalnum(): return jsonify({"error": "Invalid username format. Letters/numbers only."}), 400
    
    conn = sqlite3.connect(DB_PATH)
    user = conn.execute("SELECT address FROM users WHERE username = ?", (username,)).fetchone()
    
    if not user:
        # Create new wallet for new user
        key = ed25519.Ed25519PrivateKey.generate()
        priv_hex = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).hex()
        pub_hex = key.public_key().public_bytes_raw().hex()
        conn.execute("INSERT INTO users (username, address, private_key) VALUES (?, ?, ?)", (username, pub_hex, priv_hex))
        conn.commit()
        address = pub_hex
    else:
        address = user[0]
        
    conn.close()
    session['username'] = username
    session['address'] = address
    return jsonify({"success": True})

@app.route('/api/logout')
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route('/api/state')
def state():
    if 'address' not in session: return jsonify({"error": "Unauthorized"}), 401
    balances = get_network_balances()
    return jsonify({"balance": balances.get(session['address'].lower(), 0)})

@app.route('/api/send', methods=['POST'])
def send_funds():
    if 'address' not in session: return jsonify({"error": "Unauthorized"}), 401
    req = request.json
    try: amount = int(req['amount'])
    except: return jsonify({"error": "Invalid amount format."}), 400
    
    dest_input = req['dest'].lower().strip()
    conn = sqlite3.connect(DB_PATH)
    
    # Username Resolution System (@username to 64-char address)
    if dest_input.startswith('@'):
        target_user = conn.execute("SELECT address FROM users WHERE username = ?", (dest_input[1:],)).fetchone()
        if not target_user: conn.close(); return jsonify({"error": "User not found on the network."}), 404
        recipient_addr = target_user[0]
    else:
        recipient_addr = dest_input
        if len(recipient_addr) != 64: conn.close(); return jsonify({"error": "Invalid address format"}), 400

    # Fetch User's Private Key from secure DB
    user_data = conn.execute("SELECT private_key FROM users WHERE username = ?", (session['username'],)).fetchone()
    conn.close()
    
    wallet_key = serialization.load_pem_private_key(bytes.fromhex(user_data[0]), password=None)
    
    balances = get_network_balances()
    if balances.get(session['address'].lower(), 0) < amount: 
        return jsonify({"error": "Insufficient network balance!"}), 400

    payload = {"amount": amount, "nonce": os.urandom(8).hex(), "recipient": recipient_addr, "sender": session['address']}
    serialized = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    sig = wallet_key.sign(serialized).hex()
    
    manifest = {"type": "TRANSFER", "payload": payload, "signature": sig}
    

    # conn = sqlite3.connect(DB_PATH)
    # conn.execute("INSERT OR IGNORE INTO chain (signature, manifest) VALUES (?, ?)", (sig, json.dumps(manifest)))
    # conn.commit(); conn.close()

    return jsonify({"manifest": manifest})

@app.route('/api/claim', methods=['POST'])
def claim():
    if 'address' not in session: return jsonify({"error": "Unauthorized"}), 401
    try:
        tx = json.loads(request.json['manifest'])
        sig = tx["signature"]
    except: return jsonify({"error": "Corrupted JSON format."}), 400

    conn = sqlite3.connect(DB_PATH)
    if conn.execute("SELECT 1 FROM chain WHERE signature = ?", (sig,)).fetchone():
        conn.close(); return jsonify({"error": "Replay Attack Blocked: Code already on the blockchain."}), 400

    # Verify math before adding to DB
    payload = tx["payload"]
    tx_type = tx.get("type", "TRANSFER")
    serialized = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')

    try:
        if tx_type == "BOND":
            if tx.get("authority", "").lower() != ADMIN_PUBKEY.lower(): raise Exception("Admin Key mismatch.")
            if payload["recipient"].lower() != session['address'].lower(): raise Exception("Bond is addressed to a different wallet.")
            ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(ADMIN_PUBKEY)).verify(bytes.fromhex(sig), serialized)
        elif tx_type == "TRANSFER":
            if payload["recipient"].lower() != session['address'].lower(): raise Exception("Transfer is addressed to a different wallet.")
            ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload["sender"])).verify(bytes.fromhex(sig), serialized)
    except Exception as e:
        conn.close(); return jsonify({"error": str(e) or "Cryptographic Verification Failed."}), 400

    try:
        conn.execute("INSERT INTO chain (signature, manifest) VALUES (?, ?)", (sig, json.dumps(tx)))
        conn.commit()
    except:
        conn.close(); return jsonify({"error": "Failed to write to blockchain."}), 500
        
    conn.close()
    return jsonify({"message": f"Transaction permanently written to the global ledger!"})

if __name__ == '__main__':
    # Uses environment PORT for Cloud hosts (Render/Railway/Heroku)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
