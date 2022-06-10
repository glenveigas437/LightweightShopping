from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from utility import DBConnectivity
from flask_paginate import Pagination, get_page_args
from abc import ABC
from passlib.hash import pbkdf2_sha256
from functools import wraps


app = Flask(__name__)
client = DBConnectivity.create_mongo_connection()
app.secret_key =  '31a25654ff00049ecaca39c924828e9f'

#Session
def createSessions(user):
    session['logged_in'] = True
    session['user'] = user
    session['cart'] = {}
    session['cartTotal'] = 0


def login_required(f):
  @wraps(f)
  def wrap(*args, **kwargs):
    if 'logged_in' in session:
      return f(*args, **kwargs)
    else:
      return redirect('/')
  
  return wrap


def MergeDicts(dict1, dict2):
    if isinstance(dict1, list) and isinstance(dict2, list):
        return dict1+dict2
    elif isinstance(dict1, dict) and isinstance(dict2, dict):
        return dict(list(dict1.items())+list(dict2.items()))
    return False

#Searcher
class Searcher(ABC):
    def sortBy(self):
        pass

class AllSearch(Searcher):
    def sortBy(self, cursor, totalCount, page, perPage, offset):
        cursor=list(cursor)
        paginateProducts = get_products(cursor, offset=offset, per_page=perPage)
        pagination = Pagination(page=page, per_page=perPage, total=totalCount)

        return paginateProducts, pagination

class CategoricSearch(Searcher):
    def sortBy(self, param, cursor, page, perPage, offset):
        print(param)
        newCursor = cursor.find({"name": {'$regex' : '.*' + param[0] + '.*'}})
        totalCount = param[1][param[0]]
        final=[]
        for new in newCursor:
            final.append(new)

        paginateProducts = get_products(final, offset=offset, per_page=perPage)
        pagination = Pagination(page=page, per_page=perPage, total=totalCount)

        return paginateProducts, pagination

#Finder
class Finder(ABC):
    def findProducts(self):
        pass

class ProductFinder(Finder):
    def findProducts(self, items):
        categoryList={}
        for item in items:
            category=item['name'].split(' ')
            category=category[-1]
            if category not in categoryList:
                categoryList[category]=0
            categoryList[category]+=1
        return categoryList


def returnCategoryList():
    items = client['items']
    currentItems = items.find()
    currentItemsNew=[]
    for current in currentItems:
        currentItemsNew.append(current)
    totalCount = items.count_documents({})

    categories = ProductFinder().findProducts(currentItemsNew)
    return categories, currentItemsNew

categories, currentItemsNew =returnCategoryList()


@app.route("/")
@app.route("/home")
def home():
    return render_template('home.html')

#Login
@app.route("/login", methods=['GET','POST'])
def login():
    if request.method=='POST':
        users = client['users']
        email = request.form['email']
        user = users.find_one(email)

        print(user, user['password'])
        
        if user and pbkdf2_sha256.verify(request.form['password'], user['password']):
            createSessions(user)
            return redirect(url_for('products'))
        else:
            return jsonify({'Error':'Invalid Credentials'}), 401 

    return render_template('login.html', title='Login')

#Logout
@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for('home'))


#Products
def get_products(array, offset=0, per_page=10):
    return array[offset: offset+per_page]


@app.route("/products", methods=['GET', 'POST'])
@login_required
def products():
    global categories, currentItemsNew
    page, perPage, offset = get_page_args(page_parameter="page", per_page_parameter="perPage")

    dropdown = [key for key, value in categories.items()]
    if request.method == 'POST':
        selected = request.form['inlineFormCustomSelect']   
        return redirect(url_for('viewProducts', selected=selected))
    
    paginateProducts, pagination = AllSearch().sortBy(currentItemsNew, len(currentItemsNew), page, perPage, offset)
    return render_template('products.html', title='Products', productsCursor=paginateProducts, page=page, per_page=perPage, pagination=pagination, category=dropdown)


@app.route("/viewproducts/selected", methods=['GET', 'POST'])
@login_required
def viewProducts():
    global categories
    selected = request.args.get('selected')
    
    items = client['items']
    page, perPage, offset = get_page_args(page_parameter="page", per_page_parameter="perPage")

    paginateProducts, pagination = CategoricSearch().sortBy((selected,categories), items, page, perPage, offset)
    return render_template('viewProducts.html', title='Products', productsCursor=paginateProducts, page=page, per_page=perPage, pagination=pagination)


#Cart
@app.route("/addtocart", methods=['POST'])
@login_required
def addToCart():
    try:
        product = request.form['productID']
        productDetails = client.items.find_one({"_id":product})
        if productDetails and request.method=='POST':
            cartItems = {product:{'Name': productDetails['name'], 'Price':productDetails['price'], 'Quantity': 1, 'Total':round((productDetails['price']*1),2)}}
            if 'cart' in session:
                if product in session['cart']:
                    for key, item in session['cart'].items():
                        if key == product:
                            session.modified = True
                            item['Quantity']+=1
                            return redirect(request.referrer)
                else:
                    session['cart']=MergeDicts(session['cart'], cartItems)
                    return redirect(request.referrer)
            else:
                session['cart']=cartItems
                return redirect(request.referrer)
    except Exception as e:
        print(e)

@app.route("/viewcart", methods=['GET', 'POST'])
@login_required
def viewCart():
    if len(session['cart'])==0:
        return redirect(request.referrer)

    if len(session['cart'])>0:
        session.modified = True
        session['cartTotal'] = 0
        for key, value in session['cart'].items():
            session['cartTotal']+=value['Total']
            session['cartTotal']=round(session['cartTotal'], 2)

    return render_template('viewCart.html')

@app.route('/updatecart/<products>', methods=['GET','POST'])
@login_required
def updateCart(products):
    if 'cart' not in session or len(session['cart'])<=0:
        return redirect(url_for('products'))

    print(request.method)
    if request.method=='POST':
        quantity = request.form['quantity']
        try:
            session.modify = True
            for key, item in session['cart'].items():
                if(key==products):
                    print(key, products)
                    item['Quantity']=int(quantity)
                    item['Total']=item['Price']*item['Quantity']
                    item['Total']=round(item['Total'], 2)
                    session[key]=item
                    return redirect(url_for('viewCart'))
        except Exception as e:
            print(e)
            return redirect(url_for('viewCart'))


@app.route('/deleteitemfromcart/<products>', methods=['GET','POST'])
@login_required
def deleteItemFromCart(products):
    if 'cart' not in session or len(session['cart']) <= 0:
        return redirect(url_for('products'))
    try:
        session.modified = True
        for key , item in session['cart'].items():
            if key == products:
                print(key, products)
                session['cart'].pop(key, None)
                return redirect(url_for('viewCart'))
    except Exception as e:
        print(e)
        return redirect(url_for('viewCart'))


@app.route('/clearcart')
@login_required
def clearCart():
    try:
        session['cart'].clear()
        session['cartTotal']=0
        return redirect(url_for('products'))
    except Exception as e:
        print(e)
    

#Order
@app.route("/addorder")
@login_required
def addOrder():
    count=client.orders.count_documents({})
    print(count)
    try:
        order={
        '_id':count+1,
        'user':session['user']['email'],
        'bill':session['cart'],
        'total':session['cartTotal']
        }
        client.orders.insert_one(order)
        session['cart'].clear()
        session['cartTotal']=0
        return redirect(url_for('products'))
    except Exception as e:
        print(e)

@app.route("/previousorders", methods=['GET'])
@login_required
def previousOrders():
    allOrders=client.orders.find({"user":session['user']['email']})
    
    orderDict={}
    for order in allOrders:
        orderDict[order['_id']]=order

    if not len(orderDict):
        return redirect(request.referrer)
    return render_template("previousOrders.html", orders=orderDict)
        

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=True)
