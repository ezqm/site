from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3, uuid, time, hashlib
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "insano_mode"

# ========= CONFIG =========
ADMIN_USER = "admin"
# senha padrão: 1234  (hash SHA256)
ADMIN_PASS_HASH = hashlib.sha256("1234".encode()).hexdigest()

# ========= DB =========
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS produtos (
        nome TEXT PRIMARY KEY,
        valor REAL,
        estoque INTEGER,
        ativo INTEGER
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS pedidos (
        id TEXT PRIMARY KEY,
        produto TEXT,
        valor REAL,
        status TEXT,
        data REAL
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS cupons (
        codigo TEXT PRIMARY KEY,
        desconto INTEGER
    )""")

    conn.commit()

    base = [
        ("100 Coins", 5, 999, 1),
        ("1.000 Coins", 25, 999, 1),
        ("10.000 Coins", 120, 999, 1),
        ("100.000 Coins", 500, 999, 1),
        ("700.000 Coins", 2500, 999, 1),
    ]
    for p in base:
        try: c.execute("INSERT INTO produtos VALUES (?,?,?,?)", p)
        except: pass

    conn.commit()
    conn.close()

init_db()

# ========= HELPERS =========
def luhn_check(card_number):
    digits = [int(d) for d in card_number if d.isdigit()]
    checksum = 0
    parity = len(digits) % 2
    for i, digit in enumerate(digits):
        if i % 2 == parity:
            digit *= 2
            if digit > 9: digit -= 9
        checksum += digit
    return checksum % 10 == 0

def detectar_bandeira(numero):
    if numero.startswith("4"): return "Visa"
    if numero.startswith("5"): return "Mastercard"
    return "Desconhecida"

def sha256(txt):
    return hashlib.sha256(txt.encode()).hexdigest()

# ========= LOJA =========
@app.route("/")
def loja():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM produtos WHERE ativo=1")
    produtos = c.fetchall()
    conn.close()
    return render_template("loja.html", produtos=produtos)

# ========= CHECKOUT =========
@app.route("/checkout/<produto>", methods=["GET","POST"])
def checkout(produto):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM produtos WHERE nome=?", (produto,))
    item = c.fetchone()

    if not item or item[3] == 0:
        return "Produto indisponível"

    valor = item[1]

    if request.method == "POST":
        numero = request.form["numero"]
        cupom = request.form.get("cupom")

        if not luhn_check(numero):
            return "Cartão inválido"

        bandeira = detectar_bandeira(numero)

        if cupom:
            c.execute("SELECT desconto FROM cupons WHERE codigo=?", (cupom,))
            cpn = c.fetchone()
            if cpn:
                valor = valor - (valor * cpn[0] / 100)

        pedido_id = str(uuid.uuid4())[:8]

        c.execute("INSERT INTO pedidos VALUES (?,?,?,?,?)",
                  (pedido_id, produto, valor, "Pago", time.time()))
        c.execute("UPDATE produtos SET estoque=estoque-1 WHERE nome=?", (produto,))
        conn.commit()
        conn.close()

        return redirect(url_for("sucesso", pedido_id=pedido_id, bandeira=bandeira))

    conn.close()
    return render_template("checkout.html", produto=item)

# ========= SUCESSO =========
@app.route("/sucesso/<pedido_id>")
def sucesso(pedido_id):
    bandeira = request.args.get("bandeira")
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,))
    pedido = c.fetchone()
    conn.close()
    return render_template("sucesso.html", pedido=pedido, bandeira=bandeira)

# ========= ADMIN =========
@app.route("/admin", methods=["GET","POST"])
def admin():
    if request.method == "POST" and "login" in request.form:
        user = request.form["user"]
        senha = sha256(request.form["senha"])
        if user == ADMIN_USER and senha == ADMIN_PASS_HASH:
            session["admin"] = True

    if not session.get("admin"):
        return render_template("admin.html", login=True)

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # criar cupom
    if request.method == "POST" and "cupom" in request.form:
        codigo = request.form["codigo"]
        desconto = int(request.form["desconto"])
        try:
            c.execute("INSERT INTO cupons VALUES (?,?)", (codigo, desconto))
            conn.commit()
        except: pass

    c.execute("SELECT * FROM pedidos")
    pedidos = c.fetchall()

    c.execute("SELECT COUNT(*) FROM pedidos")
    total_pedidos = c.fetchone()[0]

    c.execute("SELECT SUM(valor) FROM pedidos")
    total_vendas = c.fetchone()[0] or 0

    # vendas últimos 7 dias
    dados = []
    for i in range(7):
        dia = datetime.now() - timedelta(days=i)
        inicio = datetime(dia.year, dia.month, dia.day).timestamp()
        fim = inicio + 86400
        c.execute("SELECT SUM(valor) FROM pedidos WHERE data BETWEEN ? AND ?", (inicio,fim))
        total = c.fetchone()[0] or 0
        dados.append(round(total,2))
    dados.reverse()

    conn.close()

    return render_template("admin.html",
                           login=False,
                           pedidos=pedidos,
                           total_pedidos=total_pedidos,
                           total_vendas=round(total_vendas,2),
                           grafico=dados)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/admin")

if __name__ == "__main__":
    app.run()