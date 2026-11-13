"""
MajesticMarket — Premium Second-Hand Marketplace
Flask + SQLite + Bootstrap 5
"""
import os, re, json, sqlite3
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from functools import wraps

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp"
}

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )

# ─── App Setup ───────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'majestic_market_ultrasecret_2024_xyz'

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DATABASE      = os.path.join(BASE_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXT   = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['UPLOAD_FOLDER']      = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'static', 'images', 'products'), exist_ok=True)

# ─── DB Helpers ──────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def q(sql, params=(), one=False):
    """Quick read helper."""
    db = get_db()
    cur = db.execute(sql, params)
    result = cur.fetchone() if one else cur.fetchall()
    db.close()
    return result

# ─── DB Init ─────────────────────────────────────────────────────────────────
def init_db():
    db = get_db(); c = db.cursor()

    c.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        username    TEXT UNIQUE NOT NULL,
        email       TEXT UNIQUE NOT NULL,
        password    TEXT NOT NULL,
        bio         TEXT DEFAULT '',
        is_admin    INTEGER DEFAULT 0,
        can_upload  INTEGER DEFAULT 1,
        can_comment INTEGER DEFAULT 1,
        is_suspended INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS categories (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        icon TEXT DEFAULT 'tag'
    );

    CREATE TABLE IF NOT EXISTS products (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT NOT NULL,
        description TEXT NOT NULL,
        category_id INTEGER,
        price       REAL NOT NULL,
        condition   TEXT DEFAULT 'Good',
        status      TEXT DEFAULT 'available',
        image       TEXT DEFAULT '',
        seller_id   INTEGER NOT NULL,
        views       INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (seller_id)   REFERENCES users(id),
        FOREIGN KEY (category_id) REFERENCES categories(id)
    );

    CREATE TABLE IF NOT EXISTS messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id   INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        product_id  INTEGER,
        content     TEXT NOT NULL,
        is_read     INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sender_id)   REFERENCES users(id),
        FOREIGN KEY (receiver_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS favorites (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, product_id),
        FOREIGN KEY (user_id)    REFERENCES users(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );

    CREATE TABLE IF NOT EXISTS reviews (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        reviewer_id INTEGER NOT NULL,
        seller_id   INTEGER NOT NULL,
        product_id  INTEGER,
        rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        comment     TEXT DEFAULT '',
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(reviewer_id, product_id),
        FOREIGN KEY (reviewer_id) REFERENCES users(id),
        FOREIGN KEY (seller_id)   REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS mod_logs (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id   INTEGER NOT NULL,
        action     TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id  INTEGER,
        note       TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS recently_viewed (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        viewed_at  TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, product_id),
        FOREIGN KEY (user_id)    REFERENCES users(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );
    ''')

    # Migrate older schema: add missing columns silently
    migrations = [
        ('users', 'bio',          "TEXT DEFAULT ''"),
        ('users', 'can_upload',   'INTEGER DEFAULT 1'),
        ('users', 'can_comment',  'INTEGER DEFAULT 1'),
        ('users', 'is_suspended', 'INTEGER DEFAULT 0'),
        ('products', 'condition', "TEXT DEFAULT 'Good'"),
        ('products', 'status',    "TEXT DEFAULT 'available'"),
        ('products', 'views',     'INTEGER DEFAULT 0'),
        ('messages', 'is_read',   'INTEGER DEFAULT 0'),
        ('categories', 'icon',    "TEXT DEFAULT 'tag'"),
    ]
    for table, col, defn in migrations:
        try:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {col} {defn}')
        except Exception:
            pass

    # Seed categories
    cats = [
        ('Electronics',     'cpu'),
        ('Gaming',          'controller'),
        ('Furniture',       'house-door'),
        ('Clothing',        'bag'),
        ('Books',           'book'),
        ('Photography',     'camera'),
        ('Sports',          'trophy'),
        ('Home Appliances', 'lightning-charge'),
        ('Office Equipment','briefcase'),
        ('Accessories',     'watch'),
        ('Toys',            'gift'),
        ('Vehicles',        'car-front'),
        ('Music',           'music-note-beamed'),
        ('Art',             'palette'),
        ('Other',           'box-seam'),
    ]
    for name, icon in cats:
        c.execute('INSERT OR IGNORE INTO categories (name, icon) VALUES (?,?)', (name, icon))

    db.commit()

    # Seed admin
    c.execute('INSERT OR IGNORE INTO users (username,email,password,is_admin) VALUES (?,?,?,?)',
              ('admin','admin@majesticmarket.com', generate_password_hash('admin123'), 1))
    db.commit()

    # Seed demo products if empty
    if c.execute('SELECT COUNT(*) FROM products').fetchone()[0] == 0:
        _seed_demo(db)

    db.close()

def _seed_demo(db):
    c = db.cursor()
    sellers = [
        ('zhang_wei', 'zhang@demo.com', 'Tech enthusiast & gadget lover from Nanjing'),
        ('liu_yang',  'liu@demo.com',   'Gamer and collector of rare items'),
        ('wang_fang', 'wang@demo.com',  'Interior design hobbyist & home decorator'),
        ('chen_jie',  'chen@demo.com',  'Bookworm, coffee addict, software engineer'),
        ('li_ming',   'li@demo.com',    'Sports & fitness enthusiast, cycling coach'),
    ]
    for uname, email, bio in sellers:
        c.execute('INSERT OR IGNORE INTO users (username,email,password,bio) VALUES (?,?,?,?)',
                  (uname, email, generate_password_hash('pass123'), bio))
    db.commit()

    def sid(u): return c.execute('SELECT id FROM users WHERE username=?',(u,)).fetchone()[0]
    def cid(n): return c.execute('SELECT id FROM categories WHERE name=?',(n,)).fetchone()[0]

    # Picsum seed generates consistent beautiful photos
    products = [
        # Electronics
        ('Apple iPhone 13 Pro Max 256GB',
         'Excellent condition, used 8 months. Original box, charger and two protective cases included. Battery health 94%. Deep Purple. Face ID works perfectly. No scratches on screen.',
         1699, 'Electronics', 'Like New', 'picsum.photos/seed/iphone13/600/450', 'zhang_wei'),
        ('Samsung Galaxy S22 Ultra 512GB',
         'Barely used flagship. Built-in S Pen works flawlessly. 12GB RAM, 45W fast charging support. Phantom Black. Minor scuff on back, invisible with case. One owner.',
         1450, 'Electronics', 'Good', 'picsum.photos/seed/samsung_s22/600/450', 'zhang_wei'),
        ('MacBook Air M2 8GB 256GB',
         '2022 Starlight model used only for university coursework. No dead pixels. Keyboard pristine. MagSafe charger, original box included. macOS Sonoma installed.',
         5200, 'Electronics', 'Like New', 'picsum.photos/seed/macbook_m2/600/450', 'zhang_wei'),
        ('iPad Pro 11-inch 2021 WiFi 128GB',
         'Comes with Apple Pencil 2nd gen and Smart Folio case. Perfect for digital art and students. No scratches. Battery cycles: 58.',
         3100, 'Electronics', 'Good', 'picsum.photos/seed/ipad_pro/600/450', 'liu_yang'),
        ('Sony WH-1000XM5 Headphones',
         'Industry-leading noise cancellation. 30-hour battery. Used only at home for 3 months. Soft carry case and USB-C cable included. Like showroom condition.',
         1350, 'Electronics', 'Like New', 'picsum.photos/seed/sony_xm5/600/450', 'zhang_wei'),
        ('Dell XPS 15 i7-11800H RTX 3050Ti',
         '2021 model. 16GB DDR4 RAM, 512GB NVMe SSD. Stunning OLED display. Light home use only. No thermal throttling issues. Original charger and box.',
         6800, 'Electronics', 'Good', 'picsum.photos/seed/dell_xps/600/450', 'chen_jie'),
        ('DJI Mini 3 Pro Drone',
         'Flown only 5 times, total flight time 3.2 hours. All original accessories. Captures 4K/60fps video and 48MP photos. FCC mode capable. Three batteries included.',
         3800, 'Electronics', 'Like New', 'picsum.photos/seed/dji_mini3/600/450', 'zhang_wei'),
        ('Apple Watch Series 8 GPS+Cell 45mm',
         'Midnight aluminium with Sport Band. Three additional bands included. Battery cycle count 42. Always-On display and crash detection work perfectly.',
         2200, 'Electronics', 'Good', 'picsum.photos/seed/apple_watch/600/450', 'liu_yang'),
        ('Xiaomi 27-inch 4K 144Hz Monitor',
         'IPS panel, HDR600, USB-C 65W charging. Only 1 month old. Still under manufacturer warranty. Minimal desk use, no dead pixels.',
         1580, 'Electronics', 'Like New', 'picsum.photos/seed/xiaomi_monitor/600/450', 'chen_jie'),
        ('Logitech MX Master 3 Mouse',
         'Wireless Bluetooth/USB receiver. Magspeed electromagnetic scroll wheel. USB-C charging. Graphite color. Used 6 months, flawless ergonomics.',
         380, 'Electronics', 'Good', 'picsum.photos/seed/mx_master/600/450', 'chen_jie'),

        # Gaming
        ('PlayStation 5 Disc Edition Bundle',
         'Console with 2 DualSense controllers and 3 games: FIFA 24, Spider-Man 2, Gran Turismo 7. HDMI 2.1 cable included. Barely used 4 months.',
         3200, 'Gaming', 'Like New', 'picsum.photos/seed/ps5_console/600/450', 'liu_yang'),
        ('Nintendo Switch OLED White',
         '7-inch OLED screen model. Dock, 2 JoyCons, and game case with 5 cartridges (Mario Kart 8, Animal Crossing, Zelda BotW, Metroid, Pokémon). Perfect travel console.',
         2100, 'Gaming', 'Good', 'picsum.photos/seed/switch_oled/600/450', 'liu_yang'),
        ('Xbox Series X + 2 Controllers',
         '4K 120fps gaming. 1TB custom SSD. Robot White + Carbon Black DualSense compatible controllers. Game Pass Ultimate 3-month code included.',
         2650, 'Gaming', 'Good', 'picsum.photos/seed/xbox_series/600/450', 'liu_yang'),
        ('Razer BlackWidow V3 Mechanical Keyboard',
         'Razer Green mechanical switches, full RGB backlighting. USB-A wired. Anti-ghosting, macro keys. Comes with wrist rest. 7 months use.',
         550, 'Gaming', 'Good', 'picsum.photos/seed/razer_keyboard/600/450', 'liu_yang'),
        ('Steam Deck OLED 512GB',
         '2023 model with OLED display. Screen protector applied since day one. 80+ games installed, fast NVMe SSD. Dock and carrying case included.',
         3900, 'Gaming', 'Like New', 'picsum.photos/seed/steam_deck/600/450', 'liu_yang'),
        ('Gaming Chair DXRacer Formula Series',
         'Racing-style ergonomic chair. Height adjustable, 4D armrests, lumbar + neck pillow. Black/Red color. Minor armrest wear after 1 year use.',
         890, 'Gaming', 'Fair', 'picsum.photos/seed/gaming_chair/600/450', 'wang_fang'),

        # Furniture
        ('IKEA ALEX Desk 132cm White',
         'Spacious home office desk with 5 smooth-closing drawers and metal handles. Minor surface scratch hidden under monitor. Ready to collect.',
         680, 'Furniture', 'Good', 'picsum.photos/seed/ikea_desk/600/450', 'wang_fang'),
        ('Herman Miller Aeron Chair Size B',
         'PostureFit SL lumbar support, 8Z Pellicle mesh. Fully adjustable. Used in home office, never in commercial environment. Minor armrest scuff only.',
         4200, 'Furniture', 'Good', 'picsum.photos/seed/aeron_chair/600/450', 'wang_fang'),
        ('IKEA KALLAX 4x4 Shelf Unit White',
         '16-cube shelf unit, perfect for books, records, and storage. Disassembled for easy transport. All screws, fixings, and assembly manual included.',
         450, 'Furniture', 'Good', 'picsum.photos/seed/kallax_shelf/600/450', 'wang_fang'),
        ('Scandinavian Oak Coffee Table 120x60cm',
         'Solid oak veneer top with slim hairpin legs. Minimalist design. Minor scratch on one leg, not visible from sitting position. Interior delivery available.',
         620, 'Furniture', 'Fair', 'picsum.photos/seed/coffee_table/600/450', 'wang_fang'),
        ('King-Size Bed Frame Dark Walnut 180x200cm',
         'Solid wood construction with hydraulic storage drawers under the frame. Centre support rail. Mattress NOT included. Disassembly and delivery available.',
         1800, 'Furniture', 'Good', 'picsum.photos/seed/bed_frame/600/450', 'wang_fang'),

        # Clothing
        ("Arc'teryx Beta AR Jacket XL",
         'Gore-Tex Pro construction. Pitch Black color. Excellent waterproofing still 100% functional. Used 3 ski seasons, no tears or delamination. Pit zips work perfectly.',
         2300, 'Clothing', 'Good', 'picsum.photos/seed/arcteryx_jacket/600/450', 'li_ming'),
        ('Nike Air Force 1 Low White Size 43',
         'Deadstock — tried on once indoors to check fit. Original box, extra laces, and purchase receipt available. 2023 release.',
         560, 'Clothing', 'Like New', 'picsum.photos/seed/airforce1/600/450', 'li_ming'),
        ('Adidas Ultraboost 22 Light Grey Size 42',
         'Used for 10 outdoor runs. Continental rubber outsole shows minimal wear. Primeknit upper pristine. Original shoe bag and extra laces included.',
         480, 'Clothing', 'Good', 'picsum.photos/seed/ultraboost/600/450', 'li_ming'),
        ("Levi's 501 Original Jeans W32 L32",
         'Classic straight fit, medium wash. Worn only 5 times. Looks barely used. No fading or fraying. Authentic hardware.',
         290, 'Clothing', 'Like New', 'picsum.photos/seed/levis_jeans/600/450', 'chen_jie'),
        ('Canada Goose Expedition Parka Men M Navy',
         'Fusion Fit. Rated to -30°C. 625 fill power down. No rips, no stains. Original zipper garage intact. Coyote fur trim attached.',
         3800, 'Clothing', 'Good', 'picsum.photos/seed/canada_goose/600/450', 'zhang_wei'),

        # Books
        ('Clean Code — Robert C. Martin Chinese Edition',
         'Hardcover. Pencil highlights in first 5 chapters only. ISBN 978-7-302-62329-4. Perfect for software engineering students. Publisher: Tsinghua University Press.',
         45, 'Books', 'Good', 'picsum.photos/seed/clean_code/600/450', 'chen_jie'),
        ('The Art of War — Premium Annotated Edition',
         'Collector hardcover with gold-foil cover, fold-out maps, military commentary, and bilingual text. Pristine condition, displayed only.',
         88, 'Books', 'Like New', 'picsum.photos/seed/art_of_war/600/450', 'chen_jie'),
        ('Python Crash Course 3rd Edition',
         'No writing, no highlights. Perfect condition for beginner programmers. Includes chapter exercises. Publisher: No Starch Press. ISBN: 9781718502703.',
         62, 'Books', 'Like New', 'picsum.photos/seed/python_book/600/450', 'chen_jie'),
        ('Design Patterns — GoF Gang of Four',
         'Classic software engineering reference. Dog-eared at key chapters. All content fully readable. Must-have for any developer.',
         75, 'Books', 'Fair', 'picsum.photos/seed/design_patterns/600/450', 'chen_jie'),
        ('A Brief History of Time — Stephen Hawking',
         '10th Anniversary illustrated edition. Fine condition with minor cover corner wear. All illustrations intact.',
         35, 'Books', 'Good', 'picsum.photos/seed/hawking_brief/600/450', 'chen_jie'),

        # Photography
        ('Sony Alpha A7 III Body Only',
         '24.2MP full-frame mirrorless. 693 phase-detect AF points. Shutter count ~12,400. Body cap, USB-C cable, two batteries and charger included. No sensor dust.',
         8500, 'Photography', 'Good', 'picsum.photos/seed/sony_a7iii/600/450', 'zhang_wei'),
        ('Canon EF 50mm f/1.4 USM Lens',
         'Ultra-sharp prime. Clean optical glass, no fungus or haze. Smooth autofocus ring. Canon lens cap, rear cap, and UV protective filter included.',
         1200, 'Photography', 'Good', 'picsum.photos/seed/canon_50mm/600/450', 'zhang_wei'),
        ('Manfrotto 055XPRO3 Carbon Fiber Tripod',
         'Carbon fiber legs, Manfrotto ball head included. Max load 8kg. Height 167cm. Used on 2 photo trips. All locking levers firm.',
         680, 'Photography', 'Good', 'picsum.photos/seed/manfrotto/600/450', 'zhang_wei'),
        ('Peak Design Everyday Backpack 20L Charcoal',
         'All FlexFold dividers, laptop sleeve fits 15-inch MacBook. MagLatch closure. Rain fly included. Used on 4 trips, looks new.',
         980, 'Photography', 'Like New', 'picsum.photos/seed/peak_design/600/450', 'zhang_wei'),

        # Sports
        ('Trek Marlin 7 Mountain Bike 29-inch M',
         'Shimano Deore 12-speed, hydraulic disc brakes, RockShox Judy fork. Ridden 400km, freshly serviced. Ready to ride. Minor trail scuffs on frame.',
         3200, 'Sports', 'Good', 'picsum.photos/seed/trek_marlin/600/450', 'li_ming'),
        ('Xiaomi Mi Electric Scooter Pro 2',
         'Max speed 25km/h, 45km range, pneumatic tyres. App connectivity. Minor paint chip on front deck. Both original chargers included.',
         1450, 'Sports', 'Good', 'picsum.photos/seed/xiaomi_scooter/600/450', 'li_ming'),
        ('Cork Yoga Mat Premium 6mm Non-Slip',
         '183×61cm, natural cork surface, TPE foam base. Non-toxic. Hygienic — used ~30 sessions. Includes carry strap and alignment guides.',
         180, 'Sports', 'Good', 'picsum.photos/seed/yoga_mat/600/450', 'li_ming'),
        ('PowerBlock Adjustable Dumbbell Set 2–24kg',
         '12 weight increments per dumbbell. Space-saving design replaces 16 separate dumbbells. Selector pin is smooth. Like new — 2 months old.',
         980, 'Sports', 'Like New', 'picsum.photos/seed/dumbbells/600/450', 'li_ming'),
        ('Yonex Astrox 88D Professional Badminton Racket',
         'Top professional grade. Slightly used, professionally restrung at 26lbs. Comes with Yonex bag and 2 extra grip tapes.',
         620, 'Sports', 'Good', 'picsum.photos/seed/yonex_racket/600/450', 'li_ming'),

        # Home Appliances
        ('Dyson V12 Detect Slim Cordless Vacuum',
         'Laser dust detection illuminates microscopic particles. 3 cleaning heads, 40-min runtime. Auto-empty station included. Mint condition.',
         2650, 'Home Appliances', 'Like New', 'picsum.photos/seed/dyson_v12/600/450', 'wang_fang'),
        ('Midea Inverter Air Conditioner 1.5HP',
         'Cooling + heating function. Installed 2021. Professional deep-clean service completed last month. R410A refrigerant. Energy rating A++.',
         1800, 'Home Appliances', 'Good', 'picsum.photos/seed/midea_aircon/600/450', 'wang_fang'),
        ('Nespresso Vertuo Pop Coffee Machine',
         'Centrifusion extraction technology. 5 cup sizes. Aeroccino 3 milk frother included. 4-sleeve box of assorted capsules. 6 months old.',
         580, 'Home Appliances', 'Like New', 'picsum.photos/seed/nespresso/600/450', 'wang_fang'),
        ('Xiaomi Robot Vacuum S10+ Auto-Empty',
         '3000Pa suction, LiDAR mapping, no-go zones. Auto-empty station with 2.5L dustbag. All accessories and original box included.',
         1650, 'Home Appliances', 'Good', 'picsum.photos/seed/xiaomi_vacuum/600/450', 'wang_fang'),

        # Office Equipment
        ('HP LaserJet Pro M404n Network Printer',
         'Monochrome laser, Ethernet + USB. 500-page paper tray, 38ppm print speed. Home office use only. ~800 pages printed total.',
         1100, 'Office Equipment', 'Good', 'picsum.photos/seed/hp_laser/600/450', 'chen_jie'),
        ('Flexispot E7 Pro Standing Desk 160x80cm',
         'Dual-motor electric lift, memory presets. Bamboo desktop, max load 125kg. Quiet operation below 45dB. Like new, 4 months old.',
         2200, 'Office Equipment', 'Like New', 'picsum.photos/seed/standing_desk/600/450', 'wang_fang'),
        ('Anker 12-in-1 USB-C Hub A8365',
         '4K@60Hz HDMI, 3×USB-A 3.0, SD/microSD, Gigabit Ethernet, 100W PD pass-through. Compact. Original box. 2 months old.',
         180, 'Office Equipment', 'Like New', 'picsum.photos/seed/anker_hub/600/450', 'chen_jie'),

        # Accessories
        ('Fossil Townsman Automatic Watch 44mm',
         'Rose-gold case, brown genuine leather strap. Mineral crystal. Exhibition caseback. Original box, papers, and spare links included. Worn twice.',
         980, 'Accessories', 'Like New', 'picsum.photos/seed/fossil_watch/600/450', 'zhang_wei'),
        ('Ray-Ban Aviator Classic Gold G15 Lens',
         'Classic aviator frame, gold metal. G-15 green lens. No scratches on lens. Original hard case and cleaning cloth. Retail ¥1280.',
         580, 'Accessories', 'Like New', 'picsum.photos/seed/rayban/600/450', 'chen_jie'),
        ('Samsonite Cosmolite Spinner 75cm Navy',
         '4-wheel spinner, ultralight Curv shell, TSA combination lock. Used on 3 international trips. No structural damage.',
         680, 'Accessories', 'Good', 'picsum.photos/seed/samsonite/600/450', 'chen_jie'),

        # Toys
        ('LEGO Technic Bugatti Chiron 42083 Retired',
         '3599 pieces. Built once, then disassembled and stored. All pieces present. Original instruction booklet and sealed sticker sheet. Retired set.',
         1450, 'Toys', 'Like New', 'picsum.photos/seed/lego_bugatti/600/450', 'liu_yang'),
        ('Anki Cozmo Interactive AI Robot',
         'Full kit with charging dock, 3 cubes, and USB cable. Responds to face recognition. App updated to latest version. Batteries hold charge.',
         480, 'Toys', 'Good', 'picsum.photos/seed/anki_cozmo/600/450', 'liu_yang'),

        # Music
        ('Yamaha P-45 88-Key Weighted Digital Piano',
         'GHS weighted action mimics real piano feel. Sustain pedal included. Original box and power adapter. Perfect for beginners and intermediate players.',
         1680, 'Music', 'Good', 'picsum.photos/seed/yamaha_piano/600/450', 'liu_yang'),
        ('Fender CD-60S All-Mahogany Acoustic Guitar',
         'Rich warm tone with easy playability. Slight nut wear. Includes Fender gig bag, clip-on tuner, 3 picks, and spare string set.',
         780, 'Music', 'Good', 'picsum.photos/seed/fender_guitar/600/450', 'liu_yang'),

        # Art
        ('Wacom Intuos Pro Medium PTH-660',
         'Multi-touch pressure-sensitive tablet. 8192 levels of pressure. Pro Pen 2 with stand and 6 replacement nibs. Drivers updated. Perfect for digital illustration.',
         1350, 'Art', 'Like New', 'picsum.photos/seed/wacom_intuos/600/450', 'zhang_wei'),
    ]

    for title, desc, price, cat_name, condition, img_seed, seller_uname in products:
        seller_id = c.execute('SELECT id FROM users WHERE username=?', (seller_uname,)).fetchone()[0]
        cat_id    = c.execute('SELECT id FROM categories WHERE name=?', (cat_name,)).fetchone()[0]
        image_url = f'https://{img_seed}'
        c.execute('''INSERT INTO products
                     (title,description,category_id,price,condition,status,image,seller_id)
                     VALUES (?,?,?,?,?,?,?,?)''',
                  (title, desc, cat_id, price, condition, 'available', image_url, seller_id))

    db.commit()

# ─── Auth Decorators ──────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login', next=request.path))
        return f(*a, **kw)
    return dec

def admin_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if not session.get('is_admin'):
            flash('Admin access required.', 'danger')
            return redirect(url_for('index'))
        return f(*a, **kw)
    return dec

# ─── Context Processor ───────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    unread = 0
    if session.get('user_id'):
        row = q('SELECT COUNT(*) c FROM messages WHERE receiver_id=? AND is_read=0',
                (session['user_id'],), one=True)
        unread = row['c'] if row else 0
    return dict(unread_count=unread, now=datetime.now())

# ─── Template Filter ─────────────────────────────────────────────────────────
@app.template_filter('timeago')
def timeago_filter(dt_str):
    if not dt_str:
        return ''
    try:
        dt = datetime.strptime(str(dt_str)[:19], '%Y-%m-%d %H:%M:%S')
        diff = datetime.now() - dt
        if diff.days > 365: return f'{diff.days//365}y ago'
        if diff.days > 30:  return f'{diff.days//30}mo ago'
        if diff.days > 0:   return f'{diff.days}d ago'
        h = diff.seconds // 3600
        if h > 0:           return f'{h}h ago'
        m = diff.seconds // 60
        return f'{m}m ago' if m > 0 else 'just now'
    except Exception:
        return str(dt_str)[:10]

# ─── Helper: image URL ───────────────────────────────────────────────────────
def product_image_url(image_field):
    """Return a usable image URL from whatever is stored."""
    if not image_field:
        return 'https://picsum.photos/seed/placeholder/600/450'
    if image_field.startswith('http'):
        return image_field
    if image_field.startswith('/static') or image_field.startswith('static'):
        return '/' + image_field.lstrip('/')
    return url_for('static', filename=f'uploads/{image_field}')

app.jinja_env.globals['product_image_url'] = product_image_url

# ─── Routes: Public ──────────────────────────────────────────────────────────
@app.route('/')
def index():
    db = get_db()
    featured = db.execute('''
        SELECT p.*,c.name cat,c.icon cat_icon,u.username seller
        FROM products p
        LEFT JOIN categories c ON p.category_id=c.id
        LEFT JOIN users u ON p.seller_id=u.id
        WHERE p.status='available' ORDER BY p.views DESC LIMIT 8''').fetchall()
    recent = db.execute('''
        SELECT p.*,c.name cat,c.icon cat_icon,u.username seller
        FROM products p
        LEFT JOIN categories c ON p.category_id=c.id
        LEFT JOIN users u ON p.seller_id=u.id
        WHERE p.status='available' ORDER BY p.created_at DESC LIMIT 8''').fetchall()
    categories = db.execute('''
        SELECT c.*,COUNT(p.id) cnt FROM categories c
        LEFT JOIN products p ON c.id=p.category_id AND p.status='available'
        GROUP BY c.id ORDER BY cnt DESC LIMIT 12''').fetchall()
    stats = db.execute('''SELECT
        (SELECT COUNT(*) FROM products WHERE status='available') products,
        (SELECT COUNT(*) FROM users WHERE is_admin=0) users,
        (SELECT COUNT(*) FROM categories) categories,
        (SELECT COUNT(*) FROM messages) messages''').fetchone()
    # recently viewed for logged-in users
    rv = []
    if session.get('user_id'):
        rv = db.execute('''
            SELECT p.*,c.name cat FROM recently_viewed rv
            JOIN products p ON rv.product_id=p.id
            LEFT JOIN categories c ON p.category_id=c.id
            WHERE rv.user_id=? ORDER BY rv.viewed_at DESC LIMIT 4''',
            (session['user_id'],)).fetchall()
    db.close()
    return render_template('index.html', featured=featured, recent=recent,
                           categories=categories, stats=stats, rv=rv)

# ─── Routes: Auth ────────────────────────────────────────────────────────────
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        e = request.form.get('email','').strip()
        p = request.form.get('password','').strip()
        if not u or not e or not p:
            flash('All fields required.','danger')
            return redirect(url_for('register'))
        if len(p) < 6:
            flash('Password must be at least 6 characters.','danger')
            return redirect(url_for('register'))
        db = get_db()
        if db.execute('SELECT id FROM users WHERE username=? OR email=?',(u,e)).fetchone():
            db.close(); flash('Username or email already taken.','danger')
            return redirect(url_for('register'))
        db.execute('INSERT INTO users (username,email,password) VALUES (?,?,?)',
                   (u, e, generate_password_hash(p)))
        db.commit(); db.close()
        flash('Account created! Please log in.','success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','').strip()
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username=?',(u,)).fetchone()
        db.close()
        if not user or not check_password_hash(user['password'], p):
            flash('Invalid username or password.','danger')
            return render_template('login.html')
        if user['is_suspended']:
            flash('Your account has been suspended. Contact admin.','danger')
            return render_template('login.html')
        session.update(user_id=user['id'], username=user['username'],
                       is_admin=bool(user['is_admin']),
                       can_upload=bool(user['can_upload']),
                       can_comment=bool(user['can_comment']))
        flash(f'Welcome back, {user["username"]}! ✦','success')
        nxt = request.args.get('next')
        return redirect(nxt if nxt and nxt.startswith('/') else url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.','info')
    return redirect(url_for('index'))

# ─── Routes: Dashboard & Profile ─────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    db = get_db()
    prods = db.execute('''
        SELECT p.*,c.name cat FROM products p
        LEFT JOIN categories c ON p.category_id=c.id
        WHERE p.seller_id=? ORDER BY p.created_at DESC''',(uid,)).fetchall()
    inbox = db.execute(
        'SELECT COUNT(*) c FROM messages WHERE receiver_id=? AND is_read=0',(uid,)).fetchone()['c']
    fav_count = db.execute(
        'SELECT COUNT(*) c FROM favorites WHERE user_id=?',(uid,)).fetchone()['c']
    db.close()
    return render_template('dashboard.html', products=prods,
                           inbox_count=inbox, fav_count=fav_count)

@app.route('/profile/<int:uid>')
def profile(uid):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if not user:
        flash('User not found.','danger'); return redirect(url_for('index'))
    prods = db.execute('''
        SELECT p.*,c.name cat FROM products p
        LEFT JOIN categories c ON p.category_id=c.id
        WHERE p.seller_id=? ORDER BY p.created_at DESC''',(uid,)).fetchall()
    sold_count = sum(1 for p in prods if p['status']=='sold')
    reviews = db.execute('''
        SELECT r.*,u.username reviewer FROM reviews r
        LEFT JOIN users u ON r.reviewer_id=u.id
        WHERE r.seller_id=? ORDER BY r.created_at DESC LIMIT 10''',(uid,)).fetchall()
    avg_row = db.execute(
        'SELECT AVG(rating) avg, COUNT(*) cnt FROM reviews WHERE seller_id=?',(uid,)).fetchone()
    db.close()
    return render_template('profile.html', pu=user, products=prods,
                           sold_count=sold_count, reviews=reviews,
                           avg_rating=avg_row['avg'] or 0,
                           review_count=avg_row['cnt'])

@app.route('/profile/edit', methods=['GET','POST'])
@login_required
def edit_profile():
    uid = session['user_id']
    db = get_db()
    if request.method == 'POST':
        bio = request.form.get('bio','').strip()[:300]
        db.execute('UPDATE users SET bio=? WHERE id=?',(bio, uid))
        db.commit(); db.close()
        flash('Profile updated.','success')
        return redirect(url_for('profile', uid=uid))
    user = db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    db.close()
    return render_template('edit_profile.html', user=user)

# ─── Routes: Products ────────────────────────────────────────────────────────
@app.route('/products')
def products():
    fq       = request.args.get('q','').strip()
    cat_id   = request.args.get('category','').strip()
    min_p    = request.args.get('min_price','').strip()
    max_p    = request.args.get('max_price','').strip()
    status_f = request.args.get('status','available').strip()
    sort     = request.args.get('sort','newest').strip()

    db = get_db()
    sql = '''SELECT p.*,c.name cat,c.icon cat_icon,u.username seller
             FROM products p
             LEFT JOIN categories c ON p.category_id=c.id
             LEFT JOIN users u ON p.seller_id=u.id WHERE 1=1'''
    params = []
    if status_f and status_f != 'all':
        sql += ' AND p.status=?'; params.append(status_f)
    if cat_id:
        sql += ' AND p.category_id=?'; params.append(cat_id)
    if fq:
        kw = f'%{fq}%'
        sql += ''' AND (p.title LIKE ? OR p.description LIKE ?
                   OR u.username LIKE ? OR c.name LIKE ? OR p.condition LIKE ?)'''
        params += [kw]*5
    if min_p:
        try: sql += ' AND p.price>=?'; params.append(float(min_p))
        except: pass
    if max_p:
        try: sql += ' AND p.price<=?'; params.append(float(max_p))
        except: pass

    orders = {'newest':'p.created_at DESC','oldest':'p.created_at ASC',
              'price_asc':'p.price ASC','price_desc':'p.price DESC',
              'popular':'p.views DESC'}
    sql += f' ORDER BY {orders.get(sort,"p.created_at DESC")}'

    rows = db.execute(sql, params).fetchall()
    cats = db.execute('SELECT * FROM categories ORDER BY name').fetchall()
    db.close()
    return render_template('products.html', products=rows, categories=cats,
                           q=fq, cat_id=cat_id, min_p=min_p, max_p=max_p,
                           status_f=status_f, sort=sort)

@app.route('/product/<int:pid>')
def product_detail(pid):
    db = get_db()
    db.execute('UPDATE products SET views=views+1 WHERE id=?',(pid,))
    db.commit()
    p = db.execute('''
        SELECT p.*,c.name cat,c.icon cat_icon,
               u.username seller,u.id seller_uid,u.bio seller_bio
        FROM products p
        LEFT JOIN categories c ON p.category_id=c.id
        LEFT JOIN users u ON p.seller_id=u.id
        WHERE p.id=?''',(pid,)).fetchone()
    if not p:
        db.close(); flash('Product not found.','danger')
        return redirect(url_for('products'))

    # recently viewed
    if session.get('user_id'):
        db.execute('''INSERT OR REPLACE INTO recently_viewed (user_id,product_id,viewed_at)
                      VALUES (?,?,CURRENT_TIMESTAMP)''',(session['user_id'], pid))
        db.commit()

    related = db.execute('''
        SELECT p.*,c.name cat FROM products p
        LEFT JOIN categories c ON p.category_id=c.id
        WHERE p.category_id=? AND p.id!=? AND p.status='available'
        ORDER BY RANDOM() LIMIT 4''',(p['category_id'],pid)).fetchall()

    seller_stats = db.execute('''
        SELECT COUNT(*) total,
               SUM(CASE WHEN status='sold' THEN 1 ELSE 0 END) sold,
               SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) avail
        FROM products WHERE seller_id=?''',(p['seller_uid'],)).fetchone()

    avg_row = db.execute(
        'SELECT AVG(rating) avg, COUNT(*) cnt FROM reviews WHERE seller_id=?',
        (p['seller_uid'],)).fetchone()

    msgs = []
    existing_review = None
    faved = False
    if session.get('user_id'):
        uid = session['user_id']
        msgs = db.execute('''
            SELECT m.*,u.username sname FROM messages m
            LEFT JOIN users u ON m.sender_id=u.id
            WHERE m.product_id=? AND (m.sender_id=? OR m.receiver_id=?)
            ORDER BY m.created_at ASC''',(pid,uid,uid)).fetchall()
        faved = bool(db.execute(
            'SELECT id FROM favorites WHERE user_id=? AND product_id=?',(uid,pid)).fetchone())
        existing_review = db.execute(
            'SELECT * FROM reviews WHERE reviewer_id=? AND product_id=?',(uid,pid)).fetchone()

    db.close()
    return render_template('product_details.html', p=p, related=related,
                           seller_stats=seller_stats, msgs=msgs, faved=faved,
                           avg_rating=avg_row['avg'] or 0,
                           review_count=avg_row['cnt'],
                           existing_review=existing_review)

@app.route('/product/new', methods=['GET','POST'])
@login_required
def new_product():
    if not session.get('can_upload', True):
        flash('Your upload permission has been revoked. Contact an admin.','danger')
        return redirect(url_for('dashboard'))
    db = get_db()
    cats = db.execute('SELECT * FROM categories ORDER BY name').fetchall()
    db.close()
    if request.method == 'POST':
        title = request.form.get('title','').strip()
        desc  = request.form.get('description','').strip()
        cat   = request.form.get('category_id')
        price = request.form.get('price','0').strip()
        cond  = request.form.get('condition','Good')
        if not title or not desc or not price:
            flash('Title, description and price are required.','danger')
            return render_template('new_product.html', categories=cats)
        try: price = float(price)
        except: flash('Invalid price.','danger'); return render_template('new_product.html', categories=cats)
        img_val = _handle_upload(request.files.get('image'), title)
        db = get_db()
        db.execute('''INSERT INTO products
                     (title,description,category_id,price,condition,image,seller_id)
                     VALUES (?,?,?,?,?,?,?)''',
                   (title,desc,cat,price,cond,img_val,session['user_id']))
        db.commit(); db.close()
        flash('Product listed successfully! ✦','success')
        return redirect(url_for('dashboard'))
    return render_template('new_product.html', categories=cats)

def _handle_upload(file_obj, fallback_seed='item'):
    """Save uploaded file or return a Picsum placeholder."""
    if file_obj and file_obj.filename and allowed_file(file_obj.filename):
        fn = f'{datetime.now().strftime("%Y%m%d%H%M%S")}_{secure_filename(file_obj.filename)}'
        path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
        file_obj.save(path)
        # Resize with Pillow if available
        try:
            from PIL import Image
            img = Image.open(path)
            img.thumbnail((800, 600), Image.LANCZOS)
            img.save(path, optimize=True, quality=85)
        except Exception:
            pass
        return f'/static/uploads/{fn}'
    seed = re.sub(r'[^a-z0-9]', '', fallback_seed.lower())[:16] or 'item'
    return f'https://picsum.photos/seed/{seed}/600/450'

@app.route('/product/edit/<int:pid>', methods=['GET','POST'])
@login_required
def edit_product(pid):
    db = get_db()
    p = db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
    if not p or (p['seller_id'] != session['user_id'] and not session.get('is_admin')):
        db.close(); flash('Not authorized.','danger')
        return redirect(url_for('dashboard'))
    cats = db.execute('SELECT * FROM categories ORDER BY name').fetchall()
    if request.method == 'POST':
        title  = request.form.get('title','').strip()
        desc   = request.form.get('description','').strip()
        cat    = request.form.get('category_id')
        status = request.form.get('status', p['status'])
        cond   = request.form.get('condition', p['condition'])
        try: price = float(request.form.get('price','0'))
        except: price = p['price']
        img_val = p['image']
        new_img = request.files.get('image')
        if new_img and new_img.filename and allowed_file(new_img.filename):
            img_val = _handle_upload(new_img, title)
        db.execute('''UPDATE products
                      SET title=?,description=?,category_id=?,price=?,
                          condition=?,status=?,image=? WHERE id=?''',
                   (title,desc,cat,price,cond,status,img_val,pid))
        db.commit(); db.close()
        flash('Listing updated.','success')
        return redirect(url_for('product_detail', pid=pid))
    db.close()
    return render_template('edit_product.html', p=p, categories=cats)

@app.route('/product/delete/<int:pid>', methods=['POST'])
@login_required
def delete_product(pid):
    db = get_db()
    p = db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
    if p and (p['seller_id']==session['user_id'] or session.get('is_admin')):
        db.execute('DELETE FROM products WHERE id=?',(pid,))
        db.commit(); flash('Product deleted.','success')
    else:
        flash('Not authorized.','danger')
    db.close()
    return redirect(url_for('dashboard'))

@app.route('/product/status/<int:pid>/<new_status>', methods=['POST'])
@login_required
def update_status(pid, new_status):
    if new_status not in ('available','sold','reserved'):
        abort(400)
    db = get_db()
    p = db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
    if p and (p['seller_id']==session['user_id'] or session.get('is_admin')):
        db.execute('UPDATE products SET status=? WHERE id=?',(new_status,pid))
        db.commit(); flash(f'Status updated to {new_status}.','success')
    db.close()
    return redirect(url_for('dashboard'))

# ─── Routes: Reviews ─────────────────────────────────────────────────────────
@app.route('/review/<int:pid>', methods=['POST'])
@login_required
def add_review(pid):
    if not session.get('can_comment', True):
        flash('Your commenting permission has been revoked.','danger')
        return redirect(url_for('product_detail', pid=pid))
    db = get_db()
    p = db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
    if not p:
        db.close(); abort(404)
    if p['seller_id'] == session['user_id']:
        db.close(); flash('You cannot review your own listing.','warning')
        return redirect(url_for('product_detail', pid=pid))
    try:
        rating  = int(request.form.get('rating', 5))
        comment = request.form.get('comment','').strip()[:500]
        db.execute('''INSERT OR REPLACE INTO reviews
                     (reviewer_id,seller_id,product_id,rating,comment)
                     VALUES (?,?,?,?,?)''',
                   (session['user_id'], p['seller_id'], pid, rating, comment))
        db.commit(); flash('Review submitted.','success')
    except Exception:
        flash('Could not save review.','danger')
    db.close()
    return redirect(url_for('product_detail', pid=pid))

# ─── Routes: Favorites ───────────────────────────────────────────────────────
@app.route('/favorite/<int:pid>', methods=['POST'])
@login_required
def toggle_favorite(pid):
    db = get_db(); uid = session['user_id']
    exists = db.execute('SELECT id FROM favorites WHERE user_id=? AND product_id=?',(uid,pid)).fetchone()
    if exists:
        db.execute('DELETE FROM favorites WHERE user_id=? AND product_id=?',(uid,pid))
        action = 'removed'
    else:
        db.execute('INSERT OR IGNORE INTO favorites (user_id,product_id) VALUES (?,?)',(uid,pid))
        action = 'added'
    db.commit(); db.close()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(action=action)
    flash(f'Wishlist {action}.','success')
    return redirect(url_for('product_detail', pid=pid))

@app.route('/favorites')
@login_required
def favorites():
    db = get_db()
    items = db.execute('''
        SELECT p.*,c.name cat,u.username seller FROM favorites f
        JOIN products p ON f.product_id=p.id
        LEFT JOIN categories c ON p.category_id=c.id
        LEFT JOIN users u ON p.seller_id=u.id
        WHERE f.user_id=? ORDER BY f.created_at DESC''',(session['user_id'],)).fetchall()
    db.close()
    return render_template('favorites.html', items=items)

# ─── Routes: Messages ────────────────────────────────────────────────────────
@app.route('/messages')
@login_required
def messages_inbox():
    uid = session['user_id']
    db = get_db()
    convs = db.execute('''
        SELECT CASE WHEN m.sender_id=:uid THEN m.receiver_id ELSE m.sender_id END other_id,
               u.username other_name,
               MAX(m.created_at) last_time,
               SUM(CASE WHEN m.receiver_id=:uid AND m.is_read=0 THEN 1 ELSE 0 END) unread,
               (SELECT content FROM messages
                WHERE ((sender_id=:uid AND receiver_id=u.id) OR (sender_id=u.id AND receiver_id=:uid))
                ORDER BY created_at DESC LIMIT 1) preview,
               p.title prod_title, m.product_id
        FROM messages m
        LEFT JOIN users u ON u.id=(CASE WHEN m.sender_id=:uid THEN m.receiver_id ELSE m.sender_id END)
        LEFT JOIN products p ON p.id=m.product_id
        WHERE m.sender_id=:uid OR m.receiver_id=:uid
        GROUP BY other_id, m.product_id
        ORDER BY last_time DESC''', {'uid':uid}).fetchall()
    db.close()
    return render_template('messages.html', convs=convs)

@app.route('/messages/<int:other_id>', methods=['GET','POST'])
@app.route('/messages/<int:other_id>/<int:product_id>', methods=['GET','POST'])
@login_required
def conversation(other_id, product_id=None):
    uid = session['user_id']
    db = get_db()
    if request.method == 'POST':
        content = request.form.get('content','').strip()
        if content:
            db.execute('INSERT INTO messages (sender_id,receiver_id,product_id,content) VALUES (?,?,?,?)',
                       (uid, other_id, product_id, content))
            db.commit()
        # AJAX polling response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            db.execute('UPDATE messages SET is_read=1 WHERE sender_id=? AND receiver_id=?',(other_id,uid))
            db.commit()
            msgs = db.execute('''
                SELECT m.*,u.username sname FROM messages m
                LEFT JOIN users u ON m.sender_id=u.id
                WHERE ((m.sender_id=? AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=?))
                ORDER BY m.created_at ASC''',(uid,other_id,other_id,uid)).fetchall()
            db.close()
            return jsonify(msgs=[dict(m) for m in msgs])
    # Mark as read
    db.execute('UPDATE messages SET is_read=1 WHERE sender_id=? AND receiver_id=?',(other_id,uid))
    db.commit()
    msgs  = db.execute('''
        SELECT m.*,u.username sname FROM messages m
        LEFT JOIN users u ON m.sender_id=u.id
        WHERE ((m.sender_id=? AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=?))
        ORDER BY m.created_at ASC''',(uid,other_id,other_id,uid)).fetchall()
    other = db.execute('SELECT * FROM users WHERE id=?',(other_id,)).fetchone()
    prod  = db.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone() if product_id else None
    db.close()
    return render_template('conversation.html', msgs=msgs, other=other,
                           prod=prod, other_id=other_id, product_id=product_id)

# Polling endpoint for new messages
@app.route('/messages/poll/<int:other_id>')
@login_required
def poll_messages(other_id):
    uid = session['user_id']
    since = request.args.get('since', '2000-01-01 00:00:00')
    db = get_db()
    db.execute('UPDATE messages SET is_read=1 WHERE sender_id=? AND receiver_id=?',(other_id,uid))
    db.commit()
    msgs = db.execute('''
        SELECT m.*,u.username sname FROM messages m
        LEFT JOIN users u ON m.sender_id=u.id
        WHERE ((m.sender_id=? AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=?))
          AND m.created_at > ?
        ORDER BY m.created_at ASC''',(uid,other_id,other_id,uid,since)).fetchall()
    db.close()
    return jsonify(msgs=[dict(m) for m in msgs])

@app.route('/send_message/<int:seller_id>/<int:pid>', methods=['POST'])
@login_required
def send_message(seller_id, pid):
    content = request.form.get('content','').strip()
    if content:
        db = get_db()
        db.execute('INSERT INTO messages (sender_id,receiver_id,product_id,content) VALUES (?,?,?,?)',
                   (session['user_id'], seller_id, pid, content))
        db.commit(); db.close()
        flash('Message sent! ✦','success')
    return redirect(url_for('product_detail', pid=pid))

# ─── Routes: AI Assistant ────────────────────────────────────────────────────
@app.route('/ai-assistant')
@login_required
def ai_assistant():
    return render_template('ai_assistant.html')

@app.route('/ai-chat', methods=['POST'])
@login_required
def ai_chat():
    msg = (request.get_json() or {}).get('message','').strip()
    reply = ai_engine(msg)
    return jsonify(reply=reply)

def ai_engine(msg):
    """
    Fully dynamic rule-based AI. Queries live SQLite on every call.
    No hardcoded products. Works 100% offline. No paid API.
    """
    db  = get_db()
    low = msg.lower().strip()

    def fmt(rows, intro):
        if not rows:
            return ''
        out = f'<b>{intro}</b><br><br>'
        for r in rows:
            sc   = '#86efac' if r['status'] == 'available' else '#fca5a5'
            cond = r['condition'] if 'condition' in r.keys() else ''
            desc = str(r['description'])[:80] if 'description' in r.keys() else ''
            out += (
                f'<a href="/product/{r["id"]}" style="color:var(--gold-400);font-weight:600;">🏷️ {r["title"]}</a><br>'
                f'&nbsp;&nbsp;¥{r["price"]:,.0f} &nbsp;·&nbsp; {cond} &nbsp;·&nbsp; '
                f'<span style="color:{sc}">● {r["status"].capitalize()}</span><br>'
                f'&nbsp;&nbsp;<small style="color:var(--text-muted);">{desc}…</small><br><br>'
            )
        return out

    # 1. Greetings
    if re.search(r'\b(hi|hello|hey|greetings|good\s*(morning|evening|afternoon))\b', low):
        cnt = db.execute('SELECT COUNT(*) c FROM products WHERE status="available"').fetchone()['c']
        db.close()
        return (f'Hello! 👋 Welcome to Majestic Market AI.<br><br>'
                f'There are <b style="color:var(--gold-400);">{cnt} listings</b> right now.<br><br>'
                f'Try:<br>• "iPhone under 2000 RMB"<br>• "Show gaming products"<br>'
                f'• "Cheapest laptop"<br>• "Newest electronics"<br>'
                f'• "Help me write a description"<br>• "Pricing advice"')

    # 2. Description writer
    if re.search(r'(write|generate|create|make).*(description|listing|ad|post)', low):
        db.close()
        return ('<b>📝 Product Description Template:</b><br><br>'
                '<i>"[Item] in [Excellent/Good/Fair] condition.<br>'
                'Key features: [1], [2], [3]. Purchased [year] for ¥[price].<br>'
                'Selling because [reason]. Includes [accessories].<br>'
                'Price is [firm/negotiable]. Pickup in [city]."</i><br><br>'
                '<b>Tips:</b><br>'
                '• Upload 3–5 well-lit photos<br>'
                '• State brand, model, storage/size<br>'
                '• Mention all defects honestly<br>'
                '• Research similar listings to price right')

    # 3. How to sell
    if re.search(r'how.*(sell|list|post.*product|add.*item)', low):
        db.close()
        return ('<b>🛒 How to sell on Majestic Market:</b><br><br>'
                '1. <a href="/login" style="color:var(--gold-400);">Log in</a><br>'
                '2. Dashboard → <b>List New Product</b><br>'
                '3. Fill title, description, price, condition<br>'
                '4. Upload a clear photo<br>'
                '5. Click <b>Publish</b> — live instantly!<br><br>'
                '💡 Listings with photos get 3× more views!')

    # 4. How to buy
    if re.search(r'how.*(buy|purchase|contact)', low):
        db.close()
        return ('<b>🛍️ How to buy:</b><br><br>'
                '1. <a href="/products" style="color:var(--gold-400);">Browse products</a><br>'
                '2. Click an item you like<br>'
                '3. Click <b>Message Seller</b><br>'
                '4. Agree on price and meet safely<br>'
                '5. Inspect before paying<br><br>'
                '⚠️ Always inspect items in person first!')

    # 5. Pricing advice
    if re.search(r'\b(pric|pricing|how much|worth|value|cost)\b', low):
        rows = db.execute(
            'SELECT c.name, AVG(p.price) avg, COUNT(*) cnt FROM products p '
            'JOIN categories c ON p.category_id=c.id WHERE p.status="available" '
            'GROUP BY c.id ORDER BY avg DESC LIMIT 7').fetchall()
        db.close()
        out = '<b>💰 Live average prices by category:</b><br><br>'
        for r in rows:
            out += f'• {r["name"]}: <b>¥{r["avg"]:,.0f}</b> avg ({r["cnt"]} items)<br>'
        out += ('<br><b>Condition guide:</b><br>'
                '• Like New → 60–75% of retail<br>'
                '• Good → 40–55% of retail<br>'
                '• Fair → 15–30% of retail')
        return out

    # 6. Statistics
    if re.search(r'(statistic|how many|total|count|number of|stat\b)', low):
        s = db.execute(
            'SELECT (SELECT COUNT(*) FROM products WHERE status="available") avail,'
            '(SELECT COUNT(*) FROM products) total,'
            '(SELECT COUNT(*) FROM users WHERE is_admin=0) users,'
            '(SELECT COUNT(*) FROM messages) msgs,'
            '(SELECT COUNT(*) FROM categories) cats,'
            '(SELECT COUNT(*) FROM reviews) reviews').fetchone()
        db.close()
        return (f'<b>📊 Live Majestic Market stats:</b><br><br>'
                f'🛍️ Available listings: <b style="color:var(--gold-400);">{s["avail"]}</b><br>'
                f'📦 Total ever listed: <b>{s["total"]}</b><br>'
                f'👥 Registered users: <b>{s["users"]}</b><br>'
                f'💬 Messages sent: <b>{s["msgs"]}</b><br>'
                f'⭐ Reviews: <b>{s["reviews"]}</b><br>'
                f'📂 Categories: <b>{s["cats"]}</b>')

    # 7. Parse price constraints
    under  = re.search(r'under\s*[¥￥]?\s*(\d+)', low)
    over   = re.search(r'over\s*[¥￥]?\s*(\d+)', low)
    prange = re.search(r'(\d+)\s*[-~到to]\s*(\d+)', low)
    max_p  = float(under.group(1))  if under  else (float(prange.group(2)) if prange else None)
    min_p  = float(over.group(1))   if over   else (float(prange.group(1)) if prange else None)

    # 8. Modifier (sort order)
    order = 'p.views DESC'
    if re.search(r'\b(cheapest|lowest|budget|affordable)\b', low):
        order = 'p.price ASC'
    elif re.search(r'\b(newest|latest|recent|today)\b', low):
        order = 'p.created_at DESC'
    elif re.search(r'\b(expensive|highest|priciest)\b', low):
        order = 'p.price DESC'

    # 9. Stopwords for keyword extraction
    STOP = {
        'i','me','my','need','want','a','an','the','is','are','was','were','be',
        'under','over','below','above','between','rmb','yuan','cny',
        'find','show','get','any','some','please','for','to','and','or','with',
        'from','buy','sell','looking','something','what','which','where',
        'how','do','does','have','has','can','could','would','should',
        'tell','know','list','give','recommend','recommend',
        'cheapest','lowest','newest','latest','recent','today','popular',
        'trending','most','affordable','budget','expensive','good','great','best',
        'cheap','new','like','price','product','products','item','items','listing','listings',
    }
    raw = re.split(r'[\s,.\-!?]+', low)
    keywords = [w for w in raw if w and w not in STOP and len(w) > 2 and not re.match(r'^\d+$', w)]

    # 10. Dynamic category match
    cats = db.execute('SELECT * FROM categories').fetchall()
    matched_cat = None
    for cat in cats:
        if cat['name'].lower() in low:
            matched_cat = cat
            break

    # 11. Pure category browse (no other filters)
    if matched_cat and not keywords and max_p is None and min_p is None:
        rows = db.execute(
            'SELECT p.*,c.name cat,u.username seller FROM products p '
            'LEFT JOIN categories c ON p.category_id=c.id '
            'LEFT JOIN users u ON p.seller_id=u.id '
            'WHERE p.category_id=? AND p.status="available" '
            'ORDER BY p.views DESC LIMIT 6', (matched_cat['id'],)).fetchall()
        db.close()
        if rows:
            return fmt(rows, f'Top {matched_cat["name"]} listings ({len(rows)} found):')
        return (f'No {matched_cat["name"]} listings right now. '
                f'<a href="/product/new" style="color:var(--gold-400);">List one!</a>')

    # 12. Keyword / price / category combined search
    if keywords or max_p is not None or min_p is not None:
        sql = ('SELECT p.*,c.name cat,u.username seller FROM products p '
               'LEFT JOIN categories c ON p.category_id=c.id '
               'LEFT JOIN users u ON p.seller_id=u.id '
               'WHERE p.status="available" ')
        params = []
        if matched_cat:
            sql += ' AND p.category_id=?'; params.append(matched_cat['id'])
        if max_p is not None:
            sql += ' AND p.price<=?'; params.append(max_p)
        if min_p is not None:
            sql += ' AND p.price>=?'; params.append(min_p)
        for kw in keywords[:4]:
            like = f'%{kw}%'
            sql += ' AND (p.title LIKE ? OR p.description LIKE ? OR c.name LIKE ? OR u.username LIKE ?)'
            params += [like, like, like, like]
        sql += f' ORDER BY {order} LIMIT 6'
        rows = db.execute(sql, params).fetchall()
        db.close()

        parts = []
        if matched_cat: parts.append(f'in {matched_cat["name"]}')
        if prange:      parts.append(f'¥{prange.group(1)}–{prange.group(2)}')
        elif under:     parts.append(f'under ¥{under.group(1)}')
        elif over:      parts.append(f'over ¥{over.group(1)}')
        if keywords[:2]:parts.append(f'matching "{" ".join(keywords[:2])}"')
        label = ' '.join(parts) or 'your search'

        if rows:
            return fmt(rows, f'Found {len(rows)} result(s) {label}:')
        return (f'😔 <b>No listings found {label}.</b><br><br>'
                f'Try broader terms or '
                f'<a href="/products" style="color:var(--gold-400);">browse everything</a>.')

    # 13. Fallback — show latest listings
    rows = db.execute(
        'SELECT p.*,c.name cat,u.username seller FROM products p '
        'LEFT JOIN categories c ON p.category_id=c.id '
        'LEFT JOIN users u ON p.seller_id=u.id '
        'WHERE p.status="available" ORDER BY p.created_at DESC LIMIT 5').fetchall()
    db.close()
    latest = fmt(rows, 'Latest listings:') if rows else ''
    return ('<b>🤔 I\'m not sure what you\'re looking for.</b><br><br>'
            f'{latest}'
            'Or try asking:<br>'
            '• "Show laptops under 5000 RMB"<br>'
            '• "Find gaming chairs"<br>'
            '• "Cheapest electronics"<br>'
            '• "Newest furniture"<br>'
            '• "Help me write a description"<br>'
            '• "Pricing advice" or "Show statistics"')


@app.route('/admin')
@admin_required
def admin_dashboard():
    db = get_db()
    stats = db.execute('''SELECT
        (SELECT COUNT(*) FROM users WHERE is_admin=0) users,
        (SELECT COUNT(*) FROM products) products,
        (SELECT COUNT(*) FROM products WHERE status='available') available,
        (SELECT COUNT(*) FROM products WHERE status='sold') sold,
        (SELECT COUNT(*) FROM messages) messages,
        (SELECT COUNT(*) FROM categories) categories,
        (SELECT COUNT(*) FROM reviews) reviews''').fetchone()
    users    = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    products = db.execute('''
        SELECT p.*,u.username seller,c.name cat FROM products p
        LEFT JOIN users u ON p.seller_id=u.id
        LEFT JOIN categories c ON p.category_id=c.id
        ORDER BY p.created_at DESC''').fetchall()
    messages = db.execute('''
        SELECT m.*,s.username sname,r.username rname FROM messages m
        LEFT JOIN users s ON m.sender_id=s.id
        LEFT JOIN users r ON m.receiver_id=r.id
        ORDER BY m.created_at DESC LIMIT 80''').fetchall()
    cat_stats = db.execute('''
        SELECT c.name,c.icon,COUNT(p.id) cnt FROM categories c
        LEFT JOIN products p ON c.id=p.category_id AND p.status='available'
        GROUP BY c.id ORDER BY cnt DESC''').fetchall()
    top_sellers = db.execute('''
        SELECT u.username,u.id,COUNT(p.id) cnt FROM users u
        LEFT JOIN products p ON p.seller_id=u.id
        WHERE u.is_admin=0 GROUP BY u.id ORDER BY cnt DESC LIMIT 5''').fetchall()
    mod_logs = db.execute('''
        SELECT l.*,u.username admin_name FROM mod_logs l
        LEFT JOIN users u ON l.admin_id=u.id
        ORDER BY l.created_at DESC LIMIT 30''').fetchall()
    db.close()
    return render_template('admin.html', stats=stats, users=users, products=products,
                           messages=messages, cat_stats=cat_stats,
                           top_sellers=top_sellers, mod_logs=mod_logs)

def _log(db, action, target_type, target_id, note=''):
    db.execute('INSERT INTO mod_logs (admin_id,action,target_type,target_id,note) VALUES (?,?,?,?,?)',
               (session['user_id'], action, target_type, target_id, note))

@app.route('/admin/delete_user/<int:uid>', methods=['POST'])
@admin_required
def admin_delete_user(uid):
    db = get_db()
    u = db.execute('SELECT username FROM users WHERE id=?',(uid,)).fetchone()
    if u:
        db.execute('DELETE FROM messages WHERE sender_id=? OR receiver_id=?',(uid,uid))
        db.execute('DELETE FROM favorites WHERE user_id=?',(uid,))
        db.execute('DELETE FROM reviews WHERE reviewer_id=? OR seller_id=?',(uid,uid))
        db.execute('DELETE FROM products WHERE seller_id=?',(uid,))
        db.execute('DELETE FROM users WHERE id=?',(uid,))
        _log(db,'delete_user','user',uid,u['username'])
    db.commit(); db.close()
    flash('User deleted.','success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/suspend_user/<int:uid>', methods=['POST'])
@admin_required
def admin_suspend_user(uid):
    db = get_db()
    u = db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if u:
        new_val = 0 if u['is_suspended'] else 1
        db.execute('UPDATE users SET is_suspended=? WHERE id=?',(new_val,uid))
        action = 'suspend' if new_val else 'unsuspend'
        _log(db,action,'user',uid,u['username'])
        db.commit()
    db.close()
    flash('User suspension updated.','success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/toggle_permission/<int:uid>/<perm>', methods=['POST'])
@admin_required
def admin_toggle_permission(uid, perm):
    if perm not in ('can_upload','can_comment'):
        abort(400)
    db = get_db()
    u = db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if u:
        new_val = 0 if u[perm] else 1
        db.execute(f'UPDATE users SET {perm}=? WHERE id=?',(new_val,uid))
        _log(db,f'toggle_{perm}','user',uid,f'{u["username"]} → {new_val}')
        db.commit()
    db.close()
    flash('Permission updated.','success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_product/<int:pid>', methods=['POST'])
@admin_required
def admin_delete_product(pid):
    db = get_db()
    p = db.execute('SELECT title FROM products WHERE id=?',(pid,)).fetchone()
    if p:
        db.execute('DELETE FROM products WHERE id=?',(pid,))
        _log(db,'delete_product','product',pid,p['title'])
        db.commit()
    db.close()
    flash('Product deleted.','success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_message/<int:mid>', methods=['POST'])
@admin_required
def admin_delete_message(mid):
    db = get_db()
    db.execute('DELETE FROM messages WHERE id=?',(mid,))
    _log(db,'delete_message','message',mid,'')
    db.commit(); db.close()
    flash('Message deleted.','success')
    return redirect(url_for('admin_dashboard'))

# ─── Run ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    print('='*52)
    print(' ✦  Majestic Market — Enhanced Edition')
    print('    http://127.0.0.1:5000')
    print('    Admin: admin / admin123')
    print('='*52)
    app.run(debug=True)
