from re import template
import re
from typing import DefaultDict
from flask import Flask, render_template, redirect, url_for, request, Response, send_from_directory
import os
import json
from flask.helpers import url_for
from flask_socketio import SocketIO, emit
import psycopg2
from psycopg2 import OperationalError

os.environ["GEVENT_SUPPORT"] = 'True'

##############################
### CREDENTIALS FOR THE DB ###
##############################
DB_NAME = "project"
USER = "postgres"
PASSWORD = "foobar"
HOST = "127.0.0.1"
PORT = 5432

#########################
### DB HELPER METHODS ###
#########################
# This will create a connection with the database.
def create_connection(db_name, db_user, db_password, db_host, db_port):
   connection = None
   try:
      connection = psycopg2.connect(
         database=db_name,
         user=db_user,
         password=db_password,
         host=db_host,
         port=db_port,
      )
      print("Connection to PostgreSQL DB successful")
   except OperationalError as e:
      print(f"The error '{e}' occurred")
   return connection

# This can be used for executing queries where tables need to be created, or
# when we need to update or delete certain records.
def execute_query(connection, query):
   connection.rollback()
   connection.autocommit = True
   cursor = connection.cursor()
   try:
      cursor.execute(query)
      print("Query executed successfully")
   except OperationalError as e:
      print(f"The error '{e}' occurred")

# This can be used for queries where we are selecting records to read
# (no CRUD).
def execute_read_query(connection, query):
   cursor = connection.cursor()
   result = None
   try:
      cursor.execute(query)
      result = cursor.fetchall()
      return result
   except OperationalError as e:
      print(f"The error '{e}' occurred")

################
### DB SETUP ###
################
# Connect to the DB.
connection = create_connection(DB_NAME, USER, PASSWORD, HOST, PORT)

# Verify the connection succeeded.
if (connection is None):
   quit()

##################
### QUERY DEFS ###
##################
# Retrieves the ID of a truck given its name.
def getTruckID(truckName):
   select_query = '''
                  SELECT Truck.ID
                  FROM Truck
                  WHERE Truck.Name = '{0}'
                  '''.format(truckName)
   return execute_read_query(connection, select_query)[0][0]

# Retrieves the ID of the address of a truck given its name.
def getAddressID(truckName):
   select_query = '''
                  SELECT Truck.AddressID
                  FROM Truck
                  WHERE Truck.Name = '{0}'
                  '''.format(truckName)
   return execute_read_query(connection, select_query)[0][0]

# Retrieves the ID of a mealtype given its description.
def getMealTypeID(mealType):
   select_query = '''
                  SELECT MealType.ID
                  FROM MealType
                  WHERE MealType.Description = '{0}'
                  '''.format(mealType)
   return execute_read_query(connection, select_query)[0][0]

# Retrieves the ID of a meal given its name.
def getMealID(mealName):
   select_query = '''
                  SELECT Meal.ID
                  FROM Meal
                  WHERE Meal.Name = '{0}'
                  '''.format(mealName)
   return execute_read_query(connection, select_query)[0][0]

# Retrieves the ID of an ingredient given its name.
def getIngredientID(ingredientName):
   select_query = '''
                  SELECT Ingredient.ID
                  FROM Ingredient
                  WHERE Ingredient.Name = '{0}'
                  '''.format(ingredientName)
   return execute_read_query(connection, select_query)[0][0]

# Get all ingredients in the system.
def getAllIngredients():
   select_query = '''
                  SELECT Ingredient.Name
                  FROM Ingredient
                  ORDER BY Ingredient.Name ASC
                  '''
   return execute_read_query(connection, select_query)

# Get all ingredients for a specific meal.
def getIngredients(mealName):
   select_query = '''
                  SELECT Ingredient.Name
                  FROM Meal
                     JOIN MealIngredient ON (Meal.ID = MealIngredient.MealID)
                     JOIN Ingredient ON (MealIngredient.IngredientID = Ingredient.ID)
                  WHERE Meal.Name = '{0}'
                  '''.format(mealName)
   return execute_read_query(connection, select_query)

# Get a list of all meals in the system.
def getMeals():
   select_query = '''
                  SELECT Meal.Name
                  FROM Meal
                  '''
   return execute_read_query(connection, select_query)

# Get the information for a meal for a certian truck.
def getMealInfo(truckName, mealName):
   select_query = '''
                  SELECT Meal.Name, MealType.Description, Inventory.Number
                  FROM Truck
                     JOIN Inventory ON (Truck.ID = Inventory.TruckID)
                     JOIN Meal ON (Inventory.MealID = Meal.ID)
                     JOIN MealType ON (Meal.TypeID = MealType.ID)
                  WHERE Truck.Name = '{0}' AND Meal.Name = '{1}'
                  '''.format(truckName, mealName)
   return execute_read_query(connection, select_query)

# Get all the different meal types in the DB.
def getMealTypes():
   select_query = '''
                  SELECT MealType.Description
                  FROM MealType
                  ORDER BY MealType.Description ASC
                  '''
   return execute_read_query(connection, select_query)

# Search for meals given the specified search query across the entire fleet.
def mealFleetSearch(searchQuery):
   select_query = '''
                  SELECT Truck.Name, Meal.Name, Inventory.Number, Address.Street, Address.City, Address.State, Address.Zip
                  FROM Truck
                     JOIN Address ON (Truck.AddressID = Address.ID)
                     JOIN Inventory ON (Truck.ID = Inventory.TruckID)
                     JOIN Meal ON (Inventory.MealID = Meal.ID)
                  WHERE Meal.Name ILIKE '%{0}%'
                  ORDER BY Meal.Name ASC, Truck.Name ASC
                  '''.format(searchQuery)
   return execute_read_query(connection, select_query)

# Creates a meal given its attributes and links it to all trucks.
# This has 5 queries to be prepared.
def addMealToDB(mealName, mealType, ingredients, truckName, availNumber):
   print("name: {0}, type: {1}, ingredients: {2}, truckName: {3}, availNumber: {4}".format(mealName, mealType, ingredients, truckName, availNumber))

   # First, create the meal entity itself.
   connection.rollback()
   connection.autocommit = True
   cursor = connection.cursor()
   cursor.execute('''
                  INSERT INTO Meal (Name, TypeID)
                  VALUES (%s, %s)''', (mealName, getMealTypeID(mealType)))

   # Link all the ingredients.
   mealIngredients = []

   mealID = getMealID(mealName)
   for ingredient in ingredients:
      mealIngredients.append((mealID, getIngredientID(ingredient)))

   mealIngredients_records = ", ".join(["%s"] * len(mealIngredients))

   insert_query = f'''
                  INSERT INTO MealIngredient (MealID, IngredientID)
                  VALUES {mealIngredients_records}
                  '''

   connection.rollback()
   connection.autocommit = True
   cursor = connection.cursor()
   cursor.execute(insert_query, mealIngredients)

   # Link the new meal to the current truck.
   connection.rollback()
   connection.autocommit = True
   cursor = connection.cursor()
   cursor.execute('''
                  INSERT INTO Inventory (TruckID, MealID, Number)
                  VALUES (%s, %s, %s)''', (getTruckID(truckName), mealID, availNumber))

   # Link the new meal to all other trucks.
   # First, get a list of all trucks.
   select_query = '''
                  SELECT Truck.ID
                  FROM Truck
                  '''
   trucksIDs = execute_read_query(connection, select_query)

   # Now we build the things for our query.
   inventory = []

   for truckID in trucksIDs:
      inventory.append((truckID, mealID, 0))

   inventory_records = ", ".join(["%s"] * len(inventory))

   insert_query = f'''
                  INSERT INTO Inventory (TruckID, MealID, Number)
                  VALUES {inventory_records}
                  '''
   
   connection.rollback()
   connection.autocommit = True
   cursor = connection.cursor()
   cursor.execute(insert_query, inventory)
   # And we're done!

# Gets the information of a specific truck.
def retrieveTruckInfo(truckName):
   select_query = '''
                  SELECT Truck.Number, Address.Street, Address.City, Address.State, Address.Zip
                  FROM Truck
                     JOIN Address ON (Truck.AddressID = Address.ID)
                  WHERE Truck.Name = '{0}'
                  '''.format(truckName)
   return execute_read_query(connection, select_query)

# Gets the names of all the trucks in the fleet.
def getFleet():
   select_query = """
                  SELECT Truck.Name
                  FROM Truck
                  ORDER BY Truck.Name ASC
                  """
   return execute_read_query(connection, select_query)

# Gets the information of all trucks in the fleet except the one specified.
def getAllTrucksExcept(truckName):
   select_query = '''
                  SELECT Truck.Name, Truck.Number, Address.Street, Address.City, Address.State, Address.Zip
                  FROM Truck
                     JOIN Address ON (Truck.AddressID = Address.ID)
                  WHERE Truck.Name != '{0}'
                  '''.format(truckName)
   return execute_read_query(connection, select_query)

###############
### APP DEF ###
###############
app = Flask(__name__)
socketio = SocketIO(app)

# Event handler for the favicon.
@app.route('/favicon.ico') 
def favicon(): 
    return send_from_directory(os.path.join(app.root_path, 'static'), 'foodtruck.png', mimetype='image/vnd.microsoft.icon')

# Event handler for the main page.
@app.route("/")
def index():
   # Get the list of trucks.
   truckNames = getFleet()

   templateData = {
      'truckNames' : truckNames
   }
   return render_template('MainPage.html', **templateData)

@app.route("/<truckName>", methods=['GET', 'POST'])
def getTruckInfo(truckName):
   # Check if they are updating the truk data.
   if (request.method == 'POST'):
      # Update truck data.
      update_query = '''
                     UPDATE Address
                     SET Street = '{0}', City = '{1}', State = '{2}', Zip = '{3}'
                     WHERE Address.ID = {4}
                     '''.format(request.form['street'], request.form['city'], request.form['state'], request.form['zip'], getAddressID(truckName))
      execute_query(connection, update_query)

      # Update phone number.
      update_query = '''
                     UPDATE Truck
                     SET Number = '{0}'
                     WHERE Truck.Name = '{1}'
                     '''.format(request.form['phoneNumber'], truckName)
      execute_query(connection, update_query)

   # Query the DB for the truck info.
   truckInfo = retrieveTruckInfo(truckName)

   templateData = {
      'name': truckName,
      'truckInfo' : truckInfo
   }
   return render_template('FoodTruckInfo.html', **templateData)

@app.route("/<truckName>/menu")
def menu(truckName):
   templateData = {
      'name': truckName
   }

   return render_template('Menu.html', **templateData)

@app.route("/<truckName>/fleet")
def fleet(truckName):
   # Query the DB for all trucks.
   fleet = getAllTrucksExcept(truckName)

   templateData = {
      'name': truckName,
      'fleet': fleet
   }

   return render_template('Fleet.html', **templateData)

@app.route("/<truckName>/meal_info/<mealName>")
def meal_info(truckName, mealName):
   # Query the DB for a list of all meals for the dropdown.
   meals = getMeals()

   # Query the DB for info on the selected meal.
   if (mealName == "def"):
      # We were taken here from the menu, so just choose the first meal in the
      # list.
      mealName = meals[0][0]
   
   # Get the information and ingredients for the selected meal.
   chosen_meal_info = getMealInfo(truckName, mealName)
   ingredients = getIngredients(mealName)

   # Return the rendered template.
   templateData = {
      'name' : truckName,
      'chosenMeal': mealName,
      'meals': meals,
      'chosen_meal_info': chosen_meal_info,
      'ingredients': ingredients
   }

   return render_template('MealInfo.html', **templateData)

@socketio.on('connect', namespace='/meal')
def onConnect():
   print('Client connected to namespace meal')

@socketio.on('updateInventory', namespace='/meal')
def updateInventory(data):
   data = json.loads(data)

   # Grab the ID of the truck and meal.
   truckID = getTruckID(data['truckName'])
   mealID = getMealID(data['mealName'])

   # Update the inventory in the DB.
   update_query = '''
                  UPDATE Inventory
                  SET Number = {0}
                  WHERE TruckID = {1} AND MealID = {2}
                  '''.format(data['updatedInventory'], truckID, mealID)
   execute_query(connection, update_query)

   print("Updated {0}'s inventory of {1} to be {2}".format(data['truckName'], data['mealName'], data['updatedInventory']))

@socketio.on('disconnect', namespace='/meal')
def onDisconnect():
   print('Client disconnected from namespace meal')

@app.route("/<truckName>/search", methods=['GET', 'POST'])
def search(truckName):
   templateData = {
      'name': truckName,
      'searchQuery': None,
      'searchResults': None
   }

   if (request.method == 'POST'):
      searchQuery = request.form['query']

      if (searchQuery != '' and str.isspace(searchQuery) == False):
         templateData['searchQuery'] = searchQuery
         print('Query: {0}'.format(searchQuery))

         # Perform the search
         searchResults = mealFleetSearch(searchQuery)

         if (len(searchResults) > 0):
            templateData['searchResults'] = searchResults

   return render_template('Search.html', **templateData)

@app.route("/<truckName>/ingredients", methods=['GET', 'POST'])
def ingredientManager(truckName):
   # Determine if we need to add a new ingredient.
   if (request.method == 'POST'):
      ingredientName = request.form['ingredientName']
      if (ingredientName != '' and str.isspace(ingredientName) == False):
         print('New Ingredient: {0}'.format(ingredientName))

         # Put it in the database.
         ingredient = [
            (ingredientName)
         ]

         ingredient_record = ", ".join(["%s"] * len(ingredient))

         insert_query = (f"INSERT INTO Ingredient (Name) VALUES ({ingredient_record})")

         # Execute the INSERT command.
         connection.rollback()
         connection.autocommit = True
         cursor = connection.cursor()
         cursor.execute(insert_query, ingredient)

   # Grab a list of all ingredients.
   ingredients = getAllIngredients()

   templateData = {
      'name': truckName,
      'ingredients': ingredients
   }

   return render_template('IngredientList.html', **templateData)

# Parses the selected ingredients from the form on the create meal page.
def parseIngredients(form):
   ingredients = []

   for key, value in form.items():
      if (key != 'mealName' and key != 'mealType' and key != 'availNumber'):
         ingredients.append(key)
   
   return ingredients

@app.route("/<truckName>/create_meal", methods=['GET', 'POST'])
def createMeal(truckName):
   if (request.method == 'GET'):
      # Get the different meal types and all available ingredients.
      mealTypes = getMealTypes()
      availIngredients = getAllIngredients()

      templateData = {
         'name': truckName,
         'mealTypes': mealTypes,
         'availIngredients': availIngredients
      }

      # Return the page for them to create the meal.
      return render_template('CreateMeal.html', **templateData)
   else:
      # Create the meal, and redirect them to the meal info page with the new
      # meal selected.

      # First, grab all the attributes of the meal.
      mealName = request.form['mealName']
      mealType = request.form['mealType']
      availNumber = int(request.form['availNumber'])
      ingredients = parseIngredients(request.form)

      # Create the meal.
      addMealToDB(mealName, mealType, ingredients, truckName, availNumber)

      # Redirect the user to the Meal Info page, selecting the new page.
      return redirect(url_for('meal_info', truckName=truckName, mealName=mealName))

if __name__ == "__main__":
   socketio.run(app, debug=True)