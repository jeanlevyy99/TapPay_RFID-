from flask import Flask, jsonify, render_template, request
import sqlite3, threading, time
from pathlib import Path
try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / 'rfid_shop.db'
app = Flask(__name__)
lock = threading.RLock()
state = {'serial': None, 'connected': False, 'port': '', 'last_uid': '', 'last_scan_at': 0, 'message': 'Connect the Arduino to begin.', 'result': None}

PRODUCTS = [
 {'id':'p1','name':'Notebook','category':'Stationery','price':80,'image':'https://images.unsplash.com/photo-1531346878377-a5be20888e57?auto=format&fit=crop&w=500&q=80'},
 {'id':'p2','name':'Pen Set','category':'Stationery','price':60,'image':'https://images.unsplash.com/photo-1583485088034-697b5bc54ccd?auto=format&fit=crop&w=500&q=80'},
 {'id':'p3','name':'Headphones','category':'Electronics','price':650,'image':'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=500&q=80'},
 {'id':'p4','name':'USB Drive','category':'Electronics','price':350,'image':'https://images.unsplash.com/photo-1618410320928-25228d811631?auto=format&fit=crop&w=500&q=80'},
 {'id':'p5','name':'Water Bottle','category':'Accessories','price':180,'image':'https://images.unsplash.com/photo-1602143407151-7111542de6e8?auto=format&fit=crop&w=500&q=80'},
 {'id':'p6','name':'Backpack','category':'Accessories','price':900,'image':'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?auto=format&fit=crop&w=500&q=80'},
 {'id':'p7','name':'Juice','category':'Food & Drinks','price':50,'image':'https://images.unsplash.com/photo-1600271886742-f049cd451bba?auto=format&fit=crop&w=500&q=80'},
 {'id':'p8','name':'Snack Pack','category':'Food & Drinks','price':40,'image':'https://images.unsplash.com/photo-1621939514649-280e2aa2f3a0?auto=format&fit=crop&w=500&q=80'},
]

def db():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con

def init_db():
    with db() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL, initial_balance INTEGER NOT NULL CHECK(initial_balance >= 0),
            balance INTEGER NOT NULL CHECK(balance >= 0), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        con.execute('''CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
            student_name TEXT NOT NULL, uid TEXT NOT NULL, items_json TEXT NOT NULL,
            total INTEGER NOT NULL CHECK(total >= 0), balance_after INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id))''')

def student_for_uid(uid):
    with db() as con:
        row = con.execute('SELECT id, uid, name, initial_balance, balance FROM students WHERE uid=?', (uid,)).fetchone()
        return dict(row) if row else None

def serial_reader(port, baud=9600):
    if serial is None:
        state.update(connected=False, message='pyserial is not installed. Run pip install -r requirements.txt.')
        return
    try:
        ser = serial.Serial(port, baud, timeout=1, write_timeout=1)
        time.sleep(2)
        with lock:
            old = state.get('serial')
            if old:
                try: old.close()
                except Exception: pass
            state.update(serial=ser, connected=True, port=port, message=f'Connected to {port}. Tap a card.', result=None)
        while True:
            if not ser.is_open: break
            try: line = ser.readline().decode('utf-8', errors='ignore').strip()
            except Exception as e:
                state.update(connected=False, message=f'Serial connection lost: {e}')
                break
            if line.startswith('CARD:'):
                uid = ''.join(ch for ch in line[5:].upper() if ch in '0123456789ABCDEF')
                if uid:
                    state.update(last_uid=uid, last_scan_at=time.time(), message=f'Card detected: {uid}', result=None)
            elif line == 'READY':
                state.update(message='Arduino ready. Tap a card.')
    except Exception as e:
        state.update(connected=False, message=f'Could not connect to {port}: {e}', port=port)
    finally:
        with lock:
            ser_now = state.get('serial')
            if ser_now and getattr(ser_now, 'is_open', False):
                try: ser_now.close()
                except Exception: pass
            state.update(serial=None, connected=False)

def send_hardware(command):
    ser = state.get('serial')
    if ser and getattr(ser, 'is_open', False):
        try:
            ser.write((command+'\n').encode())
            return True
        except Exception:
            return False
    return False

@app.get('/')
def index():
    return render_template('index.html', products=PRODUCTS)

@app.get('/api/ports')
def ports():
    available = []
    if list_ports:
        available = [{'device': p.device, 'description': p.description} for p in list_ports.comports()]
    return jsonify(ports=available, connected=state['connected'], port=state['port'])

@app.post('/api/connect')
def connect():
    port = (request.json or {}).get('port','').strip()
    if not port: return jsonify(ok=False, error='Choose or enter a serial port.'), 400
    if serial is None: return jsonify(ok=False, error='Install dependencies with pip install -r requirements.txt.'), 400
    if state.get('connected'): return jsonify(ok=True, message=f'Already connected to {state["port"]}.')
    threading.Thread(target=serial_reader, args=(port,), daemon=True).start()
    return jsonify(ok=True, message=f'Connecting to {port}…')

@app.get('/api/status')
def status():
    uid = state['last_uid']
    student = student_for_uid(uid) if uid else None
    return jsonify(connected=state['connected'], port=state['port'], last_uid=uid,
                   last_scan_at=state['last_scan_at'], message=state['message'], result=state['result'], student=student)

@app.post('/api/register')
def register():
    data = request.get_json(silent=True) or {}
    uid = state['last_uid']
    if not uid or time.time() - state['last_scan_at'] > 180:
        return jsonify(ok=False, error='Tap the card on the RFID reader first. No recent physical scan was detected.'), 400
    name = str(data.get('name','')).strip()
    try:
        balance = int(data.get('balance'))
        if balance < 0: raise ValueError()
    except (TypeError, ValueError):
        return jsonify(ok=False, error='Initial balance must be a non-negative whole number of rupees.'), 400
    if not name: return jsonify(ok=False, error='Enter the student name.'), 400
    try:
        with db() as con:
            con.execute('INSERT INTO students(uid,name,initial_balance,balance) VALUES(?,?,?,?)', (uid,name,balance,balance))
    except sqlite3.IntegrityError:
        return jsonify(ok=False, error=f'Card {uid} is already registered. Duplicate registration was blocked.'), 409
    student = student_for_uid(uid)
    state.update(message=f'{name} registered successfully.', result='registered')
    return jsonify(ok=True, student=student, message='Card registered successfully.')

@app.post('/api/pay')
def pay():
    data = request.get_json(silent=True) or {}
    uid = state['last_uid']
    if not uid or time.time() - state['last_scan_at'] > 180:
        return jsonify(ok=False, error='Tap the card on the reader first.'), 400
    items = data.get('items')
    if not isinstance(items, list) or not items:
        return jsonify(ok=False, error='Your cart is empty.'), 400
    catalog = {p['id']:p for p in PRODUCTS}
    clean_items, total = [], 0
    for item in items:
        pid = str(item.get('id',''))
        try: qty = int(item.get('qty',0))
        except (ValueError, TypeError): qty = 0
        if pid not in catalog or qty < 1 or qty > 99:
            return jsonify(ok=False, error='Invalid product or quantity in cart.'), 400
        product = catalog[pid]
        line_total = product['price'] * qty
        total += line_total
        clean_items.append({'id':pid,'name':product['name'],'qty':qty,'unit_price':product['price'],'line_total':line_total})
    with lock:
        con = db()
        try:
            con.execute('BEGIN IMMEDIATE')
            student = con.execute('SELECT * FROM students WHERE uid=?', (uid,)).fetchone()
            if not student:
                con.rollback(); send_hardware('DECLINED')
                state.update(message='Payment declined: card is not registered.', result='declined')
                return jsonify(ok=False, error='This card is not registered. Ask the administrator to register it first.'), 404
            if student['balance'] < total:
                con.rollback(); send_hardware('DECLINED')
                state.update(message='Payment declined: insufficient balance.', result='declined')
                return jsonify(ok=False, error=f'Insufficient balance. Available ₹{student["balance"]}; required ₹{total}.'), 400
            new_balance = student['balance'] - total
            import json
            con.execute('UPDATE students SET balance=? WHERE id=?', (new_balance, student['id']))
            con.execute('INSERT INTO transactions(student_id,student_name,uid,items_json,total,balance_after) VALUES(?,?,?,?,?,?)',
                        (student['id'],student['name'],uid,json.dumps(clean_items),total,new_balance))
            con.commit()
            send_hardware('APPROVED')
            state.update(message=f'Payment approved for {student["name"]}: ₹{total}.', result='approved')
            return jsonify(ok=True, message='Payment approved.', student={'name':student['name'],'uid':uid,'balance':new_balance}, total=total, items=clean_items)
        except Exception as e:
            con.rollback()
            return jsonify(ok=False, error=f'Payment could not be completed: {e}'), 500
        finally:
            con.close()

@app.get('/api/students')
def students():
    with db() as con:
        rows = con.execute('SELECT id,uid,name,initial_balance,balance,created_at FROM students ORDER BY id DESC').fetchall()
    return jsonify(students=[dict(r) for r in rows])

@app.get('/api/transactions')
def transactions():
    with db() as con:
        rows = con.execute('SELECT id,student_name,uid,items_json,total,balance_after,created_at FROM transactions ORDER BY id DESC LIMIT 20').fetchall()
    import json
    return jsonify(transactions=[{**dict(r), 'items':json.loads(r['items_json'])} for r in rows])

if __name__ == '__main__':
    init_db()
    print('RFID Smart Shop: http://127.0.0.1:5000')
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
