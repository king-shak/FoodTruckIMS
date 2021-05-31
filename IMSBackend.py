from re import template
import re
from typing import DefaultDict
from flask import Flask, render_template, redirect, url_for, request, Response, send_from_directory
import os
import signal
import sys
import json
from flask.helpers import url_for
from flask_socketio import SocketIO, emit
import psycopg2
from psycopg2 import OperationalError, sql

os.environ["GEVENT_SUPPORT"] = 'True'

##############################
### CREDENTIALS FOR THE DB ###
##############################
DB_NAME = "project"
USER = "pi"
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

# Now, setup our event handler for when the script is killed to close
# the connection.
def signal_handler(sig, frame):
   print('Cleaning up...')
   connection.close()
   sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

##################
### QUERY DEFS ###
##################
# Retrieves the ID of a truck given its name.
def getTruckID(truckName):
   select_query = sql.SQL('''
                  SELECT Truck.ID
                  FROM Truck
                  WHERE Truck.Name = {truckName}
                  ''').format(truckName = sql.Literal(truckName),)
   results = execute_read_query(connection, select_query)
   if (len(results) == 0):
      return None
   else:
      return results[0][0]

# Retrieves the ID of the address of a truck given its name.
def getAddressID(truckName):
   select_query = sql.SQL('''
                  SELECT Truck.AddressID
                  FROM Truck
                  WHERE Truck.Name = {truckName}
                  ''').format(truckName = sql.Literal(truckName),)
   results = execute_read_query(connection, select_query)
   if (len(results) == 0):
      return None
   else:
      return results[0][0]

# Retrieves the ID of a mealtype given its description.
def getMealTypeID(mealType):
   select_query = sql.SQL('''
                  SELECT MealType.ID
                  FROM MealType
                  WHERE MealType.Description = {mealType}
                  ''').format(mealType = sql.Literal(mealType),)
   results = execute_read_query(connection, select_query)
   if (len(results) == 0):
      return None
   else:
      return results[0][0]

# Retrieves the ID of a meal given its name.
def getMealID(mealName):
   select_query = sql.SQL('''
                  SELECT Meal.ID
                  FROM Meal
                  WHERE Meal.Name = {mealName}
                  ''').format(mealName = sql.Literal(mealName))
   results = execute_read_query(connection, select_query)
   if (len(results) == 0):
      return None
   else:
      return results[0][0]

# Retrieves the ID of an ingredient given its name.
def getIngredientID(ingredientName):
   select_query = sql.SQL('''
                  SELECT Ingredient.ID
                  FROM Ingredient
                  WHERE Ingredient.Name = {ingredientName}
                  ''').format(ingredientName = sql.Literal(ingredientName))
   results = execute_read_query(connection, select_query)
   if (len(results) == 0):
      return None
   else:
      return results[0][0]

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
   select_query = sql.SQL('''
                  SELECT Ingredient.Name
                  FROM Meal
                     JOIN MealIngredient ON (Meal.ID = MealIngredient.MealID)
                     JOIN Ingredient ON (MealIngredient.IngredientID = Ingredient.ID)
                  WHERE Meal.Name = {mealName}
                  ''').format(mealName = sql.Literal(mealName),)
   return execute_read_query(connection, select_query)

# Get a list of all meals in the system.
def getMeals():
   select_query = '''
                  SELECT Meal.Name
                  FROM Meal
                  ORDER BY Meal.Name ASC
                  '''
   return execute_read_query(connection, select_query)

# Get the information for a meal for a certian truck.
def getMealInfo(truckName, mealName):
   select_query = sql.SQL('''
                  SELECT Meal.Name, MealType.Description, Inventory.Number
                  FROM Truck
                     JOIN Inventory ON (Truck.ID = Inventory.TruckID)
                     JOIN Meal ON (Inventory.MealID = Meal.ID)
                     JOIN MealType ON (Meal.TypeID = MealType.ID)
                  WHERE Truck.Name = {truckName} AND Meal.Name = {mealName}
                  ''').format(truckName = sql.Literal(truckName),
                              mealName = sql.Literal(mealName),)
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
   searchQuery = searchQuery.strip()
   searchQuery = '%' + searchQuery + '%'
   select_query = sql.SQL('''
                  SELECT Truck.Name, Meal.Name, Inventory.Number, Address.Street, Address.City, Address.State, Address.Zip
                  FROM Truck
                     JOIN Address ON (Truck.AddressID = Address.ID)
                     JOIN Inventory ON (Truck.ID = Inventory.TruckID)
                     JOIN Meal ON (Inventory.MealID = Meal.ID)
                  WHERE Meal.Name ILIKE {searchQuery}
                  ORDER BY Truck.Name ASC
                  ''').format(searchQuery = sql.Literal(searchQuery),)
   return execute_read_query(connection, select_query)

# Creates a meal given its attributes and links it to all trucks.
# This has 5 queries to be prepared.
def addMealToDB(mealName, mealType, ingredients, truckName, availNumber):
   print("name: {0}, type: {1}, ingredients: {2}, truckName: {3}, availNumber: {4}".format(mealName, mealType, ingredients, truckName, availNumber))

   # First, create the meal entity itself.
   insert_query = sql.SQL('''
                        INSERT INTO Meal (Name, TypeID)
                        VALUES ({mealName}, {mealTypeID})''').format(mealName = sql.Literal(mealName),
                                                                     mealTypeID = sql.Literal(getMealTypeID(mealType)),)
   execute_query(connection, insert_query)

   # Link all the ingredients.
   # All the ingredients, so we don't need to worry about injection attacks.
   mealIngredients = []

   mealID = getMealID(mealName)

   if (mealID != None):
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
      # No need to worry about injection attacks here.
      connection.rollback()
      connection.autocommit = True
      cursor = connection.cursor()
      cursor.execute('''
                     INSERT INTO Inventory (TruckID, MealID, Number)
                     VALUES (%s, %s, %s)''', (getTruckID(truckName), mealID, availNumber))

      # Link the new meal to all other trucks.
      # No need to worry about injection attacks here either - we are not using
      # any of the provided input from the user.

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
      # This indicates all is good and the meal was successfully added.
      return True
   else:
      # This indicates there was an injection attack.
      return False

# Gets the information of a specific truck.
def retrieveTruckInfo(truckName):
   select_query = sql.SQL('''
                  SELECT Truck.Number, Address.Street, Address.City, Address.State, Address.Zip
                  FROM Truck
                     JOIN Address ON (Truck.AddressID = Address.ID)
                  WHERE Truck.Name = {truckName}
                  ''').format(truckName = sql.Literal(truckName))
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
def getAllTrucksInfo():
   select_query = '''
                  SELECT Truck.Name, Truck.Number, Address.Street, Address.City, Address.State, Address.Zip
                  FROM Truck
                     JOIN Address ON (Truck.AddressID = Address.ID)
                  ORDER BY Truck.Name ASC;
                  '''
   return execute_read_query(connection, select_query)

######################
### HELPER METHODS ###
######################
def isValidTruck(truckName):
   fleet = getFleet()

   for truck in fleet:
      if (truck[0] == truckName):
         return True
   
   return False

def isValidMeal(mealName):
   meals = getMeals()
   
   for meal in meals:
      if (meal[0] == mealName):
         return True
   
   return False

def isValidMealType(mealType):
   mealTypes = getMealTypes()
   
   for type in mealTypes:
      if (type[0] == mealType):
         return True
   
   return False

def isValidIngredient(ingredientName):
   ingredients = getAllIngredients()

   for ingredient in ingredients:
      if (ingredient[0] == ingredientName):
         return True
   
   return False

def isValidLength(input, maxLength):
   return len(input) <= maxLength

###############
### APP DEF ###
###############
app = Flask(__name__)
socketio = SocketIO(app)

# Event handler for the favicon.
@app.route('/favicon.ico') 
def favicon(): 
    return send_from_directory(os.path.join(app.root_path, 'static'), 'foodtruck.png', mimetype='image/vnd.microsoft.icon')

# Event handler for the 404 page - in case we missed something.
@app.errorhandler(404)
def page_not_found(error):
   return render_template('404Page.html'), 404

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
   # First, check if is is a valid truck (the only time it won't be is if the
   # user is trying something malicious).
   if (isValidTruck(truckName)):
      # Check if they are updating the truk data.
      if (request.method == 'POST'):
         # Grab the values from the form.
         street = request.form['street']
         city = request.form['city']
         state = request.form['state']
         zip = request.form['zip']
         phoneNumber = request.form['phoneNumber']
         addressID = getAddressID(truckName)

         # Make sure the truck name is valid.
         if (addressID != None):
            # Make sure all the attributes are valid.
            if (isValidLength(street, 20) and isValidLength(city, 20) and isValidLength(state, 20) and isValidLength(zip, 5) and isValidLength(phoneNumber, 10)):
               # Update truck data.
               update_query = sql.SQL('''
                              UPDATE Address
                              SET Street = {street}, City = {city}, State = {state}, Zip = {zip}
                              WHERE Address.ID = {addressID}
                              ''').format(street = sql.Literal(street),
                                          city = sql.Literal(city),
                                          state = sql.Literal(state),
                                          zip = sql.Literal(zip),
                                          addressID = sql.Literal(addressID),)
               execute_query(connection, update_query)

               # Update phone number.
               update_query = sql.SQL('''
                              UPDATE Truck
                              SET Number = {phoneNumber}
                              WHERE Truck.Name = {truckName}
                              ''').format(phoneNumber = sql.Literal(phoneNumber),
                                          truckName = sql.Literal(truckName),)
               execute_query(connection, update_query)
            else:
               # Otherwise, redirect them from where they came from to try again.
               return redirect(request.url)
         else:
            # Otherwise, return the 404 page - invlaid URL.
            return render_template('404Page.html'), 404

      # Query the DB for the truck info.
      truckInfo = retrieveTruckInfo(truckName)

      templateData = {
         'name': truckName,
         'truckInfo' : truckInfo
      }
      return render_template('FoodTruckInfo.html', **templateData)
   else:
      return render_template('404Page.html'), 404

@app.route("/<truckName>/menu")
def menu(truckName):
   # First, make sure the truck name is valid.
   if (isValidTruck(truckName)):
      templateData = {
         'name': truckName
      }

      return render_template('Menu.html', **templateData)
   else:
      return render_template('404Page.html'), 404

@app.route("/<truckName>/fleet")
def fleet(truckName):
   # First, make sure the truck name is valid.
   if (isValidTruck(truckName)):
      # Query the DB for all trucks.
      fleet = getAllTrucksInfo()

      templateData = {
         'name': truckName,
         'fleet': fleet
      }

      return render_template('Fleet.html', **templateData)
   else:
      return render_template('404Page.html'), 404

@app.route("/<truckName>/meal_info/<mealName>")
def meal_info(truckName, mealName):
   # First, make sure the truck name is valid.
   if (isValidTruck(truckName)):
      # Query the DB for a list of all meals for the dropdown.
      meals = getMeals()

      # Query the DB for info on the selected meal.
      if (mealName == "def" or not isValidMeal(mealName)):
         # We were taken here from the menu, so just choose the first meal in the
         # list.
         # Or, the meal name is valid. Could be an injection attack or just bad
         # input.
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
   else:
      return render_template('404Page.html'), 404

@app.route("/<truckName>/delete_meal/<mealName>")
def removeMeal(truckName, mealName):
   # Make sure the truck and meal are valid.
   if (isValidTruck(truckName) and isValidMeal(mealName)):
      mealID = getMealID(mealName)

      # Remove all MealIngredient entities.
      remove_query = sql.SQL('''
                              DELETE FROM MealIngredient
                              WHERE MealID = {mealID}
                              ''').format(mealID = sql.Literal(mealID))
      execute_query(connection, remove_query)

      # Remove all Inventory entities.
      remove_query = sql.SQL('''
                              DELETE FROM Inventory
                              WHERE MealID = {mealID}
                              ''').format(mealID = sql.Literal(mealID))
      execute_query(connection, remove_query)

      # Remove the meal itself.
      remove_query = sql.SQL('''
                              DELETE FROM Meal
                              WHERE ID = {mealID}
                              ''').format(mealID = sql.Literal(mealID))
      execute_query(connection, remove_query)

      # Redirect back to meal info.
      return redirect(url_for('meal_info', truckName=truckName, mealName='def'))
   else:
      return render_template('404Page.html'), 404

@socketio.on('connect', namespace='/meal')
def onConnect():
   print('Client connected to namespace meal')

@socketio.on('updateInventory', namespace='/meal')
def updateInventory(data):
   data = json.loads(data)

   # Grab the data.
   truckName = data['truckName']
   mealName = data['mealName']
   newInventory = data['updatedInventory']

   try:
      newInventory = int(newInventory)
   except:
      newInventory = -1

   newInventoryWithinRange = newInventory >= 0 and newInventory <= 1000

   # Verify the data is valid.
   if (isValidTruck(truckName) and isValidMeal(mealName) and newInventoryWithinRange):
      # Grab the ID of the truck and meal.
      truckID = getTruckID(truckName)
      mealID = getMealID(mealName)

      # Update the inventory in the DB.
      update_query = sql.SQL('''
                     UPDATE Inventory
                     SET Number = {newInventory}
                     WHERE TruckID = {truckID} AND MealID = {mealID}
                     ''').format(newInventory = sql.Literal(newInventory),
                                 truckID = sql.Literal(truckID),
                                 mealID = sql.Literal(mealID),)
      execute_query(connection, update_query)

      print("Updated {0}'s inventory of {1} to be {2}".format(truckName, mealName, newInventory))

@socketio.on('disconnect', namespace='/meal')
def onDisconnect():
   print('Client disconnected from namespace meal')

@app.route("/<truckName>/search", methods=['GET', 'POST'])
def search(truckName):
   # First, check the truck name is valid.
   if (isValidTruck(truckName)):

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
   else:
      return render_template('404Page.html'), 404

@app.route("/<truckName>/ingredients", methods=['GET', 'POST'])
def ingredientManager(truckName):
   # Make sure the truck name is valid.
   if (isValidTruck(truckName)):
      # Determine if we need to add a new ingredient.
      if (request.method == 'POST'):
         ingredientName = request.form['ingredientName']

         # Make sure the ingredient name isn't just whitespace or an empty string.
         if (ingredientName != '' and str.isspace(ingredientName) == False):
            # Make sure it is the right length and new.
            if (not isValidIngredient(ingredientName) and isValidLength(ingredientName, 30)):
               print('New Ingredient: {0}'.format(ingredientName))

               # Put it in the database.
               insert_query = sql.SQL('''
                                    INSERT INTO Ingredient (Name) VALUES ({ingredientName})
                                    ''').format(ingredientName = sql.Literal(ingredientName),)

               # Execute the INSERT command.
               execute_query(connection, insert_query)

      # Grab a list of all ingredients.
      ingredients = getAllIngredients()

      templateData = {
         'name': truckName,
         'ingredients': ingredients
      }

      return render_template('IngredientList.html', **templateData)
   else:
      # Otherwise, give them a 404.
      return render_template('404Page.html'), 404

@app.route("/<truckName>/delete_ingredient/<ingredientName>")
def removeIngredient(truckName, ingredientName):
   # Make sure the truck and ingredient are valid.
   if (isValidTruck(truckName) and isValidIngredient(ingredientName)):
      ingredientID = getIngredientID(ingredientName)

      # Remove all MealIngredient entities.
      remove_query = sql.SQL('''
                              DELETE FROM MealIngredient
                              WHERE IngredientID = {ingredientID}
                              ''').format(ingredientID = sql.Literal(ingredientID))
      execute_query(connection, remove_query)

      # Remove the ingredient itself.
      remove_query = sql.SQL('''
                              DELETE FROM Ingredient
                              WHERE ID = {ingredientID}
                              ''').format(ingredientID = sql.Literal(ingredientID))
      execute_query(connection, remove_query)

      # Redirect back to the ingredient manager.
      return redirect(url_for('ingredientManager', truckName=truckName))
   else:
      return render_template('404Page.html'), 404

# Parses the selected ingredients from the form on the create meal page.
def parseIngredients(form):
   ingredients = []

   for key, value in form.items():
      if (key != 'mealName' and key != 'mealType' and key != 'availNumber'):
         ingredients.append(key)
   
   return ingredients

@app.route("/<truckName>/create_meal", methods=['GET', 'POST'])
def createMeal(truckName):
   # Make sure the truck name is valid.
   if (isValidTruck(truckName)):
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
         # First, grab all the attributes of the meal.
         mealName = request.form['mealName']
         mealType = request.form['mealType']
         availNumber = request.form['availNumber']
         ingredients = parseIngredients(request.form)

         # Attempt to parse the available number of the meal for the currently
         # connected truck.
         try:
            availNumber = int(availNumber)
         except:
            availNumber = -1
         
         # Check all the attributes are valid.
         mealNameValid = (not isValidMeal(mealName)) and (isValidLength(mealName, 20)) and (mealName != '') and (str.isspace(mealName) == False)
         mealTypeValid = isValidMealType(mealType)
         availNumberValid = availNumber >= 0 and availNumber <= 1000

         # First, make sure we have some ingredients - you cannot have a meal without an ingredient.
         ingredientsValid = len(ingredients) > 0
         # If we have at least one ingredient:
         if (ingredientsValid):
            # Go through them all to make sure they're in the DB.
            for ingredient in ingredients:
               if (not isValidIngredient(ingredient)):
                  ingredientsValid = False
                  break
         
         # Only proceed to create the meal if all items are valid.
         if (mealNameValid and mealTypeValid and availNumberValid and ingredientsValid):
            # Create the meal.
            # Remember, as this point everything is valid, however, we still may have an
            # injection attack in mealName.
            success = addMealToDB(mealName, mealType, ingredients, truckName, availNumber)

            if (success):
               # Redirect the user to the Meal Info page, selecting the new meal.
               return redirect(url_for('meal_info', truckName=truckName, mealName=mealName))
            else:
               # Otherwise, there was an attempted injection attack, so redirect them back
               # to the create meal page.
               return redirect(request.url)
         else:
            # Otherwise, redirect them back to the create meal page.
            return redirect(request.url)
   else:
      return render_template('404Page.html'), 404

if __name__ == "__main__":
   socketio.run(app, host="0.0.0.0", debug=True)
