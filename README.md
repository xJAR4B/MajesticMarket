---
| Username  | Password      |
| --------- | ------------- |
| admin     | `admin123`    |
| zhang_wei | `password123` |
| liu_yang  | `password123` |
| chen_xin  | `password123` |
| wang_li   | `password123` |
| li_na     | `password123` |
| ljad      | `jad123`      |
---

## ⚡ Quick Start (3 steps)

**1. Install dependencies**
```
pip install flask werkzeug
```

**2. Run the app**
```
python app.py
```

**3. Open your browser**
```
http://127.0.0.1:5000
```

---

## 🔑 Default Admin Account

| Field    | Value               |
|----------|---------------------|
| Username | `admin`             |
| Password | `admin123`          |
| URL      | `/admin`            |

---

## 📁 Project Structure

```
MajesticMarket/
│
├── app.py                  ← Main Flask application (all routes + AI logic)
├── database.db             ← SQLite database (auto-created on first run)
├── requirements.txt        ← Python dependencies
│
├── templates/              ← HTML pages (Jinja2)
│   ├── base.html           ← Shared layout (navbar, footer, flash messages)
│   ├── index.html          ← Homepage with hero, product grid, search
│   ├── login.html          ← User login form
│   ├── register.html       ← User registration form
│   ├── dashboard.html      ← Logged-in user dashboard
│   ├── products.html       ← Browse & search all products
│   ├── product_details.html← Single product page + messaging
│   ├── new_product.html    ← List a new product form
│   ├── profile.html        ← Public user profile
│   ├── messages.html       ← Message inbox
│   ├── conversation.html   ← Individual chat thread
│   ├── ai_assistant.html   ← AI chat interface
│   └── admin.html          ← Admin dashboard
│
├── static/
│   ├── css/style.css       ← Dark blue/gold glassmorphism theme
│   ├── js/script.js        ← Vanilla JS (scroll animations, AI chat, etc.)
│   └── uploads/            ← User-uploaded product images
```

---

## 🗄️ Database Tables

| Table       | Purpose                            |
|-------------|------------------------------------|
| users       | Stores registered user accounts    |
| products    | All marketplace listings           |
| messages    | Buyer-seller chat messages         |
| categories  | Product category list              |

---

## 🤖 AI Assistant

The AI assistant uses **rule-based Python logic** (no paid API required).
It works by matching keywords in the user's message and querying the SQLite database.

**Capabilities:**
- Product search by budget (e.g. "laptop under 3000 RMB")
- Category browsing (e.g. "show me electronics")
- Product description template generator
- Selling & buying guides
- Pricing recommendations
- Live marketplace statistics

---

## 🛠️ Tech Stack

| Layer     | Technology      |
|-----------|-----------------|
| Backend   | Python + Flask  |
| Database  | SQLite          |
| Frontend  | HTML + CSS + JS |
| UI Framework | Bootstrap 5  |
| Auth      | Flask sessions + Werkzeug password hashing |
