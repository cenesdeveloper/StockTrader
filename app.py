import datetime
import pytz


from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, lookup, usd, check_password_strength, execute_query


# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

@app.route("/account", methods=["GET", "POST"])
def account():
    if request.method == "POST":

        username = request.form.get('username')
        password = request.form.get('password')
        new_password = request.form.get('new_password')
        confirmation = request.form.get('confirmation')
        amount = request.form.get('amount')

        if username:
            # Handle username change
            execute_query("UPDATE users SET username = ? WHERE id = ?", (username, session["user_id"]))

        elif password and new_password and confirmation:
            # Handle password change
            rows = execute_query(
                "SELECT * FROM users WHERE id = ?", session["user_id"],
            )
            valid, message = check_password_strength(new_password)
            if not valid:
                return apology(message)
            if not check_password_hash(rows[0]["hash"], request.form.get("password")):
                return apology("Wrong password")

            new_password = request.form.get('new_password')
            confirmation = request.form.get('confirmation')

            if new_password != confirmation:
                return apology("Passwords do not match")

            execute_query("UPDATE users SET hash = ? WHERE id = ?", (generate_password_hash(new_password), session["user_id"]))


        elif amount:
            # Handle adding money
            amount = float(request.form.get('amount'))
            cash = execute_query("SELECT cash FROM users WHERE id = ?", (session["user_id"],))[0]["cash"]
            new_cash = cash + amount
            execute_query("UPDATE users SET cash = ? WHERE id = ?", (new_cash, session["user_id"]))

        return redirect("/")
    else:
        return render_template("account.html")

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Get users stocks and shares
    transactions = execute_query("SELECT symbol, SUM(shares) as shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING shares > 0", (session["user_id"]))
    cash = execute_query("SELECT cash FROM users WHERE id = ?", (session["user_id"],))[0]["cash"]
    total = cash

    for transaction in transactions:
        quote = lookup(transaction["symbol"])
        transaction["price"] = quote["price"]
        transaction["total"] = transaction["price"] * transaction["shares"]
        total += transaction["total"]

    return render_template("index.html", transactions=transactions, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        s = request.form.get("symbol")
        if not s:
            return apology("MISSING SYMBOL")
        shares = int(request.form.get("shares"))
        if not shares:
            return apology("MISSING SHARES")
        symbol = lookup(s)
        if symbol == None:
            return apology("INVALID SYMBOL")
        user_id = session["user_id"]
        user_cash = execute_query("SELECT cash FROM users WHERE id = ?", (user_id,))
        cash = user_cash[0]["cash"]
        date = datetime.datetime.now(pytz.timezone("US/Eastern"))
        price = symbol["price"]
        if (shares * price) > cash:
            return apology("CAN'T AFFORD")
        new_cash = cash - (symbol["price"] * shares)
        execute_query("UPDATE users SET cash = ? WHERE id = ?", (new_cash, session["user_id"],))
        execute_query("INSERT INTO transactions (user_id, symbol, shares, price, date) VALUES (?, ?, ?, ?, ?)", (session["user_id"], symbol["symbol"], shares, symbol["price"], date))
        flash(f"Bought {shares} shares of {s} for {usd(shares * price)}")
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = execute_query("SELECT * FROM transactions WHERE user_id = ?", (session["user_id"],))
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = execute_query(
            "SELECT * FROM users WHERE username = ?", (request.form.get("username")))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        s = request.form.get("symbol")
        if len(s) == 0:
            return apology("MISSING SYMBOL")
        symbol = lookup(s)
        if not symbol:
            return apology("INVALID SYMBOL")
        return render_template("quoted.html", symbol=symbol)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            if len(username) == 0:
                return apology("You must provide an username")

            rows = execute_query("SELECT * FROM users WHERE username = ?", (username,))
            if len(rows) != 0:
                return apology("username already exists")

            password = request.form.get("password")

            confirmation = request.form.get("confirmation")

            valid, message = check_password_strength(password)
            
            if not valid:
                return apology(message)
            if len(password) == 0:
                return apology("You must provide password")
            if len(confirmation) == 0:
                return apology("You must provide confirmation")
            if password != confirmation:
                return apology("The password and confirmation does not match")
            execute_query("INSERT INTO users (username, hash) VALUES (?, ?)", (username, generate_password_hash(password)))
            flash('Registered Succesfully!')
            return redirect("/")

        except ValueError:
            return apology('Username already exists')
    else:
        return render_template('register.html')

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    symbols = execute_query("SELECT DISTINCT symbol FROM transactions WHERE user_id = ?", (session["user_id"],))
    if request.method == "POST":

        symbol = request.form.get("symbol")
        if not symbol:
            return apology("MISSING SYMBOL")

        share = request.form.get("shares")
        if not share or not share.isdigit() or int(share) <= 0:
            return apology("INVALID SHARES")

        # Retrieve the sum of shares from the database
        shares = execute_query("SELECT SUM(shares) as shares FROM transactions WHERE user_id = ? AND symbol = ?", (session["user_id"], symbol))[0]["shares"]
        if int(share) > shares:
            return apology("TOO MANY SHARES")
        quote = lookup(symbol)
        price = quote["price"]
        cash = execute_query("SELECT cash FROM users WHERE id = ?", (session["user_id"],))[0]["cash"]
        cash += int(share) * price
        date = datetime.datetime.now(pytz.timezone("US/Eastern"))
        execute_query("UPDATE users SET cash = ? WHERE id = ?", (cash, session["user_id"]))
        execute_query("INSERT INTO transactions (user_id, symbol, shares, price, date) VALUES (?, ?, ?, ?, ?)", (session["user_id"], symbol, -int(share), price, date))
        flash(f"Sold {shares} share(s) of {symbol} for {usd(shares * price)}")
        return redirect("/")
    else:
        return render_template("sell.html", symbols=symbols)
