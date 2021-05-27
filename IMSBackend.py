from re import template
from typing import DefaultDict
from flask import Flask, render_template, redirect, url_for, request, Response, send_from_directory
import os
import json
from flask.helpers import url_for
from flask_socketio import SocketIO, emit
import psycopg2
from psycopg2 import OperationalError

# Credentials for the DB.
DB_NAME = "project"
USER = "postgres"
PASSWORD = "foobar"
HOST = "127.0.0.1"
PORT = 5432

# Some methods for working with the DB.
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

# Connect to the DB.
connection = create_connection(DB_NAME, USER, PASSWORD, HOST, PORT)

# Verify the connection succeeded.
if (connection is None):
   quit()

# Setup our Flask App
app = Flask(__name__)
socketio = SocketIO(app)

# Static event handlers
@app.route("/")
def index():
   # Get the list of trucks.
   select_query = """
                  SELECT Truck.Name
                  FROM Truck
                  """
   truckNames = execute_read_query(connection, select_query)

   templateData = {
      'truckNames' : truckNames
   }
   return render_template('MainPage.html', **templateData)

@app.route('/favicon.ico') 
def favicon(): 
    return send_from_directory(os.path.join(app.root_path, 'static'), 'foodtruck.png', mimetype='image/vnd.microsoft.icon')

@app.route("/<truckName>")
def getTruckInfo(truckName):
   # Query the DB for the truck info.
   select_query = '''
                  SELECT Truck.Name, Truck.Number, Address.Street, Address.City, Address.State, Address.Zip
                  FROM Truck
                     JOIN Address ON (Truck.AddressID = Address.ID)
                  WHERE Truck.Name = '{0}'
                  '''.format(truckName)
   truckInfo = execute_read_query(connection, select_query)

   templateData = {
      'name': truckInfo[0][0],
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
   select_query = '''
                  SELECT Truck.Name, Truck.Number, Address.Street, Address.City, Address.State, Address.Zip
                  FROM Truck
                     JOIN Address ON (Truck.AddressID = Address.ID)
                  WHERE Truck.Name != '{0}'
                  '''.format(truckName)
   fleet = execute_read_query(connection, select_query)

   templateData = {
      'name': truckName,
      'fleet': fleet
   }

   return render_template('Fleet.html', **templateData)

@app.route("/<truckName>/meal_info/<mealName>")
def meal_info(truckName, mealName):
   # Query the DB for a list of all meals for the dropdown.
   select_query = '''
                  SELECT Meal.Name
                  FROM Meal
                  '''
   meals = execute_read_query(connection, select_query)

   # Query the DB for info on the selected meal.
   if (mealName == "def"):
      # We were taken here from the menu, so just choose the first meal in the
      # list.
      mealName = meals[0][0]
   
   select_query = '''
                  SELECT Meal.Name, MealType.Description, Inventory.Number
                  FROM Truck
                     JOIN Inventory ON (Truck.ID = Inventory.TruckID)
                     JOIN Meal ON (Inventory.MealID = Meal.ID)
                     JOIN MealType ON (Meal.TypeID = MealType.ID)
                  WHERE Truck.Name = '{0}' AND Meal.Name = '{1}'
                  '''.format(truckName, mealName)
   chosen_meal_info = execute_read_query(connection, select_query)

   # Get the ingredients for the selected meal.
   select_query = '''
                  SELECT Ingredient.Name
                  FROM Meal
                     JOIN MealIngredient ON (Meal.ID = MealIngredient.MealID)
                     JOIN Ingredient ON (MealIngredient.IngredientID = Ingredient.ID)
                  WHERE Meal.Name = '{0}'
                  '''.format(mealName)
   ingredients = execute_read_query(connection, select_query)

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
   select_query = '''
                  SELECT Truck.ID
                  FROM Truck
                  WHERE Truck.Name = '{0}'
                  '''.format(data['truckName'])
   truckID = execute_read_query(connection, select_query)[0][0]

   select_query = '''
                  SELECT Meal.ID
                  FROM Meal
                  WHERE Meal.Name = '{0}'
                  '''.format(data['mealName'])
   mealID = execute_read_query(connection, select_query)[0][0]

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

      if (str.isspace(searchQuery) == False):
         templateData['searchQuery'] = searchQuery
         print('Query: {0}'.format(searchQuery))

         # Perform the search
         select_query = '''
                        SELECT Truck.Name, Meal.Name, Inventory.Number, Address.Street, Address.City, Address.State, Address.Zip
                        FROM Truck
                           JOIN Address ON (Truck.AddressID = Address.ID)
                           JOIN Inventory ON (Truck.ID = Inventory.TruckID)
                           JOIN Meal ON (Inventory.MealID = Meal.ID)
                        WHERE Meal.Name ILIKE '%{0}%'
                        ORDER BY Meal.Name ASC
                        '''.format(searchQuery)
         searchResults = execute_read_query(connection, select_query)

         if (len(searchResults) > 0):
            templateData['searchResults'] = searchResults

   return render_template('Search.html', **templateData)

   

if __name__ == "__main__":
   socketio.run(app, debug=True)